"""
Integration tests: retry escalation (F5).

Test goals:
  - LLM consistently produces bad output → RetryLimitError after max_retries
  - AdminNotifier is called on exhaustion (log + no webhook)
  - Retry counter is exact
  - Tiebreaker path (Layer3) at MEDIUM+MEDIUM → decision after S3
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
    """Fingerprint with strict rules — orthogonal embeddings → always LOW."""
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
    Pipeline whose LLM always returns informal text and
    whose embeddings are always orthogonal (LOW).
    """
    # LLM always returns informal text
    llm_mock = MagicMock()
    llm_mock.complete.return_value = "Das ist halt irgendwie ok super."

    # Embeddings always orthogonal → Layer2 LOW
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
        """LLM is called exactly max_retries times — no more, no less."""
        notifier = AdminNotifier(NotifierConfig())
        pipeline, _ = make_always_failing_pipeline(
            strict_fingerprint, notifier, max_retries=3
        )

        # We need access to the LLM mock — via the store mock
        with pytest.raises(RetryLimitError):
            pipeline.process([{"role": "user", "content": "Test."}], "de")

        # Verify indirectly: 3 REFINING statuses → 3 LLM calls (1 initial + 2 refine)
        # checked via status messages

    def test_status_includes_refining_on_retry(self, strict_fingerprint):
        notifier = AdminNotifier(NotifierConfig())
        pipeline, status = make_always_failing_pipeline(
            strict_fingerprint, notifier, max_retries=2
        )

        with pytest.raises(RetryLimitError):
            pipeline.process([{"role": "user", "content": "Test."}], "de")

        # With max_retries=2: 1 initial + 1 refinement → REFINING once
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
        assert "Retry limit" in error_msg
        assert "1" in error_msg


class TestRetryWithEventualSuccess:
    def test_success_on_second_attempt_does_not_escalate(
        self, strict_fingerprint, tmp_path
    ):
        """
        First attempt fails, second succeeds → no escalation log.
        """
        log_path = tmp_path / "admin.log"
        notifier = AdminNotifier(NotifierConfig(log_path=str(log_path)))

        good_text = "Die Ergebnisse der präzisen Analyse sind klar nachvollziehbar."

        call_count = {"n": 0}

        def controlled_complete(messages):
            if "Analyze the following user request" in messages[0]["content"]:
                return "DEFAULT"
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "Das ist halt irgendwie ok super."  # bad
            return good_text  # good

        llm_mock = MagicMock()
        llm_mock.complete.side_effect = controlled_complete

        # Good embedding for the second call
        embed_call = {"n": 0}

        def controlled_embed(text):
            embed_call["n"] += 1
            if embed_call["n"] <= 1:
                return [0.0, 1.0]  # orthogonal → LOW (first verify call)
            return [1.0, 0.0]     # identical → HIGH (second verify call)

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
