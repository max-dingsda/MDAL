"""Unit-Tests für Semantic Layer 3 — LLM-as-Judge (CR-Finding #5: CoT-Format)."""

from unittest.mock import MagicMock

import pytest

from mdal.fingerprint.models import (
    EmbeddingProfile, Fingerprint, GoldenSample, GoldenSamples, StyleRules,
)
from mdal.interfaces.scoring import ScoreLevel
from mdal.session import SessionContext
from mdal.verification.semantic.layer3 import Layer3LLMJudge, _parse_judgment


def make_fingerprint(samples: list[tuple[str, str]] | None = None) -> Fingerprint:
    golden = [GoldenSample(prompt=p, response=r) for p, r in (samples or [])]
    return Fingerprint(
        version=1, language="de",
        layer1=StyleRules(formality_level=3),
        layer2=EmbeddingProfile(
            centroid=[0.1, 0.2],
            model_name="nomic-embed-text",
            sample_count=2,
            dimensions=2,
        ),
        layer3=GoldenSamples(samples=golden),
    )


def make_context() -> SessionContext:
    return SessionContext(language="de", fingerprint_version=1)


# ---------------------------------------------------------------------------
# _parse_judgment — CoT-Format (Urteil auf letzter Zeile)
# ---------------------------------------------------------------------------

class TestParseJudgment:
    def test_passt_alone(self):
        assert _parse_judgment("PASST") is True

    def test_passt_nicht_alone(self):
        assert _parse_judgment("PASST NICHT") is False

    def test_cot_passt_last_line(self):
        response = (
            "Der Text verwendet eine sachliche, strukturierte Sprache.\n"
            "PASST"
        )
        assert _parse_judgment(response) is True

    def test_cot_passt_nicht_last_line(self):
        response = (
            "Der Text ist zu informell und verwendet Umgangssprache.\n"
            "PASST NICHT"
        )
        assert _parse_judgment(response) is False

    def test_lowercase_passt(self):
        assert _parse_judgment("passt") is True

    def test_lowercase_passt_nicht(self):
        assert _parse_judgment("passt nicht") is False

    def test_multiline_cot_passt(self):
        response = (
            "Der Stil ist formal und entspricht dem Referenzniveau.\n"
            "Die Satzstruktur und der Wortschatz passen gut zu den Beispielen.\n"
            "PASST"
        )
        assert _parse_judgment(response) is True

    def test_empty_response_returns_false(self):
        assert _parse_judgment("") is False

    def test_unclear_response_returns_false(self):
        assert _parse_judgment("Ich bin nicht sicher.") is False

    def test_whitespace_around_verdict(self):
        assert _parse_judgment("  PASST  ") is True
        assert _parse_judgment("  PASST NICHT  ") is False

    def test_passt_nicht_wins_over_passt(self):
        # Wenn sowohl "PASST" als auch "PASST NICHT" im Text vorkommt:
        # letzte Zeile gewinnt
        response = "Abschnitt passt in Teilen.\nPASST NICHT"
        assert _parse_judgment(response) is False


# ---------------------------------------------------------------------------
# Layer3LLMJudge
# ---------------------------------------------------------------------------

class TestLayer3LLMJudge:
    def _make_judge(self, llm_response: str) -> tuple[Layer3LLMJudge, MagicMock]:
        llm_mock = MagicMock()
        llm_mock.complete.return_value = llm_response
        return Layer3LLMJudge(llm_adapter=llm_mock), llm_mock

    def test_no_golden_samples_returns_medium(self):
        judge, _ = self._make_judge("irrelevant")
        fp = make_fingerprint(samples=[])
        result = judge.check("test output", fp, make_context())
        assert result.level == ScoreLevel.MEDIUM
        assert "Golden Samples" in result.details

    def test_passt_returns_high(self):
        judge, _ = self._make_judge("Gute Begründung.\nPASST")
        fp = make_fingerprint([("Frage", "Antwort")])
        result = judge.check("test output", fp, make_context())
        assert result.level == ScoreLevel.HIGH

    def test_passt_nicht_returns_low(self):
        judge, _ = self._make_judge("Schlechte Begründung.\nPASST NICHT")
        fp = make_fingerprint([("Frage", "Antwort")])
        result = judge.check("test output", fp, make_context())
        assert result.level == ScoreLevel.LOW

    def test_details_contain_reasoning(self):
        judge, _ = self._make_judge("Der Stil passt gut.\nPASST")
        fp = make_fingerprint([("Frage", "Antwort")])
        result = judge.check("test output", fp, make_context())
        assert "PASST" in result.details
        assert "Der Stil passt gut" in result.details

    def test_llm_called_with_samples_in_prompt(self):
        judge, llm_mock = self._make_judge("PASST")
        fp = make_fingerprint([("Meine Frage", "Meine Antwort")])
        judge.check("output", fp, make_context())
        call_args = llm_mock.complete.call_args[0][0]
        prompt_text = call_args[0]["content"]
        assert "Meine Antwort" in prompt_text

    def test_max_5_samples_in_prompt(self):
        judge, llm_mock = self._make_judge("PASST")
        # 7 Samples geben, nur 5 sollen im Prompt landen
        samples = [(f"Q{i}", f"A{i}") for i in range(7)]
        fp = make_fingerprint(samples)
        judge.check("output", fp, make_context())
        prompt_text = llm_mock.complete.call_args[0][0][0]["content"]
        assert "A5" not in prompt_text   # Sample 6 nicht drin
        assert "A4" in prompt_text       # Sample 5 noch drin
