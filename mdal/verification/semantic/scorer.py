"""
Scoring model — decision cascade (ScoringEngineProtocol).

Implements the decision table from the architecture sketch exactly:

  S1 OR  S2 low              → REFINEMENT
  S1 AND S2 high             → OUTPUT
  S1 OR  S2 high, other med  → TRANSFORM
  S1 AND S2 medium           → TIEBREAK (→ Layer 3)
  After S3 "matches"         → TRANSFORM
  After S3 "does not match"  → REFINEMENT

The system makes binary decisions externally.
Internally the checks work with severity levels because embeddings produce
similarity scores, not yes/no answers.

→ Rust core (target architecture): pure decision logic without IO.
"""

from __future__ import annotations

from mdal.interfaces.scoring import CheckResult, ScoreLevel, ScoringDecision


class ScoringEngine:
    """Implements ScoringEngineProtocol."""

    def decide(self, s1: CheckResult, s2: CheckResult) -> ScoringDecision:
        """
        Makes a decision based on the results of Layer 1 and 2.

        Decision table (from architecture sketch):
          S1 OR  S2 is LOW               → REFINEMENT
          S1 AND S2 both HIGH            → OUTPUT
          S1 OR  S2 HIGH, other MEDIUM   → TRANSFORM
          S1 AND S2 both MEDIUM          → TIEBREAK
        """
        l1, l2 = s1.level, s2.level

        # Clear deviation
        if l1 == ScoreLevel.LOW or l2 == ScoreLevel.LOW:
            return ScoringDecision.REFINEMENT

        # Both conforming
        if l1 == ScoreLevel.HIGH and l2 == ScoreLevel.HIGH:
            return ScoringDecision.OUTPUT

        # Minor deviation: one HIGH, one MEDIUM
        if (l1 == ScoreLevel.HIGH and l2 == ScoreLevel.MEDIUM) or \
           (l1 == ScoreLevel.MEDIUM and l2 == ScoreLevel.HIGH):
            return ScoringDecision.TRANSFORM

        # Grey area: both MEDIUM → tiebreaker
        if l1 == ScoreLevel.MEDIUM and l2 == ScoreLevel.MEDIUM:
            return ScoringDecision.TIEBREAK

        # Should not be reachable, but defensive fallback:
        return ScoringDecision.REFINEMENT

    def decide_after_tiebreak(self, tiebreak_passed: bool) -> ScoringDecision:
        """
        Decision after Layer 3 (LLM-as-Judge):
          S3 "matches"         → TRANSFORM (grey area rated as medium)
          S3 "does not match"  → REFINEMENT
        """
        return ScoringDecision.TRANSFORM if tiebreak_passed else ScoringDecision.REFINEMENT
