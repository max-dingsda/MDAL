"""
MDAL server — CLI entry point (mdal-server).

Startup sequence (F11):
  1. Load and validate configuration
  2. Verify runtime paths
  3. Build pipeline
  4. Start server

Configuration path:
  Environment variable MDAL_CONFIG (default: config/mdal.yaml)

Environment variables:
  MDAL_CONFIG  — path to the YAML configuration file
  MDAL_HOST    — bind address (default: 0.0.0.0)
  MDAL_PORT    — port (default: 6969)
  MDAL_LOG     — log level (default: INFO)
"""

from __future__ import annotations

import logging
import os
import sys
import traceback

import uvicorn
from fastapi import Request
from fastapi.responses import JSONResponse

from mdal.config import ConfigError, load_config, validate_runtime_paths
from mdal.notifier import AdminNotifier
from mdal.proxy.app import app
from mdal.proxy.startup import build_audit_writer, build_pipeline, connectivity_check


def main() -> None:
    """Starts the MDAL proxy server."""
    log_level = os.environ.get("MDAL_LOG", "INFO").upper()
    logging.basicConfig(
        level  = log_level,
        format = "%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("mdal.server")

    config_path = os.environ.get("MDAL_CONFIG", "config/mdal.yaml")
    host = os.environ.get("MDAL_HOST", "0.0.0.0")
    port = int(os.environ.get("MDAL_PORT", "6969"))

    # Start with a safe default state
    app.state.pipeline = None
    app.state.audit = None
    app.state.default_language = "de"
    app.state.is_active = False
    app.state.notifier = None

    logger.info("Loading configuration: %s", config_path)
    try:
        config = load_config(config_path)
        validate_runtime_paths(config)
        logger.info("Initializing MDAL pipeline …")
        pipeline = build_pipeline(config)
        audit    = build_audit_writer(config)
        logger.info("Checking connectivity to external endpoints …")
        connectivity_check(config)

        app.state.pipeline         = pipeline
        app.state.audit            = audit
        app.state.default_language = config.language
        app.state.notifier         = AdminNotifier(config.notifier)
        app.state.is_active        = True
    except Exception as exc:
        logger.warning("Startup checks failed: %s", exc)
        logger.warning(
            "\033[1;31m>>> MDAL is starting in CONFIGURATION MODE. Please visit http://localhost:%d/config <<<\033[0m", port
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled technical error: %s", exc, exc_info=True)
        notifier = getattr(request.app.state, "notifier", None)
        if notifier:
            notifier.notify_technical_crash(
                error=type(exc).__name__,
                details=str(exc),
                traceback_str=traceback.format_exc(),
            )
        return JSONResponse(
            status_code=503,
            content={"detail": "Dienst nicht verfügbar (Technischer Fehler)"}
        )

    logger.info("MDAL proxy ready on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level=log_level.lower())


if __name__ == "__main__":
    main()
