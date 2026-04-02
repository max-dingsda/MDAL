"""
Session Context — ephemerer Zustand einer laufenden Session (F14, NF3).

Der Session Context existiert ausschließlich für die Dauer einer Session.
Er wird nach Session-Ende vollständig verworfen — keine Persistierung.

Zweck:
  - Multi-Turn-Konsistenz: Der Fingerabdruck wird innerhalb einer Session
    konsistent angewendet. Output 3 darf Output 1 stilistisch nicht widersprechen.
  - Aktive Fingerprint-Version für diese Session merken.
  - Prüfhistorie für Konsistenzvergleich vorhalten.

Session-übergreifende Konsistenz ist explizit nicht vorgesehen (F14):
Sie würde Datenspeicherung erfordern und widerspricht NF3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from mdal.interfaces.scoring import CheckResult


@dataclass
class SessionContext:
    """
    Ephemerer Zustand einer laufenden Session.

    Wird beim ersten Request angelegt und nach Session-Ende verworfen.
    Enthält keine persistierten Nutzerinhalte.
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
        Speichert ein Prüfergebnis in der Session-Prüfhistorie.

        Die Historie ermöglicht Konsistenzvergleiche über mehrere Turns (F14):
        Wenn frühere Turns mit HIGH bewertet wurden und ein späterer Turn
        deutlich abweicht, kann das ein Signal für Drift sein.
        """
        self._check_history.append(result)
        self.turn_count += 1

    def check_history(self) -> list[CheckResult]:
        """Gibt eine Kopie der Prüfhistorie zurück (unveränderlich von außen)."""
        return list(self._check_history)

    def has_prior_checks(self) -> bool:
        return len(self._check_history) > 0

    def last_check(self) -> CheckResult | None:
        return self._check_history[-1] if self._check_history else None
