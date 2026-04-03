"""
MDAL Konfiguration — Laden, Validieren, Betriebsbereitschaft prüfen (F11).

Das System darf nur in vollständig konfiguriertem Zustand betrieben werden.
Ein unvollständiges Setup führt zu einer Fehlermeldung und verhindert den Betrieb.
Stiller Durchleitungsmodus ist nicht vorgesehen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class LLMConfig(BaseModel):
    url:     str
    model:   str
    timeout: int = 60
    api_key: str | None = None


class EmbeddingConfig(BaseModel):
    url:     str
    model:   str
    timeout: int = 30
    api_key: str | None = None


class AuditConfig(BaseModel):
    target:            Literal["file", "postgresql", "mysql", "mssql"]
    path:              str | None = None
    connection_string: str | None = None

    @model_validator(mode="after")
    def _require_target_params(self) -> AuditConfig:
        if self.target == "file" and not self.path:
            raise ValueError("audit.target = 'file' erfordert audit.path")
        if self.target in ("postgresql", "mysql", "mssql") and not self.connection_string:
            raise ValueError(
                f"audit.target = '{self.target}' erfordert audit.connection_string"
            )
        return self


class ChecksConfig(BaseModel):
    semantic:  bool = True
    structure: bool = True

    @model_validator(mode="after")
    def _at_least_one_active(self) -> ChecksConfig:
        # F18: Abschaltung aller Prüfungen gleichzeitig ist nicht zulässig.
        if not self.semantic and not self.structure:
            raise ValueError(
                "Mindestens eine Prüfung muss aktiv sein (F18). "
                "checks.semantic und checks.structure dürfen nicht gleichzeitig false sein."
            )
        return self


class NotifierConfig(BaseModel):
    log_path:    str | None = None
    webhook_url: str | None = None


class MDALConfig(BaseModel):
    llm:                   LLMConfig
    embedding:             EmbeddingConfig
    fingerprint_path:      str
    plugin_registry_path:  str
    audit:                 AuditConfig
    checks:                ChecksConfig      = Field(default_factory=ChecksConfig)
    notifier:              NotifierConfig    = Field(default_factory=NotifierConfig)
    language:              str               = "de"    # Standard-Sprache für Fingerprint-Lookup
    fallback_llm:          LLMConfig | None  = None   # F9
    max_retries:           int               = 3       # F5, konfigurierbar aber default 3

    @model_validator(mode="after")
    def _validate_completeness(self) -> MDALConfig:
        # F11: Das System muss vollständig konfiguriert sein.
        # Hier prüfen wir strukturelle Vollständigkeit der Config.
        # Die Existenz von Pfaden wird beim Start des Systems geprüft (mdal.startup).
        if self.max_retries < 1:
            raise ValueError("max_retries muss mindestens 1 sein")
        return self


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Wird geworfen wenn die Config unvollständig oder ungültig ist (F11)."""


def load_config(path: str | Path) -> MDALConfig:
    """
    Lädt und validiert die MDAL-Konfiguration aus einer YAML-Datei.

    Wirft ConfigError wenn:
    - Die Datei nicht gefunden wird
    - Pflichtfelder fehlen
    - Die Konfiguration F11 oder F18 verletzt

    Ein unvollständiges Setup führt zu Betriebsstopp — kein stiller Fallback.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Konfigurationsdatei nicht gefunden: {path}")

    try:
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Ungültiges YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Konfigurationsdatei ist leer oder kein Mapping: {path}")

    try:
        return MDALConfig(**raw)
    except Exception as exc:
        raise ConfigError(f"Konfigurationsfehler: {exc}") from exc


def validate_runtime_paths(config: MDALConfig) -> None:
    """
    Prüft zur Laufzeit ob konfigurierte Pfade tatsächlich existieren.
    Wird beim Systemstart aufgerufen — nicht beim Config-Laden.
    Trennung ermöglicht Unit-Tests ohne Dateisystem-Setup.
    """
    errors: list[str] = []

    fingerprint = Path(config.fingerprint_path)
    if not fingerprint.exists():
        errors.append(f"fingerprint_path existiert nicht: {fingerprint}")

    registry = Path(config.plugin_registry_path)
    if not registry.exists():
        errors.append(f"plugin_registry_path existiert nicht: {registry}")

    if config.audit.target == "file" and config.audit.path:
        audit_dir = Path(config.audit.path).parent
        if not audit_dir.exists():
            # Audit-Verzeichnis wird beim ersten Write angelegt — kein Fehler hier.
            pass

    if errors:
        raise ConfigError(
            "System nicht betriebsbereit (F11):\n" + "\n".join(f"  - {e}" for e in errors)
        )
