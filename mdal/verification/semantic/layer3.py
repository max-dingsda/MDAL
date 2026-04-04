"""
Semantic Layer 3 — LLM-as-Judge (SemanticCheckerProtocol).

Höchste Präzision, höchste Kosten.
Wird nur für Grenzfälle aufgerufen wenn S1 und S2 keinen eindeutigen Befund liefern
(ScoringDecision.TIEBREAK).

Der Judge bekommt die Golden Samples aus dem Fingerprint als Kontext und
entscheidet ob der zu prüfende Output stilistisch dazu passt.
Antwort ist binär: "passt" → HIGH, "passt nicht" → LOW.

Zählt als LLM-Aufruf im Sinne der Retry-Logik (F5).
Bleibt Python — direkter LLM-Call, kein Rust-Kandidat.
"""

from __future__ import annotations

from mdal.fingerprint.models import Fingerprint
from mdal.interfaces.llm import LLMAdapterProtocol
from mdal.interfaces.scoring import CheckResult, ScoreLevel
from mdal.session import SessionContext

_JUDGE_PROMPT = """\
Du bist ein Stil-Gutachter. Deine Aufgabe ist es zu beurteilen ob ein Text \
stilistisch zu einer Reihe von Referenzbeispielen passt.

Referenzbeispiele (repräsentieren den gewünschten Stil):
{samples}

Zu beurteilender Text:
{output}

Kriterien: Tonalität, Formalitätsniveau, Formulierungsstil, sprachliches Verhalten.
Inhalt und Thema des Textes sind irrelevant — nur der Stil zählt.

Begründe dein Urteil in 1-2 Sätzen. Schreibe dann als letzte Zeile \
ausschließlich eines der folgenden Wörter:
  PASST
  PASST NICHT
"""


class Layer3LLMJudge:
    """
    Implementiert SemanticCheckerProtocol via LLM-as-Judge.

    Benötigt Fingerprint mit mindestens einem Golden Sample.
    Wenn keine Golden Samples vorhanden: MEDIUM als konservatives Ergebnis.
    """

    def __init__(self, llm_adapter: LLMAdapterProtocol) -> None:
        self._llm = llm_adapter

    def check(
        self,
        output: str,
        fingerprint: Fingerprint,
        context: SessionContext,
    ) -> CheckResult:
        samples = fingerprint.layer3.samples

        if not samples:
            return CheckResult(
                level=ScoreLevel.MEDIUM,
                details="Keine Golden Samples konfiguriert — konservatives MEDIUM.",
            )

        samples_text = "\n\n".join(
            f"[Beispiel {i+1}]\nUser: {s.prompt}\nAssistent: {s.response}"
            for i, s in enumerate(samples[:5])   # max. 5 Samples im Prompt
        )

        prompt = _JUDGE_PROMPT.format(
            samples=samples_text,
            output=output,
        )

        raw = self._llm.complete([{"role": "user", "content": prompt}])
        passed = _parse_judgment(raw)

        # Begründung aus der CoT-Antwort extrahieren (alle Zeilen außer dem Urteil)
        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        reasoning = " ".join(lines[:-1]) if len(lines) > 1 else ""

        return CheckResult(
            level=ScoreLevel.HIGH if passed else ScoreLevel.LOW,
            details=f"LLM-Judge: {'PASST' if passed else 'PASST NICHT'}"
                    + (f" — {reasoning[:120]}" if reasoning else ""),
        )


def _parse_judgment(response: str) -> bool:
    """
    Parst die LLM-Judge-Antwort mit CoT-Format (CR-Finding #5).

    Das Urteil steht am Ende der Antwort (letzte nicht-leere Zeile).
    Robust gegenüber Leerzeichen und Groß-/Kleinschreibung.
    Fallback: konservativ als nicht-passend werten wenn unklar.
    """
    lines = [line.strip() for line in response.strip().splitlines() if line.strip()]
    if not lines:
        return False

    last = lines[-1].upper()
    if last == "PASST NICHT" or last.startswith("PASST NICHT"):
        return False
    if last == "PASST" or last.startswith("PASST"):
        return True

    # Fallback: gesamten Text nach "PASST NICHT" / "PASST" durchsuchen
    text = response.upper()
    if "PASST NICHT" in text:
        return False
    if "PASST" in text:
        return True

    return False
