"""Unit-Tests für connectivity_check() in mdal.proxy.startup (CR-Finding #6)."""

from unittest.mock import MagicMock, patch

import pytest

from mdal.config import ConfigError, MDALConfig
from mdal.proxy.startup import connectivity_check


def make_config(
    llm_url: str = "http://localhost:11434",
    embed_url: str = "http://localhost:11434",
    audit_target: str = "file",
    audit_path: str = "./audit/test.log",
    fallback_llm: dict | None = None,
) -> MDALConfig:
    data: dict = {
        "llm":                  {"url": llm_url,    "model": "llama3.1:8b"},
        "embedding":            {"url": embed_url,  "model": "nomic-embed-text"},
        "fingerprint_path":     "./fingerprints",
        "plugin_registry_path": "./plugins",
        "audit":                {"target": audit_target, "path": audit_path},
    }
    if fallback_llm:
        data["fallback_llm"] = fallback_llm
    return MDALConfig(**data)


def mock_adapter(healthy: bool) -> MagicMock:
    adapter = MagicMock()
    adapter.health_check.return_value = healthy
    return adapter


# ---------------------------------------------------------------------------
# Erfolgsfälle
# ---------------------------------------------------------------------------

class TestConnectivityCheckSuccess:
    def test_all_healthy_passes(self):
        config = make_config()
        with patch("mdal.proxy.startup.llm_adapter_from_config",   return_value=mock_adapter(True)), \
             patch("mdal.proxy.startup.embedding_adapter_from_config", return_value=mock_adapter(True)):
            connectivity_check(config)   # darf nicht werfen

    def test_file_audit_skips_db_check(self):
        config = make_config(audit_target="file")
        with patch("mdal.proxy.startup.llm_adapter_from_config",   return_value=mock_adapter(True)), \
             patch("mdal.proxy.startup.embedding_adapter_from_config", return_value=mock_adapter(True)):
            connectivity_check(config)   # kein DB-Treiber nötig


# ---------------------------------------------------------------------------
# Fehlerfälle
# ---------------------------------------------------------------------------

class TestConnectivityCheckFailures:
    def test_llm_unreachable_raises(self):
        config = make_config()
        with patch("mdal.proxy.startup.llm_adapter_from_config",   return_value=mock_adapter(False)), \
             patch("mdal.proxy.startup.embedding_adapter_from_config", return_value=mock_adapter(True)):
            with pytest.raises(ConfigError, match="LLM nicht erreichbar"):
                connectivity_check(config)

    def test_embedding_unreachable_raises(self):
        config = make_config()
        with patch("mdal.proxy.startup.llm_adapter_from_config",   return_value=mock_adapter(True)), \
             patch("mdal.proxy.startup.embedding_adapter_from_config", return_value=mock_adapter(False)):
            with pytest.raises(ConfigError, match="Embedding-Endpunkt nicht erreichbar"):
                connectivity_check(config)

    def test_both_unreachable_error_lists_both(self):
        config = make_config()
        with patch("mdal.proxy.startup.llm_adapter_from_config",   return_value=mock_adapter(False)), \
             patch("mdal.proxy.startup.embedding_adapter_from_config", return_value=mock_adapter(False)):
            with pytest.raises(ConfigError) as exc_info:
                connectivity_check(config)
            msg = str(exc_info.value)
            assert "LLM" in msg
            assert "Embedding" in msg

    def test_error_contains_url(self):
        config = make_config(llm_url="http://wrong-host:9999")
        with patch("mdal.proxy.startup.llm_adapter_from_config",   return_value=mock_adapter(False)), \
             patch("mdal.proxy.startup.embedding_adapter_from_config", return_value=mock_adapter(True)):
            with pytest.raises(ConfigError, match="wrong-host"):
                connectivity_check(config)


# ---------------------------------------------------------------------------
# Fallback-LLM (nicht blockernd)
# ---------------------------------------------------------------------------

class TestConnectivityCheckFallback:
    def test_fallback_unreachable_does_not_raise(self):
        """Fallback-LLM nicht erreichbar → nur Warning, kein Startabbruch."""
        config = make_config(
            fallback_llm={"url": "http://fallback:9999", "model": "gemma3"}
        )
        fallback_adapter = mock_adapter(False)
        with patch("mdal.proxy.startup.llm_adapter_from_config",   return_value=mock_adapter(True)), \
             patch("mdal.proxy.startup.embedding_adapter_from_config", return_value=mock_adapter(True)):
            # Für den Fallback-LLM-Adapter einen separaten Mock holen
            with patch("mdal.proxy.startup.llm_adapter_from_config",
                       side_effect=[mock_adapter(True), fallback_adapter]):
                connectivity_check(config)   # darf nicht werfen
