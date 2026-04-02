"""
Retry-Steuerung (F5).

Regelt die Schleife aus LLM-Aufruf → Prüfung → Entscheidung:

  - Maximal `max_retries` LLM-Aufrufe (konfigurierbar, Default 3).
  - Transformer-Aufruf zählt NICHT als LLM-Aufruf (F5).
  - Bei Erschöpfung: Admin benachrichtigen (F5), RetryLimitError werfen.
  - Output wird bei Erschöpfung zurückgehalten (nicht an Client weitergeleitet).

Schnittstelle bewusst als Callable-Parameter gehalten, damit:
  a) RetryController ohne konkrete Pipeline-Abhängigkeiten testbar ist
  b) Die Rust-Extraktion dieses Kerns später erleichtert wird
"""

from __future__ import annotations

from typing import Callable

from mdal.interfaces.scoring import ScoringDecision
from mdal.notifier import AdminNotifier
from mdal.session import SessionContext
from mdal.verification.engine import VerificationResult


class RetryLimitError(Exception):
    """
    Retry-Limit erschöpft — kein konformer Output produzierbar (F5).

    Der Output wird NICHT an den Client weitergeleitet.
    Der Admin wurde über AdminNotifier.notify_escalation informiert.
    """

    def __init__(self, session_id: str, attempts: int) -> None:
        super().__init__(
            f"Retry-Limit ({attempts}) erschöpft für Session {session_id}. "
            "Output wurde zurückgehalten."
        )
        self.session_id = session_id
        self.attempts   = attempts


class RetryController:
    """
    Orchestriert die Retry-Schleife der MDAL-Pipeline.

    Ablauf je Durchlauf:
      1. LLM aufrufen (initial_call beim ersten Mal, refine_call danach)
      2. Output prüfen (verify)
      3. Entscheidung auswerten:
         - OUTPUT    → Output zurückgeben (fertig)
         - TRANSFORM → Transformer anwenden, Output zurückgeben (fertig)
         - REFINEMENT → Retry, falls Limit nicht erreicht; sonst eskalieren

    Der Transformer zählt nicht als LLM-Aufruf (F5).
    """

    def __init__(self, max_retries: int, notifier: AdminNotifier) -> None:
        if max_retries < 1:
            raise ValueError("max_retries muss mindestens 1 sein")
        self._max      = max_retries
        self._notifier = notifier

    def run(
        self,
        context:      SessionContext,
        initial_call: Callable[[], str],
        refine_call:  Callable[[str, str], str],
        verify:       Callable[[str, SessionContext], VerificationResult],
        transform:    Callable[[str], str],
    ) -> str:
        """
        Führt die Retry-Schleife aus und gibt den finalen Output zurück.

        Parameters
        ----------
        context:      Aktiver Session-Kontext (wird bei record_check befüllt).
        initial_call: Callable ohne Parameter → erster LLM-Aufruf.
        refine_call:  Callable(prev_output, error_summary) → verfeinerter LLM-Aufruf.
        verify:       Callable(output, context) → VerificationResult.
        transform:    Callable(output) → transformierter Output (kein LLM).

        Returns
        -------
        str: Finaler Output (direkt oder nach Transformer).

        Raises
        ------
        RetryLimitError: Wenn max_retries LLM-Aufrufe verbraucht wurden ohne
                         konformen Output. Admin wurde benachrichtigt.
        """
        attempts = 0
        output   = initial_call()
        attempts += 1

        while True:
            result = verify(output, context)

            if result.decision == ScoringDecision.OUTPUT:
                return output

            if result.decision == ScoringDecision.TRANSFORM:
                return transform(output)

            # REFINEMENT: weiterer LLM-Aufruf nötig
            if attempts >= self._max:
                self._notifier.notify_escalation(
                    session_id  = context.session_id,
                    retry_count = attempts,
                    last_error  = result.error_summary(),
                )
                raise RetryLimitError(context.session_id, attempts)

            output   = refine_call(output, result.error_summary())
            attempts += 1
