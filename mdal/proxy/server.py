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
  MDAL_PORT    — port (default: 8080)
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
    logger.info("Loading configuration: %s", config_path)

    try:
        config = load_config(config_path)
        validate_runtime_paths(config)
    except ConfigError as exc:
        logger.critical("Configuration error — server will not start (F11): %s", exc)
        sys.exit(1)

    logger.info("Initializing MDAL pipeline …")
    try:
        pipeline = build_pipeline(config)
        audit    = build_audit_writer(config)
    except Exception as exc:
        logger.critical("Initialization failed: %s", exc)
        sys.exit(1)

    logger.info("Checking connectivity to external endpoints …")
    try:
        connectivity_check(config)
    except ConfigError as exc:
        logger.critical("Connectivity check failed — server will not start (F11): %s", exc)
        sys.exit(1)

    # Store dependencies in app state (available to route handlers)
    app.state.pipeline         = pipeline
    app.state.audit            = audit
    app.state.default_language = config.language

    # F4/F11: Global exception handler for technical crashes
    notifier = AdminNotifier(config.notifier)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled technical error: %s", exc, exc_info=True)
        notifier.notify_technical_crash(
            error=type(exc).__name__,
            details=str(exc),
            traceback_str=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=503,
            content={"detail": "Dienst nicht verfügbar (Technischer Fehler)"}
        )

    host = os.environ.get("MDAL_HOST", "0.0.0.0")
    port = int(os.environ.get("MDAL_PORT", "8080"))

    logger.info("MDAL proxy ready on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level=log_level.lower())


if __name__ == "__main__":
    main()
