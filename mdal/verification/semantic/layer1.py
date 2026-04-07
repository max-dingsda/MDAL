"""
Semantic Layer 1 — rule-based checker (SemanticCheckerProtocol).

Fast and deterministic. Checks measurable style properties from the fingerprint:
  - Formality level (heuristic: sentence length, vocabulary indicators)
  - Preferred vocabulary (preferred_vocabulary)
  - Avoided vocabulary (avoided_vocabulary)

PoC limitations:
  The formality heuristic is a first approach for validation.
  Thresholds and weights are deliberately kept observable (NF9).
  Goal: determine whether this approach is viable (one of the 4 PoC questions).

→ Rust core (target architecture): rule-based matching without LLM overhead.
"""

from __future__ import annotations

import re

from mdal.fingerprint.models import Fingerprint
from mdal.interfaces.scoring import CheckResult, ScoreLevel
from mdal.session import SessionContext

# Formality heuristic: thresholds for sentence length (words)
_FORMAL_MIN_AVG_SENTENCE_WORDS = 12
_INFORMAL_MAX_AVG_SENTENCE_WORDS = 7

# Informal indicators (cross-language — for German/English)
_INFORMAL_PATTERNS = re.compile(
    r"\b(naja|okay|ok|jo|äh|ähm|hmm|halt|irgendwie|eigentlich|sozusagen"
    r"|btw|imho|fyi|yeah|yep|nope|gonna|wanna|gotta)\b",
    re.IGNORECASE,
)

# Formal indicators
_FORMAL_PATTERNS = re.compile(
    r"\b(gemäß|hinsichtlich|infolgedessen|diesbezüglich|folglich|mithin"
    r"|demnach|entsprechend|insbesondere|ferner|zudem|darüber hinaus"
    r"|pursuant|whereas|herewith|aforementioned|subsequently)\b",
    re.IGNORECASE,
)


class Layer1RuleChecker:
    """
    Implements SemanticCheckerProtocol via rule-based style checking.

    Scoring logic:
      Each enabled check produces a signal (pass/fail).
      The overall result is the weakest signal:
        - Avoided vocabulary found       → LOW  (immediately)
        - Formality strongly deviating   → LOW
        - No preferred terms found       → MEDIUM
        - Formality slightly deviating   → MEDIUM
        - Everything matches             → HIGH
    """

    def check(
        self,
        output: str,
        fingerprint: Fingerprint,
        context: SessionContext,
    ) -> CheckResult:
        rules  = fingerprint.layer1
        scores: list[ScoreLevel] = []
        notes:  list[str]        = []

        # --- Avoided vocabulary (F1: style normalization) ---
        if rules.avoided_vocabulary:
            found = [
                w for w in rules.avoided_vocabulary
                if re.search(rf"\b{re.escape(w)}\b", output, re.IGNORECASE)
            ]
            if found:
                scores.append(ScoreLevel.LOW)
                notes.append(f"Avoided vocabulary found: {found}")
            else:
                scores.append(ScoreLevel.HIGH)

        # --- Preferred vocabulary ---
        if rules.preferred_vocabulary:
            found = [
                w for w in rules.preferred_vocabulary
                if re.search(rf"\b{re.escape(w)}\b", output, re.IGNORECASE)
            ]
            ratio = len(found) / len(rules.preferred_vocabulary)
            if ratio >= 0.5:
                scores.append(ScoreLevel.HIGH)
            elif ratio > 0:
                scores.append(ScoreLevel.MEDIUM)
                notes.append(
                    f"Only {len(found)}/{len(rules.preferred_vocabulary)} "
                    f"preferred terms found."
                )
            else:
                scores.append(ScoreLevel.MEDIUM)
                notes.append("No preferred vocabulary found.")

        # --- Formality level ---
        estimated = _estimate_formality(output)
        expected  = rules.formality_level
        delta     = abs(estimated - expected)

        if delta == 0:
            scores.append(ScoreLevel.HIGH)
        elif delta == 1:
            scores.append(ScoreLevel.MEDIUM)
            notes.append(
                f"Formality: expected={expected}, estimated≈{estimated} (Δ=1)."
            )
        else:
            scores.append(ScoreLevel.LOW)
            notes.append(
                f"Formality strongly deviating: expected={expected}, estimated≈{estimated} (Δ={delta})."
            )

        # Sentence length check (if configured)
        if rules.avg_sentence_length_max is not None:
            avg_len = _avg_sentence_length(output)
            if avg_len > rules.avg_sentence_length_max * 1.5:
                scores.append(ScoreLevel.LOW)
                notes.append(
                    f"Average sentence length too high: "
                    f"{avg_len:.0f} words (max. {rules.avg_sentence_length_max})."
                )
            elif avg_len > rules.avg_sentence_length_max:
                scores.append(ScoreLevel.MEDIUM)

        # Weakest signal wins
        final = _weakest(scores) if scores else ScoreLevel.MEDIUM

        return CheckResult(
            level=final,
            details="; ".join(notes) if notes else "Rule check passed.",
        )


# ---------------------------------------------------------------------------
# Helper functions — formality heuristic
# ---------------------------------------------------------------------------

def _estimate_formality(text: str) -> int:
    """
    Estimates the formality level on a 1-5 scale.
    Heuristic: combination of sentence length and vocabulary indicators.
    For the PoC: observe whether this heuristic produces meaningful values.
    """
    avg_len = _avg_sentence_length(text)
    word_count = len(text.split())

    if word_count == 0:
        return 3

    informal_hits = len(_INFORMAL_PATTERNS.findall(text))
    formal_hits   = len(_FORMAL_PATTERNS.findall(text))

    # Raw value: sentence length as base (short=informal, long=formal)
    if avg_len <= _INFORMAL_MAX_AVG_SENTENCE_WORDS:
        base = 1
    elif avg_len <= 10:
        base = 2
    elif avg_len <= _FORMAL_MIN_AVG_SENTENCE_WORDS:
        base = 3
    elif avg_len <= 18:
        base = 4
    else:
        base = 5

    # Vocabulary adjustments
    adjustment = 0
    if informal_hits > 0:
        adjustment -= min(informal_hits, 2)
    if formal_hits > 0:
        adjustment += min(formal_hits, 1)

    return max(1, min(5, base + adjustment))


def _avg_sentence_length(text: str) -> float:
    """Average number of words per sentence."""
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0.0
    word_counts = [len(s.split()) for s in sentences]
    return sum(word_counts) / len(word_counts)


def _weakest(scores: list[ScoreLevel]) -> ScoreLevel:
    """Returns the weakest score level (LOW < MEDIUM < HIGH)."""
    order = {ScoreLevel.LOW: 0, ScoreLevel.MEDIUM: 1, ScoreLevel.HIGH: 2}
    return min(scores, key=lambda s: order[s])
