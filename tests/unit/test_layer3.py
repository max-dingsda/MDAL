"""Unit tests for Semantic Layer 3 — LLM-as-Judge (CR-Finding #5: CoT format)."""

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
# _parse_judgment — CoT format (verdict on last line)
# ---------------------------------------------------------------------------

class TestParseJudgment:
    def test_matches_alone(self):
        assert _parse_judgment("MATCHES") is True

    def test_does_not_match_alone(self):
        assert _parse_judgment("DOES NOT MATCH") is False

    def test_cot_matches_last_line(self):
        response = (
            "The text uses a factual, structured style.\n"
            "MATCHES"
        )
        assert _parse_judgment(response) is True

    def test_cot_does_not_match_last_line(self):
        response = (
            "The text is too informal and uses colloquial language.\n"
            "DOES NOT MATCH"
        )
        assert _parse_judgment(response) is False

    def test_lowercase_matches(self):
        assert _parse_judgment("matches") is True

    def test_lowercase_does_not_match(self):
        assert _parse_judgment("does not match") is False

    def test_multiline_cot_matches(self):
        response = (
            "The style is formal and corresponds to the reference level.\n"
            "The sentence structure and vocabulary fit well with the examples.\n"
            "MATCHES"
        )
        assert _parse_judgment(response) is True

    def test_empty_response_returns_false(self):
        assert _parse_judgment("") is False

    def test_unclear_response_returns_false(self):
        assert _parse_judgment("I am not sure.") is False

    def test_whitespace_around_verdict(self):
        assert _parse_judgment("  MATCHES  ") is True
        assert _parse_judgment("  DOES NOT MATCH  ") is False

    def test_does_not_match_wins_over_matches(self):
        # If both "MATCHES" and "DOES NOT MATCH" appear in the text:
        # last line wins
        response = "Some sections match partially.\nDOES NOT MATCH"
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
        assert "golden samples" in result.details.lower()

    def test_matches_returns_high(self):
        judge, _ = self._make_judge("Good reasoning.\nMATCHES")
        fp = make_fingerprint([("Question", "Answer")])
        result = judge.check("test output", fp, make_context())
        assert result.level == ScoreLevel.HIGH

    def test_does_not_match_returns_low(self):
        judge, _ = self._make_judge("Poor reasoning.\nDOES NOT MATCH")
        fp = make_fingerprint([("Question", "Answer")])
        result = judge.check("test output", fp, make_context())
        assert result.level == ScoreLevel.LOW

    def test_details_contain_reasoning(self):
        judge, _ = self._make_judge("The style fits well.\nMATCHES")
        fp = make_fingerprint([("Question", "Answer")])
        result = judge.check("test output", fp, make_context())
        assert "MATCHES" in result.details
        assert "The style fits well" in result.details

    def test_llm_called_with_samples_in_prompt(self):
        judge, llm_mock = self._make_judge("MATCHES")
        fp = make_fingerprint([("My question", "My answer")])
        judge.check("output", fp, make_context())
        call_args = llm_mock.complete.call_args[0][0]
        prompt_text = call_args[0]["content"]
        assert "My answer" in prompt_text

    def test_max_5_samples_in_prompt(self):
        judge, llm_mock = self._make_judge("MATCHES")
        # Provide 7 samples — only 5 should appear in the prompt
        samples = [(f"Q{i}", f"A{i}") for i in range(7)]
        fp = make_fingerprint(samples)
        judge.check("output", fp, make_context())
        prompt_text = llm_mock.complete.call_args[0][0][0]["content"]
        assert "A5" not in prompt_text   # sample 6 not included
        assert "A4" in prompt_text       # sample 5 still included
