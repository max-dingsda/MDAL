"""
Scoring and check interfaces — interfaces for future Rust extraction.

The scoring logic (Layer 1, Layer 2, decision cascade) is the most
computationally intensive part of MDAL and the primary candidate for the Rust core.
These protocols define the boundaries between the Python runtime and the Rust core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mdal.fingerprint.models import Fingerprint
    from mdal.session import SessionContext


class ScoreLevel(str, Enum):
    """Three-level rating scale for semantic checker results."""
    LOW    = "low"     # Clear deviation → refinement
    MEDIUM = "medium"  # Grey area → transformer or tiebreaker
    HIGH   = "high"    # Conforming → output or minor transformation


class ScoringDecision(str, Enum):
    """Decision of the scoring model after evaluating all active layers."""
    OUTPUT      = "output"      # Pass output directly
    TRANSFORM   = "transform"   # Apply tone transformer, then output
    REFINEMENT  = "refinement"  # Return output to LLM (counts as retry)
    TIEBREAK    = "tiebreak"    # Layer 3 (LLM-as-Judge) is required


@dataclass
class CheckResult:
    """Result of a single semantic checker layer."""
    level:   ScoreLevel
    details: str = ""
    # Raw similarity score (0.0–1.0) — for threshold calibration
    raw_score: float | None = None


@dataclass
class StructureCheckResult:
    """Result of the structure check (F2). Binary — no grey levels."""
    passed:       bool
    error_report: str = ""
    # Which validation stage produced the error
    failed_at:    str | None = None  # "xsd" | "elements" | None


@runtime_checkable
class SemanticCheckerProtocol(Protocol):
    """
    Interface for a single layer of the semantic evaluator cascade.
    Implementations: Layer1RuleChecker, Layer2EmbeddingChecker, Layer3LLMJudge.
    Layers 1 and 2 → Rust core; Layer 3 stays in Python (LLM calls).
    """

    def check(
        self,
        output: str,
        fingerprint: Fingerprint,
        context: SessionContext,
    ) -> CheckResult:
        """
        Evaluates an LLM output against the fingerprint.
        Must be deterministic (Layer 1) or reproducible (Layer 2).
        """
        ...


@runtime_checkable
class ScoringEngineProtocol(Protocol):
    """
    Decision logic: takes results from all active layers and
    returns a ScoringDecision.

    Decision table (from architecture sketch):
    S1 OR S2 low               → REFINEMENT
    S1 AND S2 high             → OUTPUT
    S1 OR S2 high, other med   → TRANSFORM
    S1 AND S2 medium           → TIEBREAK (→ Layer 3)
    After S3 "matches"         → TRANSFORM
    After S3 "does not match"  → REFINEMENT

    → Rust core (target architecture)
    """

    def decide(self, s1: CheckResult, s2: CheckResult) -> ScoringDecision:
        ...

    def decide_after_tiebreak(self, tiebreak_passed: bool) -> ScoringDecision:
        ...
