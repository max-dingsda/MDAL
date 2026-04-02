"""
Audit Writer (F4, NF5) — write-only, betreiberseitig konfigurierbar.

Das System schreibt Prüf- und Transformationsereignisse in ein externes Audit-Ziel.
Es liest, bearbeitet oder löscht niemals externe Daten — ausschließlich append-only.

Speicherort, Aufbewahrungsdauer und Löschzeitpunkt liegen vollständig
in der Verantwortung des Betreibers.

Unterstützte Targets (v1):
  - file: JSONL-Datei, append-only

Geplante Targets (nach PoC):
  - postgresql, mysql, mssql (NF5)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mdal.config import AuditConfig


class AuditWriteError(Exception):
    """Wird geworfen wenn ein Audit-Event nicht geschrieben werden kann."""


class AuditWriter:
    """
    Write-only Audit Writer.

    Jedes Event wird als einzelne JSON-Zeile (JSONL) geschrieben.
    Das Format ist bewusst einfach — der Betreiber entscheidet über Rotation,
    Archivierung und Löschung.
    """

    def __init__(self, config: AuditConfig) -> None:
        self._config = config

    def write(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Schreibt ein Audit-Event.

        event_type: Kurze Beschreibung des Ereignisses, z.B.:
            "check.passed", "check.failed", "retry.attempt",
            "retry.exhausted", "transform.applied", "escalation.admin"

        data: Ereignis-spezifische Felder — werden mit Timestamp und event_type
              zu einem Audit-Eintrag zusammengeführt.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event":     event_type,
            **data,
        }

        if self._config.target == "file":
            self._write_file(entry)
        else:
            # Placeholder für DB-Targets — wird nach PoC-Validierung implementiert
            raise NotImplementedError(
                f"Audit-Target '{self._config.target}' ist noch nicht implementiert. "
                f"Verfügbar: 'file'"
            )

    def _write_file(self, entry: dict[str, Any]) -> None:
        assert self._config.path is not None
        path = Path(self._config.path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise AuditWriteError(
                f"Audit-Log konnte nicht geschrieben werden ({path}): {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def audit_writer_from_config(config: AuditConfig) -> AuditWriter:
    return AuditWriter(config)
