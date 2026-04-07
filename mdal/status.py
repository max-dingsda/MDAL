"""
Status messages to the client during pipeline processing (F15).

These messages inform the user about the current processing state.
StatusReporter is a Protocol — the concrete implementation can deliver
messages via SSE, WebSocket, log, or any other channel.
The LoggingStatusReporter implementation is the PoC default.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Protocol, runtime_checkable


class StatusMessage(str, Enum):
    """Predefined status messages for the client (F15)."""

    PROCESSING = "Processing request"
    CHECKING   = "Verifying result"
    ADJUSTING  = "Adjusting result"
    REFINING   = "Refining response"
    READY      = "Response ready"


@runtime_checkable
class StatusReporter(Protocol):
    """
    Receives status messages from the pipeline and forwards them.

    Implementations may:
      - write messages to the log (LoggingStatusReporter)
      - stream messages to the client via SSE (API phase)
      - write messages to a queue (for tests)
    """

    def report(self, message: StatusMessage) -> None:
        """Sends a status message. Must not raise."""
        ...


class LoggingStatusReporter:
    """
    Writes status messages to the Python log.

    Default implementation for the PoC.
    Replaced by an SSE implementation in production (Phase 5).
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def report(self, message: StatusMessage) -> None:
        self._logger.info("[STATUS] %s", message.value)


class QueueStatusReporter:
    """
    Collects status messages in a list.

    Used in tests to verify delivered status messages.
    """

    def __init__(self) -> None:
        self.messages: list[StatusMessage] = []

    def report(self, message: StatusMessage) -> None:
        self.messages.append(message)
