"""
Scoring- und Prüf-Interfaces — Nahtstellen für spätere Rust-Extraktion.

Die Scoring-Logik (Schicht 1, Schicht 2, Entscheidungskaskade) ist der
rechenintensivste Teil von MDAL und der primäre Kandidat für den Rust-Kern.
Diese Protokolle definieren die Grenzen zwischen Python-Laufzeit und Rust-Kern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mdal.fingerprint.models import Fingerprint
    from mdal.session import SessionContext


class ScoreLevel(str, Enum):
    """Dreistufige Bewertungsskala für Semantic-Checker-Ergebnisse."""
    LOW    = "low"     # Klare Abweichung → Refinement
    MEDIUM = "medium"  # Graubereich → ggf. Transformer oder Tiebreaker
    HIGH   = "high"    # Konform → Output oder leichte Transformation


class ScoringDecision(str, Enum):
    """Entscheidung des Scoring-Modells nach Auswertung aller aktiven Schichten."""
    OUTPUT      = "output"      # Output direkt durchleiten
    TRANSFORM   = "transform"   # Ton-Transformer anwenden, dann Output
    REFINEMENT  = "refinement"  # Output ans LLM zurückgeben (zählt als Retry)
    TIEBREAK    = "tiebreak"    # Schicht 3 (LLM-as-Judge) wird benötigt


@dataclass
class CheckResult:
    """Ergebnis einer einzelnen Semantic-Checker-Schicht."""
    level:   ScoreLevel
    details: str = ""
    # Rohwert des Ähnlichkeits-Scores (0.0–1.0) — für Schwellwert-Kalibrierung
    raw_score: float | None = None


@dataclass
class StructureCheckResult:
    """Ergebnis der Strukturprüfung (F2). Binär — keine Graustufen."""
    passed:       bool
    error_report: str = ""
    # Welche Validierungsstufe hat den Fehler produziert
    failed_at:    str | None = None  # "xsd" | "elements" | None


@runtime_checkable
class SemanticCheckerProtocol(Protocol):
    """
    Interface für eine einzelne Schicht der Semantic-Evaluator-Kaskade.
    Implementierungen: Layer1RuleChecker, Layer2EmbeddingChecker, Layer3LLMJudge.
    Schicht 1 und 2 → Rust-Kern; Schicht 3 bleibt Python (LLM-Calls).
    """

    def check(
        self,
        output: str,
        fingerprint: Fingerprint,
        context: SessionContext,
    ) -> CheckResult:
        """
        Bewertet einen LLM-Output gegen den Fingerprint.
        Muss deterministisch sein (Schicht 1) oder reproduzierbar (Schicht 2).
        """
        ...


@runtime_checkable
class ScoringEngineProtocol(Protocol):
    """
    Entscheidungslogik: nimmt Ergebnisse aller aktiven Schichten und
    gibt eine ScoringDecision zurück.

    Entscheidungstabelle (aus Architekturskizze):
    S1 OR S2 low              → REFINEMENT
    S1 AND S2 high            → OUTPUT
    S1 OR S2 high, andere med → TRANSFORM
    S1 AND S2 medium          → TIEBREAK (→ Schicht 3)
    Nach S3 "passt"           → TRANSFORM
    Nach S3 "passt nicht"     → REFINEMENT

    → Rust-Kern (Zielarchitektur)
    """

    def decide(self, s1: CheckResult, s2: CheckResult) -> ScoringDecision:
        ...

    def decide_after_tiebreak(self, tiebreak_passed: bool) -> ScoringDecision:
        ...
