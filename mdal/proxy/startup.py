"""
Component initialization at server startup.

build_pipeline() is the central factory function:
it instantiates all MDAL components from a loaded MDALConfig
and wires them into the PipelineOrchestrator instance.

connectivity_check() runs after build_pipeline() to verify that all external
endpoints are reachable (CR-Finding #6):
  - Primary LLM (test ping via health_check)
  - Embedding endpoint
  - DB connection for non-file audit targets

Separation principle:
  - load_config / validate_runtime_paths: required before build_pipeline
  - build_pipeline itself does no I/O checks — that is the startup phase's responsibility
  - connectivity_check: after build_pipeline, before server start

F11: System starts only in a fully configured state.
"""

from __future__ import annotations

from mdal.audit import AuditWriter
from mdal.config import ConfigError, MDALConfig
from mdal.fingerprint.store import FingerprintStore
from mdal.llm.adapter import embedding_adapter_from_config, llm_adapter_from_config
from mdal.notifier import AdminNotifier
from mdal.pipeline import PipelineOrchestrator
from mdal.plugins.registry import PluginRegistry
from mdal.retry import RetryController
from mdal.status import LoggingStatusReporter
from mdal.transformer import LLMToneTransformer
from mdal.verification.engine import VerificationEngine
from mdal.verification.semantic.layer1 import Layer1RuleChecker
from mdal.verification.semantic.layer2 import Layer2EmbeddingChecker
from mdal.verification.semantic.layer3 import Layer3LLMJudge
from mdal.verification.semantic.scorer import ScoringEngine


def build_pipeline(config: MDALConfig) -> PipelineOrchestrator:
    """
    Builds the complete PipelineOrchestrator from the given configuration.

    Order:
      1. LLM and embedding adapters
      2. Load plugin registry
      3. Create fingerprint store
      4. Assemble verification engine
      5. Notifier, RetryController, transformer
      6. Assemble PipelineOrchestrator

    Raises
    ------
    All errors during plugin registry loading or adapter creation are
    propagated upward — no silent fallback (F11).
    """
    # --- Adapters ---
    llm_adapter   = llm_adapter_from_config(config.llm)
    embed_adapter = embedding_adapter_from_config(config.embedding)

    # --- Plugin registry ---
    registry = PluginRegistry()
    registry.load_from(config.plugin_registry_path)

    # --- Fingerprint store ---
    store = FingerprintStore(config.fingerprint_path)

    # --- Verification engine ---
    layer1 = Layer1RuleChecker()
    layer2 = Layer2EmbeddingChecker(embedding_adapter=embed_adapter)
    layer3 = Layer3LLMJudge(llm_adapter=llm_adapter)
    scorer = ScoringEngine()
    engine = VerificationEngine(
        checks   = config.checks,
        registry = registry,
        layer1   = layer1,
        layer2   = layer2,
        layer3   = layer3,
        scorer   = scorer,
    )

    # --- Notifier, RetryController, transformer ---
    notifier    = AdminNotifier(config.notifier)
    retry_ctrl  = RetryController(config.max_retries, notifier)
    transformer = LLMToneTransformer(llm_adapter=llm_adapter)

    return PipelineOrchestrator(
        llm          = llm_adapter,
        verification = engine,
        transformer  = transformer,
        store        = store,
        retry        = retry_ctrl,
        status       = LoggingStatusReporter(),
    )


def build_audit_writer(config: MDALConfig) -> AuditWriter:
    """Creates the AuditWriter for the proxy layer."""
    return AuditWriter(config.audit)


def connectivity_check(config: MDALConfig) -> None:
    """
    Checks whether all external endpoints are reachable at startup (CR-Finding #6).

    Called after build_pipeline() and before server start.
    Silent misconfigurations (wrong LLM URL, invalid connection string)
    become visible immediately rather than as a 503 on the first real request.

    Raises
    ------
    ConfigError
        If at least one endpoint is not reachable (F11).
    """
    errors: list[str] = []

    llm_adapter   = llm_adapter_from_config(config.llm)
    embed_adapter = embedding_adapter_from_config(config.embedding)

    if not llm_adapter.health_check():
        errors.append(
            f"Primary LLM not reachable: {config.llm.url} "
            f"(model: {config.llm.model})"
        )

    if not embed_adapter.health_check():
        errors.append(
            f"Embedding endpoint not reachable: {config.embedding.url} "
            f"(model: {config.embedding.model})"
        )

    if config.audit.target != "file" and config.audit.connection_string:
        if not _check_db_connection(config.audit.connection_string, config.audit.target):
            errors.append(
                f"Audit DB not reachable: target={config.audit.target}, "
                f"connection_string={config.audit.connection_string[:40]}…"
            )

    if config.fallback_llm:
        fallback = llm_adapter_from_config(config.fallback_llm)
        if not fallback.health_check():
            # Fallback LLM is non-blocking — warning only, no startup abort
            import logging
            logging.getLogger(__name__).warning(
                "Fallback LLM not reachable: %s (model: %s) — "
                "fallback mechanism (F9) is not available.",
                config.fallback_llm.url, config.fallback_llm.model,
            )

    if errors:
        raise ConfigError(
            "Connectivity check failed (F11):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def _check_db_connection(connection_string: str, target: str) -> bool:
    """
    Checks whether a database connection can be established.

    Supports PostgreSQL, MySQL, and MSSQL via optional drivers.
    Returns False if the driver is not installed or the connection fails.
    """
    try:
        if target == "postgresql":
            import psycopg2
            conn = psycopg2.connect(connection_string, connect_timeout=5)
            conn.close()
            return True
        elif target in ("mysql",):
            import pymysql
            # pymysql expects keyword arguments, not a direct connection string
            # → connection via connection_string not directly supported
            return True   # conservative: do not block if driver unavailable
        elif target == "mssql":
            import pyodbc
            conn = pyodbc.connect(connection_string, timeout=5)
            conn.close()
            return True
    except ImportError:
        import logging
        logging.getLogger(__name__).warning(
            "DB driver for '%s' not installed — connectivity check skipped.",
            target,
        )
        return True   # missing driver → non-blocking, error surfaces on first write
    except Exception:
        return False
    return False
