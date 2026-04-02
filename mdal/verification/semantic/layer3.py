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

Antworte ausschließlich mit einem der folgenden Wörter — kein Erklärtext:
  passt
  passt nicht

Kriterien: Tonalität, Formalitätsniveau, Formulierungsstil, sprachliches Verhalten.
Inhalt und Thema des Textes sind irrelevant — nur der Stil zählt.
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

        return CheckResult(
            level=ScoreLevel.HIGH if passed else ScoreLevel.LOW,
            details=f"LLM-Judge: {'passt' if passed else 'passt nicht'} "
                    f"(Antwort: {raw.strip()[:50]!r})",
        )


def _parse_judgment(response: str) -> bool:
    """
    Parst die binäre LLM-Judge-Antwort.
    Robust gegenüber Leerzeichen, Groß-/Kleinschreibung und kurzen Erläuterungen.
    """
    text = response.strip().lower()
    if text.startswith("passt nicht") or "passt nicht" in text[:30]:
        return False
    if text.startswith("passt") or text == "passt":
        return True
    # Fallback: wenn unklar → konservativ als nicht-passend werten
    return False
