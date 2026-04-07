"""
Regression tests for the scoring model.

Table-driven from scorer_decisions.json — the decision table
from the architecture sketch must not change without an explicit decision.
"""

import json
from pathlib import Path

import pytest

from mdal.interfaces.scoring import CheckResult, ScoreLevel, ScoringDecision
from mdal.verification.semantic.scorer import ScoringEngine

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "scorer_decisions.json").read_text(encoding="utf-8")
)

LEVEL_MAP = {
    "low":    ScoreLevel.LOW,
    "medium": ScoreLevel.MEDIUM,
    "high":   ScoreLevel.HIGH,
}

DECISION_MAP = {
    "output":     ScoringDecision.OUTPUT,
    "transform":  ScoringDecision.TRANSFORM,
    "refinement": ScoringDecision.REFINEMENT,
    "tiebreak":   ScoringDecision.TIEBREAK,
}


@pytest.mark.parametrize(
    "case",
    FIXTURES,
    ids=[f["note"] for f in FIXTURES],
)
def test_scoring_decision(case: dict) -> None:
    scorer   = ScoringEngine()
    s1       = CheckResult(level=LEVEL_MAP[case["s1"]])
    s2       = CheckResult(level=LEVEL_MAP[case["s2"]])
    expected = DECISION_MAP[case["expected"]]
    assert scorer.decide(s1, s2) == expected, (
        f"Expected {expected} for S1={case['s1']}, S2={case['s2']} — {case['note']}"
    )
