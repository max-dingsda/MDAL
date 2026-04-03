"""
Komponenten-Initialisierung beim Server-Start.

build_pipeline() ist die zentrale Factory-Funktion:
Sie instantiiert alle MDAL-Komponenten aus einer geladenen MDALConfig
und verdrahtet sie zur PipelineOrchestrator-Instanz.

Trennungsprinzip:
  - load_config / validate_runtime_paths: Pflicht vor build_pipeline
  - build_pipeline selbst macht keine I/O-Checks — das ist Sache der Startup-Phase

F11: System startet nur in vollständig konfiguriertem Zustand.
"""

from __future__ import annotations

from mdal.audit import AuditWriter
from mdal.config import MDALConfig
from mdal.fingerprint.store import FingerprintStore
from mdal.llm.adapter import embedding_adapter_from_config, llm_adapter_from_config
from mdal.notifier import AdminNotifier
from mdal.pipeline import PipelineOrchestrator
from mdal.plugins.registry import PluginRegistry
from mdal.retry import RetryController
from mdal.status import LoggingStatusReporter
from mdal.transformer import RuleBasedToneTransformer
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
    transformer = RuleBasedToneTransformer()

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
