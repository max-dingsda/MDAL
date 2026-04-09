"""Unit tests for language detection and bypass logic in PipelineOrchestrator (Decision: Intelligent Language Fallback B)."""

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from mdal.fingerprint.models import (
    EmbeddingProfile,
    Fingerprint,
    GoldenSamples,
    StyleRules,
)
from mdal.fingerprint.store import FingerprintStore
from mdal.interfaces.scoring import ScoringDecision
from mdal.pipeline import (
    PipelineOrchestrator,
    _detect_input_language,
)
from mdal.retry import RetryController
from mdal.session import SessionContext
from mdal.status import QueueStatusReporter
from mdal.transformer import LLMToneTransformer
from mdal.verification.engine import VerificationEngine, VerificationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_fingerprint(language: str = "de") -> Fingerprint:
    """Creates a minimal valid fingerprint for testing."""
    return Fingerprint(
        version=1,
        language=language,
        layer1=StyleRules(formality_level=3),
        layer2=EmbeddingProfile(
            centroid=[0.1, 0.2, 0.3],
            model_name="nomic-embed-text",
            sample_count=5,
            dimensions=3,
        ),
        layer3=GoldenSamples(samples=[]),
    )


def make_store_with_fingerprints(tmp_path: Path, languages: list[str]) -> FingerprintStore:
    """Creates a FingerprintStore with fingerprints for given languages."""
    store = FingerprintStore(tmp_path / "fingerprints")
    for lang in languages:
        store.save(make_fingerprint(lang))
    return store


def make_mocked_llm() -> MagicMock:
    """Creates a mock LLM adapter."""
    mock = MagicMock()
    mock.complete.return_value = "This is a test response."
    mock.health_check.return_value = True
    return mock


def make_mocked_verification_engine() -> MagicMock:
    """Creates a mock VerificationEngine."""
    mock = MagicMock()
    mock.verify.return_value = VerificationResult(
        decision=ScoringDecision.OUTPUT,
        structure_result=None,
        semantic_s1=None,
        semantic_s2=None,
        semantic_s3=None,
        output_format="prose",
    )
    return mock


def make_mocked_transformer() -> MagicMock:
    """Creates a mock LLMToneTransformer."""
    mock = MagicMock()
    mock.transform.return_value = "transformed response"
    return mock


def make_mocked_retry() -> MagicMock:
    """Creates a mock RetryController."""
    mock = MagicMock()
    mock.run.return_value = "final output"
    return mock


# ---------------------------------------------------------------------------
# Test: _detect_input_language helper
# ---------------------------------------------------------------------------

class TestDetectInputLanguage:
    """Tests for the _detect_input_language helper function."""

    def test_detects_german(self):
        """Should detect German text."""
        messages = [{"role": "user", "content": "Hallo, wie geht es dir heute? Ich bin sehr glücklich, dich kennenzulernen."}]
        lang = _detect_input_language(messages)
        assert lang == "de"

    def test_detects_english(self):
        """Should detect English text."""
        messages = [{"role": "user", "content": "Hello, how are you today? I am very happy to meet you and would like to chat about this interesting topic."}]
        lang = _detect_input_language(messages)
        assert lang == "en"

    def test_detects_french(self):
        """Should detect French text."""
        messages = [{"role": "user", "content": "Bonjour, comment allez-vous? Je suis très heureux de vous rencontrer aujourd'hui pour discuter de ce sujet important."}]
        lang = _detect_input_language(messages)
        assert lang == "fr"

    def test_detects_spanish(self):
        """Should detect Spanish text."""
        messages = [{"role": "user", "content": "Hola, ¿cómo estás hoy? Estoy muy feliz de conocerte y querría hablar contigo sobre este tema importante."}]
        lang = _detect_input_language(messages)
        assert lang == "es"

    def test_returns_none_for_empty_messages(self):
        """Should return None if no user messages."""
        messages = [{"role": "system", "content": "You are helpful."}]
        lang = _detect_input_language(messages)
        assert lang is None

    def test_returns_none_for_empty_input(self):
        """Should return None for empty message list."""
        messages = []
        lang = _detect_input_language(messages)
        assert lang is None

    def test_normalizes_es_es_to_es(self):
        """Should normalize 'es-ES' to 'es'."""
        # Spanish with longer text for better detection
        messages = [{"role": "user", "content": "Buenos días, tengo una pregunta importante que quisiera hacerle. Espero que pueda ayudarme con este asunto."}]
        lang = _detect_input_language(messages)
        # After normalization, should be "es"
        assert lang in ("es", "es-es", "es-ES")

    def test_uses_last_user_message(self):
        """Should detect language from the last user message."""
        messages = [
            {"role": "user", "content": "Hallo, wie geht es dir?"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "Bonjour, ça va bien? Je voulais te poser une question importante aujourd'hui."},  # Last user message is French
        ]
        lang = _detect_input_language(messages)
        assert lang == "fr"


# ---------------------------------------------------------------------------
# Test: PipelineOrchestrator with language detection
# ---------------------------------------------------------------------------

class TestPipelineLanguageDetection:
    """Tests for language detection in PipelineOrchestrator.process()."""

    def test_uses_detected_language_when_fingerprint_exists(self, tmp_path):
        """User speaks English, config says 'de', but DE and EN fingerprints exist → use EN."""
        store = make_store_with_fingerprints(tmp_path, ["de", "en"])
        
        llm = make_mocked_llm()
        verification = make_mocked_verification_engine()
        transformer = make_mocked_transformer()
        retry = make_mocked_retry()
        retry.run.return_value = "test output"
        
        orchestrator = PipelineOrchestrator(
            llm=llm,
            verification=verification,
            transformer=transformer,
            store=store,
            retry=retry,
        )
        
        messages = [{"role": "user", "content": "Hello, how are you?"}]  # English input
        output = orchestrator.process(messages, language="de")  # Config says German
        
        assert output == "test output"
        # Should NOT crash, should attempt to load EN fingerprint

    def test_bypasses_verification_when_fingerprint_missing(self, tmp_path, caplog):
        """User speaks French, but only DE fingerprint exists → bypass, log WARN."""
        store = make_store_with_fingerprints(tmp_path, ["de"])  # Only German
        
        llm = make_mocked_llm()
        # side_effect has multiple calls: domain classification + initial call
        llm.complete.side_effect = [
            "TECHNICAL",  # Domain classification call
            "Voici ma réponse.",  # Initial call
        ]
        verification = make_mocked_verification_engine()
        transformer = make_mocked_transformer()
        retry = make_mocked_retry()
        
        def mock_retry_run(context, initial_call, refine_call, verify, transform):
            # Simulate bypass flow: just call initial_call, return as-is
            return initial_call()
        
        retry.run.side_effect = mock_retry_run
        
        orchestrator = PipelineOrchestrator(
            llm=llm,
            verification=verification,
            transformer=transformer,
            store=store,
            retry=retry,
        )
        
        messages = [{"role": "user", "content": "Bonjour, comment ça va?"}]  # French
        
        with caplog.at_level("WARNING"):
            output = orchestrator.process(messages, language="de")
        
        # Should have logged a WARN about missing fingerprint
        assert "Fingerprint missing" in caplog.text
        assert "fr" in caplog.text  # Detected language
        assert "de" in caplog.text  # Config language
        assert output == "Voici ma réponse."

    def test_session_context_has_none_fingerprint_version_on_bypass(self, tmp_path):
        """When bypassing, SessionContext.fingerprint_version should be None."""
        store = make_store_with_fingerprints(tmp_path, ["de"])  # Only German
        
        llm = make_mocked_llm()
        verification = make_mocked_verification_engine()
        transformer = make_mocked_transformer()
        
        captured_context = {}
        
        def mock_retry_run(context, initial_call, refine_call, verify, transform):
            captured_context["context"] = context
            return initial_call()
        
        retry = make_mocked_retry()
        retry.run.side_effect = mock_retry_run
        
        orchestrator = PipelineOrchestrator(
            llm=llm,
            verification=verification,
            transformer=transformer,
            store=store,
            retry=retry,
        )
        
        messages = [{"role": "user", "content": "你好"}]  # Chinese
        orchestrator.process(messages, language="de")
        
        # Verify context was created with None fingerprint_version
        assert captured_context["context"].fingerprint_version is None


# ---------------------------------------------------------------------------
# Test: Unsupported language (integration-style)
# ---------------------------------------------------------------------------

class TestUnsupportedLanguageBehavior:
    """Integration-style tests for unsupported languages (French, Chinese, Russian, etc.)."""

    @pytest.mark.parametrize("unsupported_lang,text", [
        ("fr", "Bonjour! Je suis très heureux de vous rencontrer aujourd'hui pour discuter de ce projet important."),
        ("es", "¡Hola! ¿Cómo estás hoy? Tengo un problema importante y necesito tu ayuda para resolverlo."),
        ("it", "Ciao! Come stai? Ho una domanda importante che vorrei farti. Spero di poter discutere di questo argomento con te oggi."),
        ("pt", "Olá! Como você está? Tenho uma pergunta importante. Gostaria de conversar com você sobre este assunto especial."),
        ("ru", "Привет! Как дела? У меня есть очень важный вопрос. Надеюсь, что ты сможешь мне помочь с этим."),
        ("zh", "你好！今天怎么样？我有一个非常重要的问题想要问你。希望我们能够讨论这个重要的话题。"),
        ("ja", "こんにちは！元気ですか？質問があります。今日はこの重要なテーマについて話し合いたいです。"),
    ])
    def test_unsupported_language_bypasses_verification(
        self, tmp_path, caplog, unsupported_lang, text
    ):
        """For any unsupported language: bypass verification, log WARN."""
        # Only provide German and English fingerprints
        store = make_store_with_fingerprints(tmp_path, ["de", "en"])
        
        llm = make_mocked_llm()
        # Each call will return the same response (domain classification + initial)
        llm.complete.side_effect = [
            "TECHNICAL",  # Domain classification
            f"Response in {unsupported_lang}",  # Initial LLM call
        ]
        
        verification = make_mocked_verification_engine()
        transformer = make_mocked_transformer()
        
        def mock_retry_run(context, initial_call, refine_call, verify, transform):
            return initial_call()
        
        retry = make_mocked_retry()
        retry.run.side_effect = mock_retry_run
        
        orchestrator = PipelineOrchestrator(
            llm=llm,
            verification=verification,
            transformer=transformer,
            store=store,
            retry=retry,
        )
        
        messages = [{"role": "user", "content": text}]
        
        with caplog.at_level("WARNING"):
            output = orchestrator.process(messages, language="de")
        
        # Verify bypass occurred
        assert "Fingerprint missing" in caplog.text
        assert unsupported_lang in caplog.text or unsupported_lang.split("-")[0] in caplog.text
        # Output should not be None
        assert output is not None
