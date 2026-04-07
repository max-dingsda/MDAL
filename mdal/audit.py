"""
Audit Writer (F4, NF5) — write-only, operator-configurable.

The system writes verification and transformation events to an external audit target.
It never reads, modifies, or deletes external data — strictly append-only.

Storage location, retention period, and deletion schedule are entirely
the operator's responsibility.

Supported targets (v1):
  - file: JSONL file, append-only

Planned targets (after PoC):
  - postgresql, mysql, mssql (NF5)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mdal.config import AuditConfig


class AuditWriteError(Exception):
    """Raised when an audit event cannot be written."""


class AuditWriter:
    """
    Write-only audit writer.

    Each event is written as a single JSON line (JSONL).
    The format is deliberately simple — the operator decides on rotation,
    archiving, and deletion.
    """

    def __init__(self, config: AuditConfig) -> None:
        self._config = config

    def write(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Writes an audit event.

        event_type: Short description of the event, e.g.:
            "check.passed", "check.failed", "retry.attempt",
            "retry.exhausted", "transform.applied", "escalation.admin"

        data: Event-specific fields — merged with timestamp and event_type
              into a single audit entry.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event":     event_type,
            **data,
        }

        if self._config.target == "file":
            self._write_file(entry)
        else:
            # Placeholder for DB targets — implemented after PoC validation
            raise NotImplementedError(
                f"Audit target '{self._config.target}' is not yet implemented. "
                f"Available: 'file'"
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
                f"Audit log could not be written ({path}): {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def audit_writer_from_config(config: AuditConfig) -> AuditWriter:
    return AuditWriter(config)
