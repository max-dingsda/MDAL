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
    pipeline: PipelineOrchestrator = request.app.state.pipeline
    if not pipeline._llm.health_check():
        raise HTTPException(
            status_code = 503,
            detail      = "Backend LLM nicht erreichbar",
        )
    return {"status": "ok"}


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
