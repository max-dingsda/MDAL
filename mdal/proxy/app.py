"""
MDAL API-Proxy — FastAPI-Anwendung (F19).

Implementiert die OpenAI Chat Completions API-Oberfläche als Proxy:
  POST /v1/chat/completions — Hauptendpunkt, leitet durch die MDAL-Pipeline
  GET  /health              — Betriebszustand

Sprachauswahl (für Fingerprint-Lookup):
  1. Request-Header X-MDAL-Language (pro Request)
  2. Konfiguriertes Standardsprachkürzel (app.state.default_language)

Fehlerbehandlung:
  - RetryLimitError      → 503 (kein konformer Output produzierbar)
  - LLMUnavailableError  → 503 (Backend-LLM nicht erreichbar)
  - Fingerprint fehlt    → 503 (nicht konfiguriert)
  - Unbekannte Fehler    → 500

F6:  stream=True wird abgelehnt — MDAL prüft nur vollständige Outputs.
F15: Statusmeldungen werden geloggt (LoggingStatusReporter im Proxy-Betrieb).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

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


# ---------------------------------------------------------------------------
# Fehler-Handler
# ---------------------------------------------------------------------------

@app.exception_handler(RetryLimitError)
async def retry_limit_handler(request: Request, exc: RetryLimitError) -> JSONResponse:
    """F5: Retry-Limit erschöpft — 503 zurückgeben."""
    body = ErrorResponse.make(
        message    = str(exc),
        error_type = "retry_limit_exceeded",
        code       = "retry_limit_exceeded",
    )
    return JSONResponse(status_code=503, content=body.model_dump())


@app.exception_handler(LLMUnavailableError)
async def llm_unavailable_handler(request: Request, exc: LLMUnavailableError) -> JSONResponse:
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
    Betriebszustand des MDAL-Proxys.

    Gibt 200 zurück wenn der Proxy betriebsbereit ist.
    Gibt 503 zurück wenn der Backend-LLM nicht erreichbar ist.
    """
    pipeline: PipelineOrchestrator = request.app.state.pipeline
    if not pipeline._llm.health_check():
        raise HTTPException(
            status_code = 503,
            detail      = "Backend-LLM nicht erreichbar",
        )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Chat Completions — Hauptendpunkt
# ---------------------------------------------------------------------------

@app.post("/v1/chat/completions")
def chat_completions(
    body:    ChatCompletionRequest,
    request: Request,
) -> ChatCompletionResponse:
    """
    OpenAI-kompatibler Chat-Completions-Endpunkt.

    Ablauf:
      1. stream=True ablehnen (F6)
      2. Sprache bestimmen (Header > Config-Default)
      3. Pipeline ausführen
      4. Audit schreiben
      5. OpenAI-kompatible Antwort zurückgeben

    Fehler:
      - RetryLimitError      → 503 (exception_handler oben)
      - LLMUnavailableError  → 503 (exception_handler oben)
      - Fingerprint fehlt    → 503
    """
    # F6: kein Streaming
    if body.stream:
        raise HTTPException(
            status_code = 400,
            detail      = "stream=true wird von MDAL nicht unterstützt (F6: vollständige Outputs erforderlich)",
        )

    pipeline: PipelineOrchestrator = request.app.state.pipeline
    audit:    AuditWriter | None   = getattr(request.app.state, "audit", None)
    language: str = (
        request.headers.get("X-MDAL-Language")
        or request.app.state.default_language
    )

    messages = body.messages_as_dicts()

    # Audit: Anfrage empfangen
    if audit:
        audit.write("request_received", {
            "language":      language,
            "message_count": len(messages),
            "model":         body.model,
        })

    try:
        output = pipeline.process(messages=messages, language=language)
    except (KeyError, FileNotFoundError) as exc:
        logger.error("Fingerprint für Sprache '%s' nicht gefunden: %s", language, exc)
        raise HTTPException(
            status_code = 503,
            detail      = f"Kein Fingerprint für Sprache '{language}' konfiguriert",
        ) from exc

    # Audit: Antwort geliefert
    if audit:
        audit.write("response_delivered", {
            "language":        language,
            "output_length":   len(output),
        })

    return ChatCompletionResponse.from_content(output)
