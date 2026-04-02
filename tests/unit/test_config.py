"""Unit-Tests für mdal.config — Laden, Validieren, F11, F18."""

from pathlib import Path

import pytest
import yaml

from mdal.config import (
    ConfigError,
    MDALConfig,
    load_config,
    validate_runtime_paths,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CONFIG: dict = {
    "llm":       {"url": "http://localhost:11434", "model": "llama3.2"},
    "embedding": {"url": "http://localhost:11434", "model": "nomic-embed-text"},
    "fingerprint_path":     "./fingerprints/default",
    "plugin_registry_path": "./plugins",
    "audit": {"target": "file", "path": "./audit/test.log"},
    "checks": {"semantic": True, "structure": True},
}


def write_yaml(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "mdal.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Gültige Konfigurationen
# ---------------------------------------------------------------------------

class TestValidConfig:
    def test_loads_minimal_valid_config(self, tmp_path):
        p = write_yaml(tmp_path, VALID_CONFIG)
        config = load_config(p)
        assert config.llm.model == "llama3.2"
        assert config.embedding.model == "nomic-embed-text"

    def test_defaults_applied(self, tmp_path):
        p = write_yaml(tmp_path, VALID_CONFIG)
        config = load_config(p)
        assert config.checks.semantic is True
        assert config.checks.structure is True
        assert config.max_retries == 3

    def test_optional_fallback_llm_absent(self, tmp_path):
        p = write_yaml(tmp_path, VALID_CONFIG)
        config = load_config(p)
        assert config.fallback_llm is None

    def test_optional_fallback_llm_present(self, tmp_path):
        data = {**VALID_CONFIG, "fallback_llm": {"url": "http://localhost:11434", "model": "gemma2"}}
        p = write_yaml(tmp_path, data)
        config = load_config(p)
        assert config.fallback_llm is not None
        assert config.fallback_llm.model == "gemma2"

    def test_only_semantic_check_active(self, tmp_path):
        data = {**VALID_CONFIG, "checks": {"semantic": True, "structure": False}}
        p = write_yaml(tmp_path, data)
        config = load_config(p)
        assert config.checks.structure is False

    def test_only_structure_check_active(self, tmp_path):
        data = {**VALID_CONFIG, "checks": {"semantic": False, "structure": True}}
        p = write_yaml(tmp_path, data)
        config = load_config(p)
        assert config.checks.semantic is False


# ---------------------------------------------------------------------------
# F18 — Beide Prüfungen gleichzeitig deaktiviert ist verboten
# ---------------------------------------------------------------------------

class TestF18BothChecksDisabled:
    def test_both_checks_false_raises(self, tmp_path):
        data = {**VALID_CONFIG, "checks": {"semantic": False, "structure": False}}
        p = write_yaml(tmp_path, data)
        with pytest.raises(ConfigError, match="F18"):
            load_config(p)


# ---------------------------------------------------------------------------
# Pflichtfelder fehlen
# ---------------------------------------------------------------------------

class TestMissingRequiredFields:
    def test_missing_llm_raises(self, tmp_path):
        data = {k: v for k, v in VALID_CONFIG.items() if k != "llm"}
        p = write_yaml(tmp_path, data)
        with pytest.raises(ConfigError):
            load_config(p)

    def test_missing_embedding_raises(self, tmp_path):
        data = {k: v for k, v in VALID_CONFIG.items() if k != "embedding"}
        p = write_yaml(tmp_path, data)
        with pytest.raises(ConfigError):
            load_config(p)

    def test_missing_fingerprint_path_raises(self, tmp_path):
        data = {k: v for k, v in VALID_CONFIG.items() if k != "fingerprint_path"}
        p = write_yaml(tmp_path, data)
        with pytest.raises(ConfigError):
            load_config(p)

    def test_missing_audit_raises(self, tmp_path):
        data = {k: v for k, v in VALID_CONFIG.items() if k != "audit"}
        p = write_yaml(tmp_path, data)
        with pytest.raises(ConfigError):
            load_config(p)


# ---------------------------------------------------------------------------
# Audit-Konfiguration
# ---------------------------------------------------------------------------

class TestAuditConfig:
    def test_file_target_without_path_raises(self, tmp_path):
        data = {**VALID_CONFIG, "audit": {"target": "file"}}
        p = write_yaml(tmp_path, data)
        with pytest.raises(ConfigError, match="audit.path"):
            load_config(p)

    def test_postgresql_without_connection_string_raises(self, tmp_path):
        data = {**VALID_CONFIG, "audit": {"target": "postgresql"}}
        p = write_yaml(tmp_path, data)
        with pytest.raises(ConfigError, match="connection_string"):
            load_config(p)

    def test_postgresql_with_connection_string_valid(self, tmp_path):
        data = {**VALID_CONFIG, "audit": {
            "target": "postgresql",
            "connection_string": "postgresql://user:pass@host/db",
        }}
        p = write_yaml(tmp_path, data)
        config = load_config(p)
        assert config.audit.target == "postgresql"


# ---------------------------------------------------------------------------
# Dateisystem-Fehler
# ---------------------------------------------------------------------------

class TestFileErrors:
    def test_missing_config_file_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="nicht gefunden"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        p = tmp_path / "mdal.yaml"
        p.write_text(": invalid: yaml: {{{", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)

    def test_empty_file_raises(self, tmp_path):
        p = tmp_path / "mdal.yaml"
        p.write_text("", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)


# ---------------------------------------------------------------------------
# validate_runtime_paths
# ---------------------------------------------------------------------------

class TestValidateRuntimePaths:
    def test_raises_when_fingerprint_path_missing(self, tmp_path):
        data = {
            **VALID_CONFIG,
            "fingerprint_path":     str(tmp_path / "nonexistent_fingerprint"),
            "plugin_registry_path": str(tmp_path / "plugins"),
        }
        p = write_yaml(tmp_path, data)
        config = load_config(p)
        (tmp_path / "plugins").mkdir()
        with pytest.raises(ConfigError, match="fingerprint_path"):
            validate_runtime_paths(config)

    def test_raises_when_plugin_registry_missing(self, tmp_path):
        fp_dir = tmp_path / "fingerprints"
        fp_dir.mkdir()
        data = {
            **VALID_CONFIG,
            "fingerprint_path":     str(fp_dir),
            "plugin_registry_path": str(tmp_path / "nonexistent_plugins"),
        }
        p = write_yaml(tmp_path, data)
        config = load_config(p)
        with pytest.raises(ConfigError, match="plugin_registry_path"):
            validate_runtime_paths(config)

    def test_passes_when_all_paths_exist(self, tmp_path):
        fp_dir  = tmp_path / "fingerprints"
        reg_dir = tmp_path / "plugins"
        fp_dir.mkdir()
        reg_dir.mkdir()
        data = {
            **VALID_CONFIG,
            "fingerprint_path":     str(fp_dir),
            "plugin_registry_path": str(reg_dir),
        }
        p = write_yaml(tmp_path, data)
        config = load_config(p)
        validate_runtime_paths(config)   # darf nicht werfen
