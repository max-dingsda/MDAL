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

from mdal.fingerprint.models import Fingerprint
from mdal.fingerprint.store import FingerprintStore
from mdal.interfaces.llm import LLMAdapterProtocol
from mdal.retry import RetryController
from mdal.session import SessionContext
from mdal.status import QueueStatusReporter, StatusMessage, StatusReporter
from mdal.transformer import LLMToneTransformer
from mdal.verification.engine import VerificationEngine, VerificationResult

# ---------------------------------------------------------------------------
# Refinement-Prompt
# ---------------------------------------------------------------------------

_REFINEMENT_USER_MESSAGE = (
    "Bitte überarbeite deine letzte Antwort. "
    "Folgende Probleme wurden festgestellt: {error_summary} "
    "Behalte Struktur, Reihenfolge und Vollständigkeit der Antwort unverändert bei."
)


def _build_refinement_messages(
    original_messages: list[dict],
    prev_output:       str,
    error_summary:     str,
) -> list[dict]:
    """
    Hängt den vorherigen Output und einen Korrektur-Hinweis an die
    Original-Messages an — ohne den Original-Kontext zu verändern.
    """
    return [
        *original_messages,
        {"role": "assistant", "content": prev_output},
        {
            "role":    "user",
            "content": _REFINEMENT_USER_MESSAGE.format(error_summary=error_summary),
        },
    ]


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
            return self._verification.verify(output, fingerprint, ctx)

        def do_transform(output: str) -> str:
            self._status.report(StatusMessage.ADJUSTING)
            return self._transformer.transform(output, fingerprint)

        final_output = self._retry.run(
            context      = context,
            initial_call = initial_call,
            refine_call  = refine_call,
            verify       = verify,
            transform    = do_transform,
        )

        self._status.report(StatusMessage.READY)
        return final_output
