"""
MDAL API proxy — FastAPI application (F19).

Implements the OpenAI Chat Completions API surface as a proxy:
  POST /v1/chat/completions — main endpoint, routes through the MDAL pipeline
  GET  /health              — operational status

Language selection (for fingerprint lookup):
  1. Request header X-MDAL-Language (per request)
  2. Configured default language code (app.state.default_language)

Error handling:
  - RetryLimitError      → 503 (no conforming output producible)
  - LLMUnavailableError  → 503 (backend LLM not reachable)
  - Fingerprint missing  → 503 (not configured)
  - Unknown errors       → 500

F6:  stream=True is rejected — MDAL only processes complete outputs.
F15: Status messages are logged (LoggingStatusReporter in proxy operation).
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any
import yaml
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse

from mdal.audit import AuditWriter
from mdal.llm.adapter import LLMUnavailableError
from mdal.pipeline import PipelineOrchestrator
from mdal.proxy.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ErrorResponse,
)
from mdal.retry import RetryLimitError

logger = logging.getLogger(__name__)

app = FastAPI(
    title       = "MDAL Proxy",
    description = "Model-agnostic Delivery Assurance Layer — OpenAI-compatible proxy",
    version     = "0.1.0",
)

# State for Start/Stop Maintenance Mode
app.state.is_active = True

# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(RetryLimitError)
async def retry_limit_handler(request: Request, exc: RetryLimitError) -> JSONResponse:
    logger.warning("Escalation triggered (F5): %s", exc)
    """F5: Retry limit exhausted — return 503."""
    body = ErrorResponse.make(
        message    = str(exc),
        error_type = "retry_limit_exceeded",
        code       = "retry_limit_exceeded",
    )
    return JSONResponse(status_code=503, content=body.model_dump())


@app.exception_handler(LLMUnavailableError)
async def llm_unavailable_handler(request: Request, exc: LLMUnavailableError) -> JSONResponse:
    logger.error("Backend LLM unavailable: %s", exc)
    body = ErrorResponse.make(
        message    = str(exc),
        error_type = "service_unavailable",
        code       = "llm_unavailable",
    )
    return JSONResponse(status_code=503, content=body.model_dump())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health(request: Request) -> dict[str, str]:
    """
    Operational status of the MDAL proxy.

    Returns 200 when the proxy is operational.
    Returns 503 when the backend LLM is not reachable.
    """
    if not getattr(request.app.state, "is_active", True) or not getattr(request.app.state, "pipeline", None):
        raise HTTPException(status_code=503, detail="MDAL Proxy im Wartungsmodus / Nicht konfiguriert")

    pipeline: PipelineOrchestrator = request.app.state.pipeline
    if not pipeline._llm.health_check():
        raise HTTPException(
            status_code = 503,
            detail      = "Backend LLM nicht erreichbar",
        )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Configuration UI & API
# ---------------------------------------------------------------------------

@app.get("/config", response_class=HTMLResponse)
def get_config_ui():
    """Serves the Configuration HTML UI."""
    for p in ["config/config.html", "templates/config.html"]:
        html_path = Path(p)
        if html_path.exists():
            return html_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>Error: config.html not found</h1>", status_code=404)


@app.get("/api/config")
def get_config_api():
    """Returns the current mdal.yaml configuration as JSON."""
    yaml_path = Path("config/mdal.yaml")
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


@app.post("/api/config")
async def save_config_api(request: Request):
    """Saves the JSON payload back to mdal.yaml."""
    data = await request.json()
    yaml_path = Path("config/mdal.yaml")
    
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
        
    config["llm"] = data.get("llm", {})
    config["embedding"] = data.get("embedding", {})
    config["audit"] = data.get("audit", {})
    config["checks"] = data.get("checks", {})
    config["notifier"] = data.get("notifier", {})
    
    if data.get("fingerprint_path"):
        config["fingerprint_path"] = data.get("fingerprint_path")
    if data.get("plugin_registry_path"):
        config["plugin_registry_path"] = data.get("plugin_registry_path")
    if data.get("env_start_cmd"):
        config["env_start_cmd"] = data.get("env_start_cmd")
        
    # Clean up empty strings to None for correct YAML output
    for key in ["llm", "embedding"]:
        if "api_key" in config.get(key, {}) and not config[key]["api_key"]:
            config[key].pop("api_key", None)
            
    if "connection_string" in config.get("audit", {}) and not config["audit"]["connection_string"]:
        config["audit"].pop("connection_string", None)
        
    if "webhook_url" in config.get("notifier", {}) and not config["notifier"]["webhook_url"]:
        config["notifier"].pop("webhook_url", None)
        
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
    return {"status": "success"}


@app.get("/api/browse-folder")
def browse_folder_api():
    """Opens a native Windows folder dialog and returns the path."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        folder = filedialog.askdirectory(title="Ordner auswählen")
        root.destroy()
        
        return {"folder": folder}
    except Exception as e:
        logger.error("Error opening folder dialog: %s", e)
        return {"folder": ""}

@app.post("/api/proxy/state")
async def set_proxy_state(request: Request):
    """Toggles the maintenance mode of the proxy."""
    data = await request.json()
    target_active = data.get("active", True)
    
    if target_active:
        try:
            from mdal.config import load_config, validate_runtime_paths
            from mdal.proxy.startup import build_pipeline, build_audit_writer, connectivity_check
            from mdal.notifier import AdminNotifier
            import os
            
            config_path = os.environ.get("MDAL_CONFIG", "config/mdal.yaml")
            config = load_config(config_path)
            validate_runtime_paths(config)
            pipeline = build_pipeline(config)
            audit = build_audit_writer(config)
            connectivity_check(config)
            
            request.app.state.pipeline = pipeline
            request.app.state.audit = audit
            request.app.state.default_language = config.language
            request.app.state.notifier = AdminNotifier(config.notifier)
            request.app.state.is_active = True
            logger.info("Proxy-Status geändert: AKTIV (Pipeline erfolgreich geladen)")
            return {"status": "success", "is_active": True}
        except Exception as e:
            logger.error("Proxy-Start fehlgeschlagen: %s", e)
            return JSONResponse(status_code=400, content={"status": "error", "message": str(e)})
    else:
        request.app.state.is_active = False
        logger.info("Proxy-Status geändert: GESTOPPT (Wartungsmodus)")
        return {"status": "success", "is_active": False}

@app.post("/api/trainer/start")
def start_trainer_api():
    """Spawns the trainer in a new, independent Windows terminal."""
    try:
        yaml_path = Path("config/mdal.yaml")
        env_cmd = ""
        if yaml_path.exists():
            with open(yaml_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                env_cmd = config.get("env_start_cmd", "")
        
        cmds = []
        if env_cmd:
            cmds.append(env_cmd)
            cmds.append("timeout /t 3 /nobreak")
        
        # Standard Commercial-Test Trainer Befehl
        cmds.append("python -m mdal.trainer.trainer --config config/trainer_commercial.yaml --input manuelle_tests/semantik/gpt4o_chats.json --language de")
        
        # Befehle mit '&' für die Windows-Konsole verketten
        full_cmd = " & ".join(cmds)
        logger.info(f"Starte Trainer in neuem Fenster: {full_cmd}")
        
        # creationflags=subprocess.CREATE_NEW_CONSOLE öffnet ein natives Windows CMD!
        subprocess.Popen(full_cmd, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        return {"status": "success"}
    except Exception as e:
        logger.error("Fehler beim Starten des Trainers: %s", e)
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Chat completions — main endpoint
# ---------------------------------------------------------------------------

@app.post("/v1/chat/completions")
def chat_completions(
    body:    ChatCompletionRequest,
    request: Request,
) -> ChatCompletionResponse:
    """
    OpenAI-compatible chat completions endpoint.

    Flow:
      1. Reject stream=True (F6)
      2. Determine language (header > config default)
      3. Run pipeline
      4. Write audit entry
      5. Return OpenAI-compatible response

    Errors:
      - RetryLimitError      → 503 (exception_handler above)
      - LLMUnavailableError  → 503 (exception_handler above)
      - Fingerprint missing  → 503
    """
    if not getattr(request.app.state, "is_active", True):
        raise HTTPException(
            status_code=503,
            detail="MDAL Proxy ist momentan gestoppt (Wartungsmodus)."
        )

    # F6: no streaming
    if body.stream:
        raise HTTPException(
            status_code = 400,
            detail      = "stream=true wird von MDAL nicht unterstützt (F6: vollständige Outputs zwingend)",
        )

    pipeline: PipelineOrchestrator = request.app.state.pipeline
    audit:    AuditWriter | None   = getattr(request.app.state, "audit", None)
    language: str = (
        request.headers.get("X-MDAL-Language")
        or request.app.state.default_language
    )

    messages = body.messages_as_dicts()

    # Audit: request received
    if audit:
        audit.write("request_received", {
            "language":      language,
            "message_count": len(messages),
            "model":         body.model,
        })

    logger.info("Processing request for model '%s' in language '%s'", body.model, language)

    try:
        output = pipeline.process(messages=messages, language=language)
    except (KeyError, FileNotFoundError) as exc:
        logger.error("Fingerprint for language '%s' not found: %s", language, exc)
        raise HTTPException(
            status_code = 503,
            detail      = f"Kein Fingerprint für Sprache '{language}' konfiguriert",
        ) from exc

    # Audit: response delivered
    if audit:
        audit.write("response_delivered", {
            "language":      language,
            "output_length": len(output),
        })

    logger.info("Successfully processed request in language '%s'", language)

    return ChatCompletionResponse.from_content(output)
