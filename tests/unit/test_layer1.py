"""Unit tests for Semantic Layer 1 — rule-based checker."""

import pytest

from mdal.fingerprint.models import (
    EmbeddingProfile, Fingerprint, GoldenSamples, StyleRule, StyleRules,
)
from mdal.interfaces.scoring import ScoreLevel
from mdal.session import SessionContext
from mdal.verification.semantic.layer1 import (
    Layer1RuleChecker, _avg_sentence_length, _estimate_formality, _weakest,
)


def make_fingerprint(rules: StyleRules) -> Fingerprint:
    return Fingerprint(
        version=1, language="de",
        layer1=rules,
        layer2=EmbeddingProfile(centroid=[0.5], model_name="test", sample_count=1, dimensions=1),
        layer3=GoldenSamples(samples=[]),
    )


def make_context() -> SessionContext:
    return SessionContext(language="de", fingerprint_version=1)


class TestLayer1RuleChecker:
    def test_avoided_vocabulary_found_gives_low(self):
        rules = StyleRules(
            formality_level=3,
            avoided_vocabulary=["halt", "irgendwie"],
        )
        checker = Layer1RuleChecker()
        result = checker.check(
            "Das ist halt irgendwie nicht so gut.",
            make_fingerprint(rules),
            make_context(),
        )
        assert result.level == ScoreLevel.LOW

    def test_no_avoided_vocabulary_found_gives_high(self):
        rules = StyleRules(
            formality_level=3,
            preferred_vocabulary=[],
            avoided_vocabulary=["halt", "irgendwie"],
        )
        checker = Layer1RuleChecker()
        # sentence with ~10 words → formality ≈ 3 (matches the configuration)
        result = checker.check(
            "Die vorliegende Analyse zeigt ein klar erkennbares und nachvollziehbares Ergebnis.",
            make_fingerprint(rules),
            make_context(),
        )
        # Avoided vocab: none found → no LOW from vocabulary check
        assert result.level != ScoreLevel.LOW

    def test_preferred_vocabulary_present_contributes_high(self):
        rules = StyleRules(
            formality_level=3,
            preferred_vocabulary=["präzise", "strukturiert", "klar"],
            avoided_vocabulary=[],
        )
        checker = Layer1RuleChecker()
        result = checker.check(
            "Die Analyse ist präzise und strukturiert und klar formuliert.",
            make_fingerprint(rules),
            make_context(),
        )
        assert result.level in (ScoreLevel.HIGH, ScoreLevel.MEDIUM)

    def test_no_preferred_vocabulary_found_gives_medium(self):
        rules = StyleRules(
            formality_level=3,
            preferred_vocabulary=["präzise", "strukturiert"],
            avoided_vocabulary=[],
        )
        checker = Layer1RuleChecker()
        result = checker.check(
            "Hier ist die Antwort auf deine Frage.",
            make_fingerprint(rules),
            make_context(),
        )
        # Preferred vocab not found → at most MEDIUM
        assert result.level in (ScoreLevel.MEDIUM, ScoreLevel.LOW)

    def test_empty_rules_gives_medium_or_high(self):
        """Without vocabulary config, Layer 1 only checks formality — text must match expectation."""
        rules = StyleRules(formality_level=3)
        checker = Layer1RuleChecker()
        # sentence with ~10-12 words → formality heuristic yields ≈ 3
        result = checker.check(
            "Die Ergebnisse der Analyse lassen eine klare Schlussfolgerung zu.",
            make_fingerprint(rules),
            make_context(),
        )
        assert result.level in (ScoreLevel.HIGH, ScoreLevel.MEDIUM)

    def test_sentence_length_too_long_gives_penalty(self):
        rules = StyleRules(
            formality_level=3,
            avg_sentence_length_max=5,
        )
        long_sentence = "Dies ist ein sehr langer Satz der weit über die erlaubte Wortanzahl hinausgeht und definitiv zu lang ist."
        checker = Layer1RuleChecker()
        result = checker.check(long_sentence, make_fingerprint(rules), make_context())
        # sentence is clearly too long → LOW or MEDIUM
        assert result.level in (ScoreLevel.LOW, ScoreLevel.MEDIUM)

    def test_result_contains_details(self):
        rules = StyleRules(
            formality_level=3,
            avoided_vocabulary=["halt"],
        )
        checker = Layer1RuleChecker()
        result = checker.check(
            "Das ist halt so.",
            make_fingerprint(rules),
            make_context(),
        )
        assert result.details != ""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestAvgSentenceLength:
    def test_single_sentence(self):
        length = _avg_sentence_length("Eins zwei drei vier fünf.")
        assert length == pytest.approx(5.0)

    def test_multiple_sentences(self):
        length = _avg_sentence_length("Ein zwei. Drei vier fünf sechs.")
        assert length == pytest.approx(3.0)

    def test_empty_string(self):
        assert _avg_sentence_length("") == 0.0


class TestEstimateFormality:
    def test_very_short_sentences_give_informal(self):
        text = "Ok. Ja. Klar. Super."
        level = _estimate_formality(text)
        assert level <= 2

    def test_long_formal_sentences_give_formal(self):
        text = (
            "Gemäß den vorliegenden Unterlagen ergibt sich folglich eine "
            "nachvollziehbare Schlussfolgerung hinsichtlich der dargestellten "
            "Sachverhalte und deren Implikationen."
        )
        level = _estimate_formality(text)
        assert level >= 4

    def test_informal_words_lower_score(self):
        text_clean    = "Die Ergebnisse zeigen eine klare Tendenz."
        text_informal = "Die Ergebnisse zeigen irgendwie eine klare Tendenz, okay."
        assert _estimate_formality(text_clean) >= _estimate_formality(text_informal)


class TestWeakest:
    def test_single_low(self):
        assert _weakest([ScoreLevel.LOW]) == ScoreLevel.LOW

    def test_low_wins_over_high(self):
        assert _weakest([ScoreLevel.HIGH, ScoreLevel.LOW]) == ScoreLevel.LOW

    def test_medium_wins_over_high(self):
        assert _weakest([ScoreLevel.HIGH, ScoreLevel.MEDIUM]) == ScoreLevel.MEDIUM

    def test_all_high(self):
        assert _weakest([ScoreLevel.HIGH, ScoreLevel.HIGH]) == ScoreLevel.HIGH
