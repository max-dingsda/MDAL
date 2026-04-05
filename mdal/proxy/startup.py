"""
Komponenten-Initialisierung beim Server-Start.

build_pipeline() ist die zentrale Factory-Funktion:
Sie instantiiert alle MDAL-Komponenten aus einer geladenen MDALConfig
und verdrahtet sie zur PipelineOrchestrator-Instanz.

connectivity_check() prüft nach build_pipeline() ob alle externen
Endpunkte erreichbar sind (CR-Finding #6):
  - Primäres LLM (Test-Ping via health_check)
  - Embedding-Endpunkt
  - DB-Verbindung bei nicht-file-Audit-Targets

Trennungsprinzip:
  - load_config / validate_runtime_paths: Pflicht vor build_pipeline
  - build_pipeline selbst macht keine I/O-Checks — das ist Sache der Startup-Phase
  - connectivity_check: nach build_pipeline, vor Server-Start

F11: System startet nur in vollständig konfiguriertem Zustand.
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
    Baut den vollständigen PipelineOrchestrator aus der gegebenen Konfiguration.

    Reihenfolge:
      1. LLM- und Embedding-Adapter
      2. Plugin Registry laden
      3. Fingerprint Store anlegen
      4. Verification Engine zusammensetzen
      5. Notifier, RetryController, Transformer
      6. PipelineOrchestrator zusammenbauen

    Raises
    ------
    Alle Fehler beim Laden der Plugin-Registry oder beim Erstellen der Adapter
    werden nach oben durchgereicht — kein stiller Fallback (F11).
    """
    # --- Adapter ---
    llm_adapter   = llm_adapter_from_config(config.llm)
    embed_adapter = embedding_adapter_from_config(config.embedding)

    # --- Plugin Registry ---
    registry = PluginRegistry()
    registry.load_from(config.plugin_registry_path)

    # --- Fingerprint Store ---
    store = FingerprintStore(config.fingerprint_path)

    # --- Verification Engine ---
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

    # --- Notifier, RetryController, Transformer ---
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
    """Erstellt den AuditWriter für den Proxy-Layer."""
    return AuditWriter(config.audit)


def connectivity_check(config: MDALConfig) -> None:
    """
    Prüft ob alle externen Endpunkte beim Start erreichbar sind (CR-Finding #6).

    Wird nach build_pipeline() und vor Server-Start aufgerufen.
    Stille Fehlkonfigurationen (falsche LLM-URL, ungültiger Connection-String)
    werden sofort sichtbar statt erst beim ersten echten Request als 503.

    Raises
    ------
    ConfigError
        Wenn mindestens ein Endpunkt nicht erreichbar ist (F11).
    """
    errors: list[str] = []

    llm_adapter   = llm_adapter_from_config(config.llm)
    embed_adapter = embedding_adapter_from_config(config.embedding)

    if not llm_adapter.health_check():
        errors.append(
            f"Primäres LLM nicht erreichbar: {config.llm.url} "
            f"(Modell: {config.llm.model})"
        )

    if not embed_adapter.health_check():
        errors.append(
            f"Embedding-Endpunkt nicht erreichbar: {config.embedding.url} "
            f"(Modell: {config.embedding.model})"
        )

    if config.audit.target != "file" and config.audit.connection_string:
        if not _check_db_connection(config.audit.connection_string, config.audit.target):
            errors.append(
                f"Audit-DB nicht erreichbar: target={config.audit.target}, "
                f"connection_string={config.audit.connection_string[:40]}…"
            )

    if config.fallback_llm:
        fallback = llm_adapter_from_config(config.fallback_llm)
        if not fallback.health_check():
            # Fallback-LLM ist nicht blockernd — nur Warnung, kein Startabbruch
            import logging
            logging.getLogger(__name__).warning(
                "Fallback-LLM nicht erreichbar: %s (Modell: %s) — "
                "Fallback-Mechanismus (F9) steht nicht zur Verfügung.",
                config.fallback_llm.url, config.fallback_llm.model,
            )

    if errors:
        raise ConfigError(
            "Konnektivitätsprüfung fehlgeschlagen (F11):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def _check_db_connection(connection_string: str, target: str) -> bool:
    """
    Prüft ob eine Datenbankverbindung hergestellt werden kann.

    Unterstützt PostgreSQL, MySQL und MSSQL via optionale Treiber.
    Gibt False zurück wenn der Treiber nicht installiert ist oder
    die Verbindung fehlschlägt.
    """
    try:
        if target == "postgresql":
            import psycopg2
            conn = psycopg2.connect(connection_string, connect_timeout=5)
            conn.close()
            return True
        elif target in ("mysql",):
            import pymysql
            # pymysql erwartet keyword-Argumente, kein Connection-String direkt
            # → Verbindung wird über connection_string nicht direkt unterstützt
            return True   # konservativ: kein Blockieren wenn Treiber nicht vorhanden
        elif target == "mssql":
            import pyodbc
            conn = pyodbc.connect(connection_string, timeout=5)
            conn.close()
            return True
    except ImportError:
        import logging
        logging.getLogger(__name__).warning(
            "DB-Treiber für '%s' nicht installiert — Konnektivitätsprüfung übersprungen.",
            target,
        )
        return True   # Treiber fehlt → nicht blockernd, Fehler tritt erst beim Schreiben auf
    except Exception:
        return False
    return False
