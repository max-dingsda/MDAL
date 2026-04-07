"""
MDAL configuration — loading, validation, and operational readiness check (F11).

The system may only be operated in a fully configured state.
An incomplete setup raises an error and prevents operation.
Silent passthrough mode is not provided.
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
            raise ValueError("audit.target = 'file' requires audit.path")
        if self.target in ("postgresql", "mysql", "mssql") and not self.connection_string:
            raise ValueError(
                f"audit.target = '{self.target}' requires audit.connection_string"
            )
        return self


class ChecksConfig(BaseModel):
    semantic:  bool = True
    structure: bool = True

    @model_validator(mode="after")
    def _at_least_one_active(self) -> ChecksConfig:
        # F18: disabling all checks simultaneously is not permitted.
        if not self.semantic and not self.structure:
            raise ValueError(
                "At least one check must be active (F18). "
                "checks.semantic and checks.structure must not both be false."
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
    language:              str               = "de"    # default language for fingerprint lookup
    fallback_llm:          LLMConfig | None  = None   # F9
    max_retries:           int               = 2       # F5: max 3 attempts total (1 initial + 2 refinements)

    @model_validator(mode="after")
    def _validate_completeness(self) -> MDALConfig:
        # F11: the system must be fully configured.
        # Here we check structural completeness of the config.
        # Path existence is verified at system startup (mdal.startup).
        if self.max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        return self


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when the config is incomplete or invalid (F11)."""


def load_config(path: str | Path) -> MDALConfig:
    """
    Loads and validates the MDAL configuration from a YAML file.

    Raises ConfigError when:
    - the file is not found
    - required fields are missing
    - the configuration violates F11 or F18

    An incomplete setup causes an operational stop — no silent fallback.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Configuration file is empty or not a mapping: {path}")

    try:
        return MDALConfig(**raw)
    except Exception as exc:
        raise ConfigError(f"Configuration error: {exc}") from exc


def validate_runtime_paths(config: MDALConfig) -> None:
    """
    Verifies at runtime that configured paths actually exist.
    Called at system startup — not during config loading.
    Separation enables unit tests without a filesystem setup.
    """
    errors: list[str] = []

    fingerprint = Path(config.fingerprint_path)
    if not fingerprint.exists():
        errors.append(f"fingerprint_path does not exist: {fingerprint}")

    registry = Path(config.plugin_registry_path)
    if not registry.exists():
        errors.append(f"plugin_registry_path does not exist: {registry}")

    if config.audit.target == "file" and config.audit.path:
        audit_dir = Path(config.audit.path).parent
        if not audit_dir.exists():
            # Audit directory is created on first write — not an error here.
            pass

    if errors:
        raise ConfigError(
            "System not operational (F11):\n" + "\n".join(f"  - {e}" for e in errors)
        )
