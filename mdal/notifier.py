"""
Admin-Benachrichtigung bei Eskalation und Fähigkeits-Asymmetrie (F5, F13).

Zwei Kanäle (konfigurierbar):
  - Logdatei (JSONL, write-only, analog zu mdal/audit.py)
  - Webhook (HTTP POST, best-effort — Fehler werden geloggt, nicht geworfen)

F5:  Retry-Limit erschöpft → notify_escalation
F13: LLM kann Stilanforderungen dauerhaft nicht erfüllen → notify_capability_asymmetry
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
    Benachrichtigt den Administrator bei kritischen Pipeline-Ereignissen.

    Kein Exception-Propagation nach außen — Benachrichtigungsfehler werden
    nur geloggt, damit der Hauptpfad nicht blockiert wird.
    """

    def __init__(self, config: NotifierConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def notify_escalation(
        self,
        session_id: str,
        retry_count: int,
        last_error: str,
    ) -> None:
        """
        F5: Retry-Limit erschöpft — Output wird zurückgehalten.

        Wird aufgerufen bevor RetryLimitError geworfen wird.
        """
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
        F13: LLM kann Stil-Anforderungen des Fingerprints nicht erfüllen.

        Hinweis für den Admin: Fingerprint ggf. neu kalibrieren oder
        Modell austauschen.
        """
        self._notify("capability_asymmetry", {
            "session_id": session_id,
            "language":   language,
            "details":    details,
        })

    def notify_technical_crash(self, error: str, details: str, traceback_str: str) -> None:
        """
        F4/F11: Unbehandelter technischer Absturz (z.B. Timeout, interner Bug).
        Wird vom globalen Exception-Handler aufgerufen, um Silent Fails zu verhindern.
        """
        self._notify("technical_crash", {
            "error":     error,
            "details":   details,
            "traceback": traceback_str,
        })

    # ------------------------------------------------------------------
    # Internes
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
                "AdminNotifier: kein log_path konfiguriert — Ereignis: %s",
                entry,
            )
            return
        path = Path(self._config.log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.error("AdminNotifier: Logdatei nicht schreibbar (%s): %s", path, exc)

    def _send_webhook(self, entry: dict[str, Any]) -> None:
        try:
            with httpx.Client(timeout=5) as client:
                response = client.post(
                    self._config.webhook_url,  # type: ignore[arg-type]
                    json=entry,
                )
                if response.status_code >= 400:
                    logger.warning(
                        "AdminNotifier: Webhook antwortete mit %d", response.status_code
                    )
        except Exception as exc:
            logger.warning("AdminNotifier: Webhook-Aufruf fehlgeschlagen: %s", exc)
