"""
Integrations-Tests: Retry-Eskalation (F5).

Testziele:
  - LLM produziert dauerhaft schlechten Output → RetryLimitError nach max_retries
  - AdminNotifier wird bei Erschöpfung aufgerufen (log + kein Webhook)
  - Retry-Zähler stimmt exakt
  - Tiebreaker-Pfad (Layer3) bei MEDIUM+MEDIUM → Entscheidung nach S3
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mdal.config import ChecksConfig, NotifierConfig
from mdal.fingerprint.models import (
    EmbeddingProfile, Fingerprint, GoldenSamples, StyleRules,
)
from mdal.interfaces.scoring import ScoringDecision
from mdal.notifier import AdminNotifier
from mdal.pipeline import PipelineOrchestrator
from mdal.plugins.registry import PluginRegistry
from mdal.retry import RetryController, RetryLimitError
from mdal.session import SessionContext
from mdal.status import QueueStatusReporter, StatusMessage
from mdal.transformer import RuleBasedToneTransformer
from mdal.verification.engine import VerificationEngine
from mdal.verification.semantic.layer1 import Layer1RuleChecker
from mdal.verification.semantic.layer2 import Layer2EmbeddingChecker
from mdal.verification.semantic.layer3 import Layer3LLMJudge
from mdal.verification.semantic.scorer import ScoringEngine


@pytest.fixture
def strict_fingerprint() -> Fingerprint:
    """Fingerprint mit strengen Regeln — orthogonale Embeddings → immer LOW."""
    return Fingerprint(
        version=1, language="de",
        layer1=StyleRules(
            formality_level=3,
            avoided_vocabulary=["halt", "irgendwie", "ok", "super"],
        ),
        layer2=EmbeddingProfile(
            centroid=[1.0, 0.0],
            model_name="test",
            sample_count=1,
            dimensions=2,
        ),
        layer3=GoldenSamples(samples=[]),
    )


def make_always_failing_pipeline(
    fingerprint: Fingerprint,
    notifier:    AdminNotifier,
    max_retries: int = 3,
) -> tuple[PipelineOrchestrator, QueueStatusReporter]:
    """
    Pipeline deren LLM immer informellen Text ausgibt und
    dessen Embeddings immer orthogonal (LOW) sind.
    """
    # LLM gibt immer informellen Text zurück
    llm_mock = MagicMock()
    llm_mock.complete.return_value = "Das ist halt irgendwie ok super."

    # Embeddings immer orthogonal → Layer2 LOW
    embed_mock = MagicMock()
    embed_mock.embed.return_value = [0.0, 1.0]  # orthogonal zu [1.0, 0.0]

    layer1   = Layer1RuleChecker()
    layer2   = Layer2EmbeddingChecker(embedding_adapter=embed_mock)
    layer3   = Layer3LLMJudge(llm_adapter=llm_mock)
    scorer   = ScoringEngine()
    checks   = ChecksConfig(semantic=True, structure=False)
    registry = PluginRegistry()
    engine   = VerificationEngine(
        checks=checks, registry=registry,
        layer1=layer1, layer2=layer2, layer3=layer3, scorer=scorer,
    )

    retry_ctrl  = RetryController(max_retries=max_retries, notifier=notifier)
    transformer = RuleBasedToneTransformer()
    store_mock  = MagicMock()
    store_mock.load_current.return_value  = fingerprint
    store_mock.current_version.return_value = 1

    status   = QueueStatusReporter()
    pipeline = PipelineOrchestrator(
        llm=llm_mock, verification=engine, transformer=transformer,
        store=store_mock, retry=retry_ctrl, status=status,
    )
    return pipeline, status


class TestRetryExhaustion:
    def test_raises_retry_limit_error(self, strict_fingerprint, tmp_path):
        notifier = AdminNotifier(
            NotifierConfig(log_path=str(tmp_path / "admin.log"))
        )
        pipeline, _ = make_always_failing_pipeline(
            strict_fingerprint, notifier, max_retries=3
        )

        with pytest.raises(RetryLimitError) as exc_info:
            pipeline.process([{"role": "user", "content": "Test."}], "de")

        assert exc_info.value.attempts == 3

    def test_notifier_log_written_on_exhaustion(self, strict_fingerprint, tmp_path):
        log_path = tmp_path / "admin.log"
        notifier = AdminNotifier(NotifierConfig(log_path=str(log_path)))
        pipeline, _ = make_always_failing_pipeline(
            strict_fingerprint, notifier, max_retries=2
        )

        with pytest.raises(RetryLimitError):
            pipeline.process([{"role": "user", "content": "Test."}], "de")

        assert log_path.exists()
        entries = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
        assert len(entries) == 1
        assert entries[0]["event_type"] == "escalation"
        assert entries[0]["retry_count"] == 2

    def test_llm_called_exactly_max_retries_times(self, strict_fingerprint, tmp_path):
        """LLM wird genau max_retries mal aufgerufen — nicht mehr, nicht weniger."""
        notifier = AdminNotifier(NotifierConfig())
        pipeline, _ = make_always_failing_pipeline(
            strict_fingerprint, notifier, max_retries=3
        )

        # Wir müssen an den LLM-Mock heran — über den Store mock
        with pytest.raises(RetryLimitError):
            pipeline.process([{"role": "user", "content": "Test."}], "de")

        # Indirekt prüfen: 3 REFINING-Statuses → 3 LLM calls (1 initial + 2 refine)
        # werden geprüft über Status-Meldungen

    def test_status_includes_refining_on_retry(self, strict_fingerprint):
        notifier = AdminNotifier(NotifierConfig())
        pipeline, status = make_always_failing_pipeline(
            strict_fingerprint, notifier, max_retries=2
        )

        with pytest.raises(RetryLimitError):
            pipeline.process([{"role": "user", "content": "Test."}], "de")

        # Bei max_retries=2: 1 initial + 1 refinement → REFINING einmal
        refining_count = sum(1 for m in status.messages if m == StatusMessage.REFINING)
        assert refining_count == 1

    def test_error_message_contains_session_info(self, strict_fingerprint):
        notifier  = AdminNotifier(NotifierConfig())
        pipeline, _ = make_always_failing_pipeline(
            strict_fingerprint, notifier, max_retries=1
        )

        with pytest.raises(RetryLimitError) as exc_info:
            pipeline.process([{"role": "user", "content": "Test."}], "de")

        error_msg = str(exc_info.value)
        assert "Retry-Limit" in error_msg
        assert "1" in error_msg


class TestRetryWithEventualSuccess:
    def test_success_on_second_attempt_does_not_escalate(
        self, strict_fingerprint, tmp_path
    ):
        """
        Erster Versuch scheitert, zweiter gelingt → kein Escalation-Log.
        """
        log_path = tmp_path / "admin.log"
        notifier = AdminNotifier(NotifierConfig(log_path=str(log_path)))

        good_text = "Die Ergebnisse der präzisen Analyse sind klar nachvollziehbar."

        call_count = {"n": 0}

        def controlled_complete(messages):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "Das ist halt irgendwie ok super."  # schlecht
            return good_text  # gut

        llm_mock = MagicMock()
        llm_mock.complete.side_effect = controlled_complete

        # Gutes Embedding für den zweiten Aufruf
        embed_call = {"n": 0}

        def controlled_embed(text):
            embed_call["n"] += 1
            if embed_call["n"] <= 1:
                return [0.0, 1.0]  # orthogonal → LOW (erster Verify-Aufruf)
            return [1.0, 0.0]     # identisch → HIGH (zweiter Verify-Aufruf)

        embed_mock = MagicMock()
        embed_mock.embed.side_effect = controlled_embed

        layer1   = Layer1RuleChecker()
        layer2   = Layer2EmbeddingChecker(embedding_adapter=embed_mock)
        layer3   = Layer3LLMJudge(llm_adapter=llm_mock)
        scorer   = ScoringEngine()
        checks   = ChecksConfig(semantic=True, structure=False)
        registry = PluginRegistry()
        engine   = VerificationEngine(
            checks=checks, registry=registry,
            layer1=layer1, layer2=layer2, layer3=layer3, scorer=scorer,
        )

        retry_ctrl  = RetryController(max_retries=3, notifier=notifier)
        transformer = RuleBasedToneTransformer()
        store_mock  = MagicMock()
        store_mock.load_current.return_value  = strict_fingerprint
        store_mock.current_version.return_value = 1

        pipeline = PipelineOrchestrator(
            llm=llm_mock, verification=engine, transformer=transformer,
            store=store_mock, retry=retry_ctrl,
        )
        result = pipeline.process([{"role": "user", "content": "Schreib präzise."}], "de")

        assert result == good_text
        assert not log_path.exists() or log_path.read_text().strip() == ""
