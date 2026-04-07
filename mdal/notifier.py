"""
Admin notification on escalation and capability asymmetry (F5, F13).

Two channels (configurable):
  - Log file (JSONL, write-only, analogous to mdal/audit.py)
  - Webhook (HTTP POST, best-effort — errors are logged, not raised)

F5:  Retry limit exhausted → notify_escalation
F13: LLM persistently unable to meet style requirements → notify_capability_asymmetry
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from mdal.config import NotifierConfig

logger = logging.getLogger(__name__)


class AdminNotifier:
    """
    Notifies the administrator of critical pipeline events.

    No exception propagation to the outside — notification errors are
    only logged so the main processing path is not blocked.
    """

    def __init__(self, config: NotifierConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notify_escalation(
        self,
        session_id: str,
        retry_count: int,
        last_error: str,
    ) -> None:
        """
        F5: Retry limit exhausted — output is withheld.

        Called before RetryLimitError is raised.
        """
        logger.error("🛑 Escalation (503) - aborting after %d attempts: %s", retry_count, last_error)
        self._notify("escalation", {
            "session_id":  session_id,
            "retry_count": retry_count,
            "last_error":  last_error,
        })

    def notify_capability_asymmetry(
        self,
        session_id: str,
        language: str,
        details: str,
    ) -> None:
        """
        F13: LLM unable to meet the style requirements of the fingerprint.

        Note for the admin: consider recalibrating the fingerprint or
        switching the model.
        """
        logger.warning("⚠️ Capability asymmetry detected (language: %s): %s", language, details)
        self._notify("capability_asymmetry", {
            "session_id": session_id,
            "language":   language,
            "details":    details,
        })

    def notify_technical_crash(self, error: str, details: str, traceback_str: str) -> None:
        """
        F4/F11: Unhandled technical crash (e.g. timeout, internal bug).
        Called by the global exception handler to prevent silent failures.
        """
        # The technical crash is already logged with traceback via logger.error in server.py.
        self._notify("technical_crash", {
            "error":     error,
            "details":   details,
            "traceback": traceback_str,
        })

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _notify(self, event_type: str, data: dict[str, Any]) -> None:
        entry: dict[str, Any] = {
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            **data,
        }
        self._write_log(entry)
        if self._config.webhook_url:
            self._send_webhook(entry)

    def _write_log(self, entry: dict[str, Any]) -> None:
        if not self._config.log_path:
            logger.warning(
                "AdminNotifier: no log_path configured — event: %s",
                entry,
            )
            return
        path = Path(self._config.log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.error("AdminNotifier: log file not writable (%s): %s", path, exc)

    def _send_webhook(self, entry: dict[str, Any]) -> None:
        try:
            with httpx.Client(timeout=5) as client:
                response = client.post(
                    self._config.webhook_url,  # type: ignore[arg-type]
                    json=entry,
                )
                if response.status_code >= 400:
                    logger.warning(
                        "AdminNotifier: webhook responded with %d", response.status_code
                    )
        except Exception as exc:
            logger.warning("AdminNotifier: webhook call failed: %s", exc)
