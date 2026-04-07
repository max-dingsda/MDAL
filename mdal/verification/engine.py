"""
Verification Engine — orchestration of the complete verification pipeline (F1, F2, F6, F18).

Flow:
  1. Check operating mode: which checks are active? (F18)
  2. Detect format (detector)
  3. Run active checks:
     - Structure check (if active and output is structured)
     - Semantic check (if active): S1 + S2 in parallel, S3 only for TIEBREAK
  4. Make scoring decision
  5. Return result

F6: Verification runs exclusively on complete outputs.
    The engine always receives the finished output — no streaming intervention.

F18: Individual checks can be deactivated; both can never be disabled simultaneously
     (enforced in config.py).

Parallelization: S1 and S2 run in parallel via ThreadPoolExecutor.
S3 only on demand for TIEBREAK.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass

from mdal.config import ChecksConfig
from mdal.fingerprint.models import Fingerprint
from mdal.interfaces.scoring import (
    CheckResult,
    ScoreLevel,
    ScoringDecision,
    StructureCheckResult,
)
from mdal.plugins.registry import PluginRegistry
from mdal.session import SessionContext
from mdal.verification.detector import detect_format
from mdal.verification.semantic.layer1 import Layer1RuleChecker
from mdal.verification.semantic.layer2 import Layer2EmbeddingChecker
from mdal.verification.semantic.layer3 import Layer3LLMJudge
from mdal.verification.semantic.scorer import ScoringEngine
from mdal.verification.structure import StructureChecker


@dataclass
class VerificationResult:
    """Complete result of a verification pass."""
    decision:         ScoringDecision
    structure_result: StructureCheckResult | None  # None if not active / not structured
    semantic_s1:      CheckResult | None            # None if semantic not active
    semantic_s2:      CheckResult | None
    semantic_s3:      CheckResult | None            # None if no TIEBREAK needed
    output_format:    str                           # "json" | "xml" | "prose"

    @property
    def passed(self) -> bool:
        """No refinement needed — output can be delivered directly (or after transform)."""
        return self.decision in (ScoringDecision.OUTPUT, ScoringDecision.TRANSFORM)

    @property
    def needs_transform(self) -> bool:
        return self.decision == ScoringDecision.TRANSFORM

    def error_summary(self) -> str:
        """Error report for the refinement prompt sent to the LLM."""
        parts: list[str] = []
        if self.structure_result and not self.structure_result.passed:
            parts.append(f"Structure error: {self.structure_result.error_report}")
        if self.semantic_s1 and self.semantic_s1.level == ScoreLevel.LOW:
            parts.append(f"Style rule violation: {self.semantic_s1.details}")
        if self.semantic_s2 and self.semantic_s2.level == ScoreLevel.LOW:
            parts.append(f"Style deviation (embedding): {self.semantic_s2.details}")
        if self.semantic_s3 and self.semantic_s3.level == ScoreLevel.LOW:
            parts.append(f"Style deviation (judge): {self.semantic_s3.details}")
        return "; ".join(parts) if parts else ""


class VerificationEngine:
    """
    Orchestrates the complete verification pass for an LLM output.

    Created once per system instance — all dependencies via constructor.
    """

    def __init__(
        self,
        checks:    ChecksConfig,
        registry:  PluginRegistry,
        layer1:    Layer1RuleChecker,
        layer2:    Layer2EmbeddingChecker,
        layer3:    Layer3LLMJudge,
        scorer:    ScoringEngine,
    ) -> None:
        self._checks   = checks
        self._structure = StructureChecker(registry)
        self._layer1   = layer1
        self._layer2   = layer2
        self._layer3   = layer3
        self._scorer   = scorer

    def verify(
        self,
        output:      str,
        fingerprint: Fingerprint,
        context:     SessionContext,
    ) -> VerificationResult:
        """
        Runs all active checks and returns a decision.

        F6: output must be complete — no streaming fragments.
        """
        detected = detect_format(output)
        fmt      = detected.format.value

        # --- Structure check ---
        structure_result: StructureCheckResult | None = None
        if self._checks.structure and detected.is_structured():
            structure_result = self._structure.check(output, detected)
            if not structure_result.passed:
                # Structure error → immediately REFINEMENT, no semantic check needed
                return VerificationResult(
                    decision=ScoringDecision.REFINEMENT,
                    structure_result=structure_result,
                    semantic_s1=None,
                    semantic_s2=None,
                    semantic_s3=None,
                    output_format=fmt,
                )

            # SWITCH (F2): if the format is JSON or XML and structure check passed,
            # semantic check is skipped entirely.
            return VerificationResult(
                decision=ScoringDecision.OUTPUT,
                structure_result=structure_result,
                semantic_s1=None,
                semantic_s2=None,
                semantic_s3=None,
                output_format=fmt,
            )

        # --- Semantic check ---
        s1: CheckResult | None = None
        s2: CheckResult | None = None
        s3: CheckResult | None = None

        if self._checks.semantic and not detected.is_structured():
            s1, s2 = self._run_semantic_parallel(output, fingerprint, context)
            decision = self._scorer.decide(s1, s2)

            if decision == ScoringDecision.TIEBREAK:
                s3 = self._layer3.check(output, fingerprint, context)
                tiebreak_passed = s3.level == ScoreLevel.HIGH
                decision = self._scorer.decide_after_tiebreak(tiebreak_passed)
        else:
            # Only structure check active (F18) — semantically unclear → OUTPUT
            decision = ScoringDecision.OUTPUT

        result = VerificationResult(
            decision=decision,
            structure_result=structure_result,
            semantic_s1=s1,
            semantic_s2=s2,
            semantic_s3=s3,
            output_format=fmt,
        )
        context.record_check(s1 or CheckResult(level=ScoreLevel.HIGH))
        return result

    def _run_semantic_parallel(
        self,
        output:      str,
        fingerprint: Fingerprint,
        context:     SessionContext,
    ) -> tuple[CheckResult, CheckResult]:
        """
        Runs Layer 1 and Layer 2 in parallel.
        Layer 2 makes a network call (embedding API) — parallelization
        keeps latency below the sum of both individual calls.
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(self._layer1.check, output, fingerprint, context)
            f2 = pool.submit(self._layer2.check, output, fingerprint, context)
            s1 = f1.result()
            s2 = f2.result()
        return s1, s2
