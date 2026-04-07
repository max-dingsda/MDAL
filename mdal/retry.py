"""
Retry control (F5).

Controls the loop of LLM call → verification → decision:

  - At most `max_retries` LLM calls (configurable, default 3).
  - Transformer call does NOT count as an LLM call (F5).
  - On exhaustion: notify admin (F5), raise RetryLimitError.
  - Output is withheld on exhaustion (not forwarded to client).

The interface is deliberately kept as callable parameters so that:
  a) RetryController can be tested without concrete pipeline dependencies
  b) Future Rust extraction of this core is simplified
"""

from __future__ import annotations

from typing import Callable

from mdal.interfaces.scoring import ScoringDecision
from mdal.notifier import AdminNotifier
from mdal.session import SessionContext
from mdal.verification.engine import VerificationResult


class RetryLimitError(Exception):
    """
    Retry limit exhausted — no conforming output producible (F5).

    The output is NOT forwarded to the client.
    The admin has been notified via AdminNotifier.notify_escalation.
    """

    def __init__(self, session_id: str, attempts: int) -> None:
        super().__init__(
            f"Retry limit ({attempts}) exhausted for session {session_id}. "
            "Output was withheld."
        )
        self.session_id = session_id
        self.attempts   = attempts


class RetryController:
    """
    Orchestrates the retry loop of the MDAL pipeline.

    Flow per iteration:
      1. Call LLM (initial_call on the first pass, refine_call thereafter)
      2. Verify output (verify)
      3. Evaluate decision:
         - OUTPUT    → return output (done)
         - TRANSFORM → apply transformer, return output (done)
         - REFINEMENT → retry if limit not reached; otherwise escalate

    The transformer does not count as an LLM call (F5).
    """

    def __init__(self, max_retries: int, notifier: AdminNotifier) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
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
        Executes the retry loop and returns the final output.

        Parameters
        ----------
        context:      Active session context (populated during record_check).
        initial_call: Callable with no parameters → first LLM call.
        refine_call:  Callable(prev_output, error_summary) → refined LLM call.
        verify:       Callable(output, context) → VerificationResult.
        transform:    Callable(output) → transformed output (no LLM).

        Returns
        -------
        str: Final output (direct or after transformer).

        Raises
        ------
        RetryLimitError: When max_retries LLM calls have been consumed without
                         a conforming output. Admin has been notified.
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

            # REFINEMENT: another LLM call required
            if attempts >= self._max:
                self._notifier.notify_escalation(
                    session_id  = context.session_id,
                    retry_count = attempts,
                    last_error  = result.error_summary(),
                )
                raise RetryLimitError(context.session_id, attempts)

            output   = refine_call(output, result.error_summary())
            attempts += 1
