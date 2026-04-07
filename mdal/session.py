"""
Session Context — ephemeral state of a running session (F14, NF3).

The session context exists exclusively for the duration of a session.
It is fully discarded after the session ends — no persistence.

Purpose:
  - Multi-turn consistency: the fingerprint is applied consistently within
    a session. Output 3 must not stylistically contradict Output 1.
  - Track the active fingerprint version for this session.
  - Maintain a check history for consistency comparisons.

Cross-session consistency is explicitly not provided (F14):
it would require data storage and conflicts with NF3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from mdal.interfaces.scoring import CheckResult


@dataclass
class SessionContext:
    """
    Ephemeral state of a running session.

    Created at the first request and discarded after the session ends.
    Contains no persisted user content.
    """
    language:            str
    fingerprint_version: int
    session_id:          str             = field(default_factory=lambda: str(uuid4()))
    turn_count:          int             = 0
    _check_history:      list[CheckResult] = field(
        default_factory=list, init=False, repr=False
    )

    def record_check(self, result: CheckResult) -> None:
        """
        Stores a check result in the session check history.

        The history enables consistency comparisons across multiple turns (F14):
        if earlier turns were rated HIGH and a later turn deviates significantly,
        this can be a signal for drift.
        """
        self._check_history.append(result)
        self.turn_count += 1

    def check_history(self) -> list[CheckResult]:
        """Returns a copy of the check history (immutable from the outside)."""
        return list(self._check_history)

    def has_prior_checks(self) -> bool:
        return len(self._check_history) > 0

    def last_check(self) -> CheckResult | None:
        return self._check_history[-1] if self._check_history else None
