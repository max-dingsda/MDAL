"""
MDAL Server — CLI-Einstiegspunkt (mdal-server).

Startsequenz (F11):
  1. Konfiguration laden und validieren
  2. Laufzeitpfade prüfen
  3. Pipeline aufbauen
  4. Server starten

Konfigurationspfad:
  Umgebungsvariable MDAL_CONFIG (Default: config/mdal.yaml)

Umgebungsvariablen:
  MDAL_CONFIG  — Pfad zur YAML-Konfigurationsdatei
  MDAL_HOST    — Bind-Adresse (Default: 0.0.0.0)
  MDAL_PORT    — Port (Default: 8080)
  MDAL_LOG     — Log-Level (Default: INFO)
"""

from __future__ import annotations

import logging
import os
import sys

import uvicorn

from mdal.config import ConfigError, load_config, validate_runtime_paths
from mdal.proxy.app import app
from mdal.proxy.startup import build_audit_writer, build_pipeline, connectivity_check


def main() -> None:
    """Startet den MDAL-Proxy-Server."""
    log_level = os.environ.get("MDAL_LOG", "INFO").upper()
    logging.basicConfig(
        level  = log_level,
        format = "%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("mdal.server")

    config_path = os.environ.get("MDAL_CONFIG", "config/mdal.yaml")
    logger.info("Lade Konfiguration: %s", config_path)

    try:
        config = load_config(config_path)
        validate_runtime_paths(config)
    except ConfigError as exc:
        logger.critical("Konfigurationsfehler — Server startet nicht (F11): %s", exc)
        sys.exit(1)

    logger.info("Initialisiere MDAL-Pipeline …")
    try:
        pipeline = build_pipeline(config)
        audit    = build_audit_writer(config)
    except Exception as exc:
        logger.critical("Initialisierung fehlgeschlagen: %s", exc)
        sys.exit(1)

    logger.info("Prüfe Konnektivität zu externen Endpunkten …")
    try:
        connectivity_check(config)
    except ConfigError as exc:
        logger.critical("Konnektivitätsprüfung fehlgeschlagen — Server startet nicht (F11): %s", exc)
        sys.exit(1)

    # Abhängigkeiten in App-State ablegen (für Route-Handler verfügbar)
    app.state.pipeline         = pipeline
    app.state.audit            = audit
    app.state.default_language = config.language

    host = os.environ.get("MDAL_HOST", "0.0.0.0")
    port = int(os.environ.get("MDAL_PORT", "8080"))

    logger.info("MDAL-Proxy bereit auf %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level=log_level.lower())


if __name__ == "__main__":
    main()
