"""
Pipeline-Orchestrator — verbindet alle MDAL-Komponenten (F1–F18).

Ablauf eines Request-Durchlaufs:
  1. STATUS: Anfrage wird verarbeitet
  2. Fingerprint laden (aktuelle Version für die Sprache)
  3. SessionContext anlegen
  4. RetryController.run() mit:
       - initial_call:  LLM-Aufruf mit den Original-Messages
       - refine_call:   LLM-Aufruf mit Refinement-Anhang
       - verify:        VerificationEngine (STATUS: Prüfung)
       - transform:     RuleBasedToneTransformer (STATUS: Anpassung)
  5. STATUS: Antwort ist bereit
  6. Output zurückgeben

Fehlerbehandlung:
  - RetryLimitError: wird nach oben weitergegeben (kein Output an Client)
  - FingerprintStore-Fehler: werden nicht gefangen (F11 — kein stiller Fallback)
"""

from __future__ import annotations

import logging
import re

try:
    from langdetect import detect, LangDetectException
except ImportError:
    detect = None

from mdal.fingerprint.models import Fingerprint
from mdal.fingerprint.store import FingerprintStore
from mdal.interfaces.llm import LLMAdapterProtocol
from mdal.retry import RetryController, RetryLimitError
from mdal.session import SessionContext
from mdal.status import QueueStatusReporter, StatusMessage, StatusReporter
from mdal.transformer import LLMToneTransformer
from mdal.verification.engine import VerificationEngine, VerificationResult
from mdal.verification.detector import detect_format

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Refinement-Prompt
# ---------------------------------------------------------------------------

_REFINEMENT_USER_MESSAGE = """\
Deine letzte Antwort war fehlerhaft und wurde vom System zurückgewiesen.

FESTGESTELLTE FEHLER:
{error_summary}

DEINE ABGELEHNTE ANTWORT:
{prev_output}

AUFGABE:
Bitte korrigiere die genannten Fehler und generiere die Antwort neu. Behalte die inhaltliche Struktur, Fakten, Reihenfolge und Vollständigkeit der Antwort unter allen Umständen UNVERÄNDERT bei!
"""


def _build_refinement_messages(
    original_messages: list[dict],
    prev_output:       str,
    error_summary:     str,
) -> list[dict]:
    """
    Hängt einen expliziten Korrektur-Hinweis inkl. des fehlerhaften Outputs an die
    Original-Messages an.
    """
    return [
        *original_messages,
        {
            "role":    "user",
            "content": _REFINEMENT_USER_MESSAGE.format(
                error_summary=error_summary,
                prev_output=prev_output
            ),
        },
    ]

# ---------------------------------------------------------------------------
# Domänen-Klassifizierung (Säule B)
# ---------------------------------------------------------------------------

_DOMAIN_PROMPT = """\
Analysiere die folgende Benutzeranfrage und ordne sie exakt einer der folgenden Domänen zu:
- TECHNICAL: Technische Erklärungen, IT-Architektur, Programmierung.
- BUSINESS: Formelle geschäftliche E-Mails, Vorstandspräsentationen, Mahnungen.
- CREATIVE: Storytelling, Prosa, bildhafte Beschreibungen, lockere Dialoge.
- SHORT_COPY: Sehr kurze Anfragen, Slogans, Social Media (unter 3 Sätze erwartet).
- DEFAULT: Alles andere, Smalltalk, allgemeine Fragen.

Antworte AUSSCHLIESSLICH mit exakt einem dieser 5 Begriffe (TECHNICAL, BUSINESS, CREATIVE, SHORT_COPY, DEFAULT). Keine Erklärungen!

Benutzeranfrage:
{prompt}
"""

def _classify_domain(messages: list[dict], llm: LLMAdapterProtocol) -> str:
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    if not user_msgs:
        return "DEFAULT"
    prompt = _DOMAIN_PROMPT.format(prompt=user_msgs[-1][:1000])
    try:
        res = llm.complete([{"role": "user", "content": prompt}]).strip().upper()
        for d in ["TECHNICAL", "BUSINESS", "CREATIVE", "SHORT_COPY"]:
            if d in res:
                return d
        return "DEFAULT"
    except Exception:
        return "DEFAULT"

# ---------------------------------------------------------------------------
# Pipeline-Orchestrator
# ---------------------------------------------------------------------------

class PipelineOrchestrator:
    """
    Verbindet LLM, VerificationEngine, Transformer und RetryController.

    Wird einmal pro Server-Instanz angelegt (alle Abhängigkeiten per Konstruktor).
    Ist zustandslos in Bezug auf individuelle Requests — SessionContext wird
    pro Request neu angelegt.
    """

    def __init__(
        self,
        llm:          LLMAdapterProtocol,
        verification: VerificationEngine,
        transformer:  LLMToneTransformer,
        store:        FingerprintStore,
        retry:        RetryController,
        status:       StatusReporter | None = None,
    ) -> None:
        self._llm          = llm
        self._verification = verification
        self._transformer  = transformer
        self._store        = store
        self._retry        = retry
        self._status: StatusReporter = status or QueueStatusReporter()

    def process(
        self,
        messages: list[dict],
        language: str,
    ) -> str:
        """
        Verarbeitet einen vollständigen LLM-Request durch die MDAL-Pipeline.

        Parameters
        ----------
        messages: Chat-Messages im OpenAI-Format (role/content).
        language: Sprachkürzel (z. B. "de", "en") zum Fingerprint-Lookup.

        Returns
        -------
        str: Finaler, konformer Output — direkt oder nach Transformation.

        Raises
        ------
        RetryLimitError: Wenn kein konformer Output produziert werden konnte.
        KeyError / FileNotFoundError: Wenn kein Fingerprint für die Sprache existiert.
        """
        self._status.report(StatusMessage.PROCESSING)

        domain = _classify_domain(messages, self._llm)
        logger.info("Säule B: Erkannte Text-Domäne für Request: %s", domain)

        fingerprint = self._store.load_current(language)
        version     = self._store.current_version(language) or 0
        context     = SessionContext(language=language, fingerprint_version=version)

        def initial_call() -> str:
            return self._llm.complete(messages)

        def refine_call(prev_output: str, error_summary: str) -> str:
            self._status.report(StatusMessage.REFINING)
            refined_messages = _build_refinement_messages(
                messages, prev_output, error_summary
            )
            return self._llm.complete(refined_messages)

        def verify(output: str, ctx: SessionContext) -> VerificationResult:
            self._status.report(StatusMessage.CHECKING)
            
            # F2: Strukturierte Outputs erkennen
            is_structured = detect_format(output).is_structured()

            # F8: Hard Language Lock (Sprach-Drift hart blockieren)
            if not is_structured and detect is not None and len(output.split()) > 10:
                try:
                    detected_lang = detect(output)
                    if not language.startswith(detected_lang):
                        error_msg = f"Sprach-Drift (F8): Erwartet '{language}', aber '{detected_lang}' generiert."
                        self._retry._notifier.notify_escalation(
                            session_id=ctx.session_id,
                            retry_count=self._retry._max,
                            last_error=error_msg,
                        )
                        raise RetryLimitError(ctx.session_id, self._retry._max)
                except LangDetectException:
                    pass  # Zu kurz oder unklar für Spracherkennung
            
            return self._verification.verify(output, fingerprint, ctx)

        def do_transform(output: str) -> str:
            self._status.report(StatusMessage.ADJUSTING)
            return self._transformer.transform(output, fingerprint, domain)

        final_output = self._retry.run(
            context      = context,
            initial_call = initial_call,
            refine_call  = refine_call,
            verify       = verify,
            transform    = do_transform,
        )

        self._status.report(StatusMessage.READY)
        
        # F21: Post-Processing Filter anwenden
        return _post_process(final_output)


# ---------------------------------------------------------------------------
# Post-Processing
# ---------------------------------------------------------------------------

def _post_process(text: str) -> str:
    """
    F21: Entfernt generierte Meta-Kommentare und LLM-Einleitungen vor der Auslieferung.
    """
    # Entfernt typische LLM-Prologe wie "Hier ist die angepasste Version:"
    text = re.sub(
        r"^(?:Hier ist|Dies ist|Anbei)(?: eine| die)? (?:angepasste|überarbeitete|korrigierte) (?:Version|Antwort|Fassung).*?:\s*\n*",
        "", text, flags=re.IGNORECASE
    )
    # Entfernt Klammer-Kommentare wie (Hier ist der Text) am Anfang oder Ende
    text = re.sub(
        r"^\s*[\(\[].*(?:angepasst|transformiert|Version|Hier ist|überarbeitet|korrigiert).*?[\)\]]\s*\n?",
        "", text, flags=re.IGNORECASE | re.MULTILINE
    )
    return text.strip()
