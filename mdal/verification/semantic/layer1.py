"""
Semantic Layer 1 — Regelbasierter Prüfer (SemanticCheckerProtocol).

Schnell und deterministisch. Prüft messbare Stilmerkmale aus dem Fingerprint:
  - Formalitätsniveau (Heuristik: Satzlänge, Vokabular-Indikatoren)
  - Bevorzugtes Vokabular (preferred_vocabulary)
  - Vermiedenes Vokabular (avoided_vocabulary)

Grenzen des PoC:
  Die Formalitätsheuristik ist ein erster Ansatz für die Validierung.
  Schwellwerte und Gewichtungen sind bewusst beobachtbar gehalten (NF9).
  Ziel: herausfinden ob dieser Ansatz tragfähig ist (eine der 4 PoC-Fragen).

→ Rust-Kern (Zielarchitektur): regelbasierter Abgleich ohne LLM-Overhead.
"""

from __future__ import annotations

import re

from mdal.fingerprint.models import Fingerprint
from mdal.interfaces.scoring import CheckResult, ScoreLevel
from mdal.session import SessionContext

# Formalitäts-Heuristik: Schwellwerte für Satzlänge (Wörter)
_FORMAL_MIN_AVG_SENTENCE_WORDS = 12
_INFORMAL_MAX_AVG_SENTENCE_WORDS = 7

# Informelle Indikatoren (sprachübergreifend — für Deutsch/Englisch)
_INFORMAL_PATTERNS = re.compile(
    r"\b(naja|okay|ok|jo|äh|ähm|hmm|halt|irgendwie|eigentlich|sozusagen"
    r"|btw|imho|fyi|yeah|yep|nope|gonna|wanna|gotta)\b",
    re.IGNORECASE,
)

# Formelle Indikatoren
_FORMAL_PATTERNS = re.compile(
    r"\b(gemäß|hinsichtlich|infolgedessen|diesbezüglich|folglich|mithin"
    r"|demnach|entsprechend|insbesondere|ferner|zudem|darüber hinaus"
    r"|pursuant|whereas|herewith|aforementioned|subsequently)\b",
    re.IGNORECASE,
)


class Layer1RuleChecker:
    """
    Implementiert SemanticCheckerProtocol via regelbasierter Stilprüfung.

    Scoring-Logik:
      Jede aktivierte Prüfung liefert ein Signal (pass/fail).
      Das Gesamtergebnis ist das schwächste Signal:
        - Avoided vocabulary gefunden      → LOW  (direkt)
        - Formalität stark abweichend      → LOW
        - Keine preferred terms gefunden   → MEDIUM
        - Formalität leicht abweichend     → MEDIUM
        - Alles passt                      → HIGH
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

        # --- Avoided vocabulary (F1: Stil-Normalisierung) ---
        if rules.avoided_vocabulary:
            found = [
                w for w in rules.avoided_vocabulary
                if re.search(rf"\b{re.escape(w)}\b", output, re.IGNORECASE)
            ]
            if found:
                scores.append(ScoreLevel.LOW)
                notes.append(f"Vermiedenes Vokabular gefunden: {found}")
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
                    f"Nur {len(found)}/{len(rules.preferred_vocabulary)} "
                    f"bevorzugte Begriffe gefunden."
                )
            else:
                scores.append(ScoreLevel.MEDIUM)
                notes.append("Kein bevorzugtes Vokabular gefunden.")

        # --- Formalitätsniveau ---
        estimated = _estimate_formality(output)
        expected  = rules.formality_level
        delta     = abs(estimated - expected)

        if delta == 0:
            scores.append(ScoreLevel.HIGH)
        elif delta == 1:
            scores.append(ScoreLevel.MEDIUM)
            notes.append(
                f"Formalität: erwartet={expected}, geschätzt≈{estimated} (Δ=1)."
            )
        else:
            scores.append(ScoreLevel.LOW)
            notes.append(
                f"Formalität stark abweichend: erwartet={expected}, geschätzt≈{estimated} (Δ={delta})."
            )

        # Satzlängen-Check (sofern konfiguriert)
        if rules.avg_sentence_length_max is not None:
            avg_len = _avg_sentence_length(output)
            if avg_len > rules.avg_sentence_length_max * 1.5:
                scores.append(ScoreLevel.LOW)
                notes.append(
                    f"Durchschnittliche Satzlänge zu hoch: "
                    f"{avg_len:.0f} Wörter (max. {rules.avg_sentence_length_max})."
                )
            elif avg_len > rules.avg_sentence_length_max:
                scores.append(ScoreLevel.MEDIUM)

        # Schwächstes Signal gewinnt
        final = _weakest(scores) if scores else ScoreLevel.MEDIUM

        return CheckResult(
            level=final,
            details="; ".join(notes) if notes else "Regelprüfung bestanden.",
        )


# ---------------------------------------------------------------------------
# Hilfsfunktionen — Formalitätsheuristik
# ---------------------------------------------------------------------------

def _estimate_formality(text: str) -> int:
    """
    Schätzt das Formalitätsniveau auf einer 1-5-Skala.
    Heuristik: Kombination aus Satzlänge und Vokabular-Indikatoren.
    Für den PoC: beobachten ob diese Heuristik sinnvolle Werte liefert.
    """
    avg_len = _avg_sentence_length(text)
    word_count = len(text.split())

    if word_count == 0:
        return 3

    informal_hits = len(_INFORMAL_PATTERNS.findall(text))
    formal_hits   = len(_FORMAL_PATTERNS.findall(text))

    # Rohwert: Satzlänge als Basis (kurz=informal, lang=formal)
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

    # Vokabular-Korrekturen
    adjustment = 0
    if informal_hits > 0:
        adjustment -= min(informal_hits, 2)
    if formal_hits > 0:
        adjustment += min(formal_hits, 1)

    return max(1, min(5, base + adjustment))


def _avg_sentence_length(text: str) -> float:
    """Durchschnittliche Anzahl Wörter pro Satz."""
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0.0
    word_counts = [len(s.split()) for s in sentences]
    return sum(word_counts) / len(word_counts)


def _weakest(scores: list[ScoreLevel]) -> ScoreLevel:
    """Gibt das schwächste Score-Level zurück (LOW < MEDIUM < HIGH)."""
    order = {ScoreLevel.LOW: 0, ScoreLevel.MEDIUM: 1, ScoreLevel.HIGH: 2}
    return min(scores, key=lambda s: order[s])
