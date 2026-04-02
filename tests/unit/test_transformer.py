"""Unit-Tests für RuleBasedToneTransformer."""

import pytest

from mdal.fingerprint.models import (
    EmbeddingProfile, Fingerprint, GoldenSamples, StyleRules,
)
from mdal.transformer import RuleBasedToneTransformer, _normalize_whitespace, _replace_word


def make_fingerprint(rules: StyleRules) -> Fingerprint:
    return Fingerprint(
        version=1, language="de",
        layer1=rules,
        layer2=EmbeddingProfile(centroid=[0.5], model_name="test", sample_count=1, dimensions=1),
        layer3=GoldenSamples(samples=[]),
    )


class TestRuleBasedToneTransformer:
    def setup_method(self):
        self.t = RuleBasedToneTransformer()

    # --- Avoided vocabulary ---

    def test_avoided_word_removed(self):
        rules = StyleRules(formality_level=1, avoided_vocabulary=["halt"])
        fp    = make_fingerprint(rules)
        result = self.t.transform("Das ist halt so.", fp)
        assert "halt" not in result.lower()

    def test_multiple_avoided_words_all_removed(self):
        rules = StyleRules(formality_level=1, avoided_vocabulary=["halt", "irgendwie"])
        fp    = make_fingerprint(rules)
        result = self.t.transform("Das ist halt irgendwie nicht gut.", fp)
        assert "halt" not in result.lower()
        assert "irgendwie" not in result.lower()

    def test_avoided_word_case_insensitive(self):
        rules = StyleRules(formality_level=1, avoided_vocabulary=["Halt"])
        fp    = make_fingerprint(rules)
        result = self.t.transform("Das ist halt so.", fp)
        assert "halt" not in result.lower()

    def test_empty_avoided_vocabulary_returns_unchanged(self):
        rules  = StyleRules(formality_level=3, avoided_vocabulary=[])
        fp     = make_fingerprint(rules)
        text   = "Die Analyse zeigt ein klares Ergebnis."
        result = self.t.transform(text, fp)
        # Formality=3 → informal substitutions aktiv; kein Wort hier informal
        assert "Analyse" in result
        assert "Ergebnis" in result

    def test_avoided_word_not_replaced_inside_other_word(self):
        # "ok" darf in "Token" nicht ersetzt werden
        rules  = StyleRules(formality_level=1, avoided_vocabulary=["ok"])
        fp     = make_fingerprint(rules)
        result = self.t.transform("Das ist ein Token.", fp)
        assert "Token" in result

    # --- Formality substitutions ---

    def test_informal_filler_removed_at_high_formality(self):
        rules  = StyleRules(formality_level=4)
        fp     = make_fingerprint(rules)
        result = self.t.transform("Das funktioniert quasi irgendwie gut.", fp)
        # "quasi" wird durch "im Wesentlichen" ersetzt, "irgendwie" entfernt
        assert "irgendwie" not in result.lower()

    def test_informal_filler_kept_at_low_formality(self):
        # Formality < threshold → keine automatischen Substitutionen
        rules  = StyleRules(formality_level=1)
        fp     = make_fingerprint(rules)
        result = self.t.transform("Das ist super.", fp)
        # "super" bleibt, weil formality=1 < threshold=3
        assert "super" in result.lower()

    def test_okay_replaced_by_in_ordnung(self):
        rules  = StyleRules(formality_level=3)
        fp     = make_fingerprint(rules)
        result = self.t.transform("Das ist okay für den Moment.", fp)
        assert "okay" not in result.lower()
        assert "in Ordnung" in result

    # --- Whitespace normalization ---

    def test_double_spaces_collapsed(self):
        rules  = StyleRules(formality_level=3, avoided_vocabulary=["halt"])
        fp     = make_fingerprint(rules)
        result = self.t.transform("Das  ist  halt  so.", fp)
        assert "  " not in result

    def test_space_before_punctuation_removed(self):
        rules  = StyleRules(formality_level=3, avoided_vocabulary=["halt"])
        fp     = make_fingerprint(rules)
        result = self.t.transform("Das ist halt .", fp)
        assert " ." not in result

    # --- Structure preservation ---

    def test_multiline_structure_preserved(self):
        rules  = StyleRules(formality_level=3, avoided_vocabulary=["halt"])
        fp     = make_fingerprint(rules)
        text   = "Erste Zeile.\nhalt etwas.\nDritte Zeile."
        result = self.t.transform(text, fp)
        lines  = result.split("\n")
        assert len(lines) == 3

    def test_no_content_added(self):
        rules  = StyleRules(formality_level=5)
        fp     = make_fingerprint(rules)
        text   = "Die Analyse zeigt ein Ergebnis."
        result = self.t.transform(text, fp)
        # Kein Satz hinzugefügt — Ausgabe darf nur kürzer oder gleich lang sein
        assert len(result) <= len(text) + 50  # +50 für mögliche Ersetzungen


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

class TestReplaceWord:
    def test_basic_replacement(self):
        assert _replace_word("Das ist halt so.", "halt", "") == "Das ist  so."

    def test_word_boundary_respected(self):
        assert _replace_word("Das Token ist ok.", "ok", "") == "Das Token ist ."

    def test_case_insensitive(self):
        result = _replace_word("Das ist HALT so.", "halt", "")
        assert "HALT" not in result

    def test_replacement_string_used(self):
        result = _replace_word("Das ist super.", "super", "sehr gut")
        assert "sehr gut" in result


class TestNormalizeWhitespace:
    def test_double_space_collapsed(self):
        assert _normalize_whitespace("a  b") == "a b"

    def test_space_before_comma_removed(self):
        assert _normalize_whitespace("a ,b") == "a,b"

    def test_leading_trailing_stripped(self):
        assert _normalize_whitespace("  text  ") == "text"

    def test_no_change_needed(self):
        assert _normalize_whitespace("Normal text.") == "Normal text."
