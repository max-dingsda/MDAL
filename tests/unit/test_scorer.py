"""Unit-Tests für das Scoring-Modell — alle Pfade der Entscheidungstabelle."""

import pytest

from mdal.interfaces.scoring import CheckResult, ScoreLevel, ScoringDecision
from mdal.verification.semantic.scorer import ScoringEngine


def r(level: ScoreLevel) -> CheckResult:
    return CheckResult(level=level)


HIGH   = ScoreLevel.HIGH
MEDIUM = ScoreLevel.MEDIUM
LOW    = ScoreLevel.LOW


class TestScoringEngine:
    """
    Vollständige Abdeckung der Entscheidungstabelle aus der Architekturskizze.
    Diese Tests sind gleichzeitig Regressionstests — die Tabelle darf sich nicht
    ohne explizite Entscheidung ändern.
    """

    def setup_method(self):
        self.scorer = ScoringEngine()

    # --- S1 OR S2 is LOW → REFINEMENT ---

    def test_s1_low_s2_high_gives_refinement(self):
        assert self.scorer.decide(r(LOW), r(HIGH)) == ScoringDecision.REFINEMENT

    def test_s1_high_s2_low_gives_refinement(self):
        assert self.scorer.decide(r(HIGH), r(LOW)) == ScoringDecision.REFINEMENT

    def test_s1_low_s2_medium_gives_refinement(self):
        assert self.scorer.decide(r(LOW), r(MEDIUM)) == ScoringDecision.REFINEMENT

    def test_s1_medium_s2_low_gives_refinement(self):
        assert self.scorer.decide(r(MEDIUM), r(LOW)) == ScoringDecision.REFINEMENT

    def test_s1_low_s2_low_gives_refinement(self):
        assert self.scorer.decide(r(LOW), r(LOW)) == ScoringDecision.REFINEMENT

    # --- S1 AND S2 HIGH → OUTPUT ---

    def test_s1_high_s2_high_gives_output(self):
        assert self.scorer.decide(r(HIGH), r(HIGH)) == ScoringDecision.OUTPUT

    # --- S1 OR S2 HIGH, andere MEDIUM → TRANSFORM ---

    def test_s1_high_s2_medium_gives_transform(self):
        assert self.scorer.decide(r(HIGH), r(MEDIUM)) == ScoringDecision.TRANSFORM

    def test_s1_medium_s2_high_gives_transform(self):
        assert self.scorer.decide(r(MEDIUM), r(HIGH)) == ScoringDecision.TRANSFORM

    # --- S1 AND S2 MEDIUM → TIEBREAK ---

    def test_s1_medium_s2_medium_gives_tiebreak(self):
        assert self.scorer.decide(r(MEDIUM), r(MEDIUM)) == ScoringDecision.TIEBREAK

    # --- Nach Tiebreak ---

    def test_tiebreak_passed_gives_transform(self):
        assert self.scorer.decide_after_tiebreak(True) == ScoringDecision.TRANSFORM

    def test_tiebreak_failed_gives_refinement(self):
        assert self.scorer.decide_after_tiebreak(False) == ScoringDecision.REFINEMENT
