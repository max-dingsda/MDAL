"""
Status-Meldungen an den Client während der Pipeline-Verarbeitung (F15).

Diese Meldungen informieren den Nutzer über den aktuellen Verarbeitungsstand.
Die konkreten Strings sind auf Deutsch — die Zielgruppe ist der Endnutzer.

StatusReporter ist ein Protocol — die konkrete Implementierung kann Meldungen
per SSE, WebSocket, Log oder beliebigem anderen Kanal ausgeben.
Die LoggingStatusReporter-Implementierung ist der PoC-Standard.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Protocol, runtime_checkable


class StatusMessage(str, Enum):
    """Vordefinierte Statusmeldungen für den Client (F15)."""

    PROCESSING = "Anfrage wird verarbeitet"
    CHECKING   = "Ergebnis wird geprüft"
    ADJUSTING  = "Ergebnis wird angepasst"
    REFINING   = "Antwort wird überarbeitet"
    READY      = "Antwort ist bereit"


@runtime_checkable
class StatusReporter(Protocol):
    """
    Empfängt Status-Meldungen aus der Pipeline und leitet sie weiter.

    Implementierungen können:
      - Meldungen ins Log schreiben (LoggingStatusReporter)
      - Meldungen per SSE an den Client streamen (API-Phase)
      - Meldungen in eine Queue schreiben (für Tests)
    """

    def report(self, message: StatusMessage) -> None:
        """Sendet eine Statusmeldung. Darf nicht werfen."""
        ...


class LoggingStatusReporter:
    """
    Schreibt Statusmeldungen in das Python-Log.

    Standard-Implementierung für den PoC.
    Im Produktivbetrieb (Phase 5) durch SSE-Implementierung ersetzt.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def report(self, message: StatusMessage) -> None:
        self._logger.info("[STATUS] %s", message.value)


class QueueStatusReporter:
    """
    Sammelt Statusmeldungen in einer Liste.

    Wird in Tests verwendet um gelieferte Statusmeldungen zu prüfen.
    """

    def __init__(self) -> None:
        self.messages: list[StatusMessage] = []

    def report(self, message: StatusMessage) -> None:
        self.messages.append(message)
