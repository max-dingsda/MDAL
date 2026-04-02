"""
Scoring-Modell — Entscheidungskaskade (ScoringEngineProtocol).

Implementiert die Entscheidungstabelle aus der Architekturskizze exakt:

  S1 OR  S2 low              → REFINEMENT
  S1 AND S2 high             → OUTPUT
  S1 OR  S2 high, andere med → TRANSFORM
  S1 AND S2 medium           → TIEBREAK (→ Layer 3)
  Nach S3 "passt"            → TRANSFORM
  Nach S3 "passt nicht"      → REFINEMENT

Das System trifft binäre Entscheidungen nach außen.
Intern arbeitet die Prüfung mit Schweregraden weil Embeddings Ähnlichkeitswerte
liefern, keine Ja/Nein-Antworten.

→ Rust-Kern (Zielarchitektur): pure Entscheidungslogik ohne IO.
"""

from __future__ import annotations

from mdal.interfaces.scoring import CheckResult, ScoreLevel, ScoringDecision


class ScoringEngine:
    """Implementiert ScoringEngineProtocol."""

    def decide(self, s1: CheckResult, s2: CheckResult) -> ScoringDecision:
        """
        Trifft eine Entscheidung basierend auf den Ergebnissen von Layer 1 und 2.

        Entscheidungstabelle (aus Architekturskizze):
          S1 OR  S2 is LOW               → REFINEMENT
          S1 AND S2 both HIGH            → OUTPUT
          S1 OR  S2 HIGH, andere MEDIUM  → TRANSFORM
          S1 AND S2 both MEDIUM          → TIEBREAK
        """
        l1, l2 = s1.level, s2.level

        # Klare Abweichung
        if l1 == ScoreLevel.LOW or l2 == ScoreLevel.LOW:
            return ScoringDecision.REFINEMENT

        # Beide konform
        if l1 == ScoreLevel.HIGH and l2 == ScoreLevel.HIGH:
            return ScoringDecision.OUTPUT

        # Leichte Abweichung: einer HIGH, einer MEDIUM
        if (l1 == ScoreLevel.HIGH and l2 == ScoreLevel.MEDIUM) or \
           (l1 == ScoreLevel.MEDIUM and l2 == ScoreLevel.HIGH):
            return ScoringDecision.TRANSFORM

        # Graubereich: beide MEDIUM → Tiebreaker
        if l1 == ScoreLevel.MEDIUM and l2 == ScoreLevel.MEDIUM:
            return ScoringDecision.TIEBREAK

        # Sollte nicht erreichbar sein, aber defensiv:
        return ScoringDecision.REFINEMENT

    def decide_after_tiebreak(self, tiebreak_passed: bool) -> ScoringDecision:
        """
        Entscheidung nach Layer 3 (LLM-as-Judge):
          S3 "passt"      → TRANSFORM (Graubereich wird als medium eingestuft)
          S3 "passt nicht"→ REFINEMENT
        """
        return ScoringDecision.TRANSFORM if tiebreak_passed else ScoringDecision.REFINEMENT
