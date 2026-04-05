"""
Verification Engine — Orchestrierung der vollständigen Prüfpipeline (F1, F2, F6, F18).

Ablauf:
  1. Betriebsmodus prüfen: welche Checks sind aktiv? (F18)
  2. Format erkennen (detector)
  3. Aktive Checks ausführen:
     - Strukturprüfung (sofern aktiv und Output strukturiert)
     - Semantikprüfung (sofern aktiv): S1 + S2 parallel, S3 nur bei TIEBREAK
  4. Scoring-Entscheidung treffen
  5. Ergebnis zurückgeben

F6: Prüfung erfolgt ausschließlich auf vollständigen Outputs.
    Die Engine bekommt immer den fertigen Output — kein Streaming-Eingriff.

F18: Einzelne Prüfungen deaktivierbar; beide gleichzeitig nie abschaltbar
     (wird in config.py sichergestellt).

Parallelisierung: S1 und S2 laufen parallel via ThreadPoolExecutor.
S3 nur on-demand bei TIEBREAK.
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
    """Vollständiges Ergebnis eines Prüfdurchlaufs."""
    decision:         ScoringDecision
    structure_result: StructureCheckResult | None  # None wenn nicht aktiv/nicht strukturiert
    semantic_s1:      CheckResult | None            # None wenn semantic nicht aktiv
    semantic_s2:      CheckResult | None
    semantic_s3:      CheckResult | None            # None wenn kein TIEBREAK nötig
    output_format:    str                           # "json" | "xml" | "prose"

    @property
    def passed(self) -> bool:
        """Kein Refinement nötig — Output kann direkt (oder nach Transform) ausgegeben werden."""
        return self.decision in (ScoringDecision.OUTPUT, ScoringDecision.TRANSFORM)

    @property
    def needs_transform(self) -> bool:
        return self.decision == ScoringDecision.TRANSFORM

    def error_summary(self) -> str:
        """Fehlerbericht für den Refinement-Prompt ans LLM."""
        parts: list[str] = []
        if self.structure_result and not self.structure_result.passed:
            parts.append(f"Strukturfehler: {self.structure_result.error_report}")
        if self.semantic_s1 and self.semantic_s1.level == ScoreLevel.LOW:
            parts.append(f"Stilregel-Verletzung: {self.semantic_s1.details}")
        if self.semantic_s2 and self.semantic_s2.level == ScoreLevel.LOW:
            parts.append(f"Stil-Abweichung (Embedding): {self.semantic_s2.details}")
        if self.semantic_s3 and self.semantic_s3.level == ScoreLevel.LOW:
            parts.append(f"Stil-Abweichung (Judge): {self.semantic_s3.details}")
        return "; ".join(parts) if parts else ""


class VerificationEngine:
    """
    Orchestriert den vollständigen Prüfdurchlauf für einen LLM-Output.

    Wird einmal pro System-Instanz angelegt — alle Abhängigkeiten per Constructor.
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
        Führt alle aktiven Prüfungen durch und gibt eine Entscheidung zurück.

        F6: output muss vollständig sein — keine Streaming-Fragmente.
        """
        detected = detect_format(output)
        fmt      = detected.format.value

        # --- Strukturprüfung ---
        structure_result: StructureCheckResult | None = None
        if self._checks.structure and detected.is_structured():
            structure_result = self._structure.check(output, detected)
            if not structure_result.passed:
                # Strukturfehler → sofort REFINEMENT, kein Semantic-Check nötig
                return VerificationResult(
                    decision=ScoringDecision.REFINEMENT,
                    structure_result=structure_result,
                    semantic_s1=None,
                    semantic_s2=None,
                    semantic_s3=None,
                    output_format=fmt,
                )
            
            # WEICHE (F2): Wenn das Format JSON oder XML ist und die Strukturprüfung bestanden wurde,
            # wird die Semantikprüfung komplett übersprungen!
            return VerificationResult(
                decision=ScoringDecision.OUTPUT,
                structure_result=structure_result,
                semantic_s1=None,
                semantic_s2=None,
                semantic_s3=None,
                output_format=fmt,
            )

        # --- Semantikprüfung ---
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
            # Nur Strukturprüfung aktiv (F18) — semantisch unklar → OUTPUT
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
        Führt Layer 1 und Layer 2 parallel aus.
        Layer 2 macht einen Netzwerkaufruf (Embedding-API) — Parallelisierung
        hält die Latenz unter der Summe beider Einzelaufrufe.
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(self._layer1.check, output, fingerprint, context)
            f2 = pool.submit(self._layer2.check, output, fingerprint, context)
            s1 = f1.result()
            s2 = f2.result()
        return s1, s2
