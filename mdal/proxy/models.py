"""
OpenAI-kompatible Request/Response-Modelle für den MDAL-Proxy (F19).

Der Proxy implementiert die OpenAI Chat Completions API-Oberfläche,
sodass jeder OpenAI-kompatible Client ohne Anpassung gegen MDAL proxied
werden kann.

Einschränkungen des PoC:
  - stream=True wird nicht unterstützt (F6: nur vollständige Outputs)
  - usage-Felder werden auf 0 gesetzt (keine Token-Zählung im Proxy)
  - function_call / tools werden durchgereicht aber nicht ausgewertet
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """Einzelne Nachricht im OpenAI-Gesprächsformat."""
    role:    str
    content: str


class ChatCompletionRequest(BaseModel):
    """
    OpenAI /v1/chat/completions Request-Body.

    Felder die MDAL nicht auswertet werden als `extra_fields` durchgereicht
    (z.B. temperature, max_tokens) und an das Backend-LLM weitergegeben.
    """
    model:    str
    messages: list[ChatMessage]
    stream:   bool = False

    model_config = {"extra": "allow"}

    def messages_as_dicts(self) -> list[dict[str, str]]:
        """Konvertiert Nachrichten für den LLM-Adapter."""
        return [{"role": m.role, "content": m.content} for m in self.messages]


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class ChatMessageResponse(BaseModel):
    role:    str = "assistant"
    content: str


class ChoiceResponse(BaseModel):
    index:         int = 0
    message:       ChatMessageResponse
    finish_reason: str = "stop"


class UsageResponse(BaseModel):
    """Platzhalter — Token-Zählung findet im Proxy nicht statt."""
    prompt_tokens:     int = 0
    completion_tokens: int = 0
    total_tokens:      int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI-kompatible Antwort-Struktur."""
    id:      str          = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object:  str          = "chat.completion"
    created: int          = Field(default_factory=lambda: int(time.time()))
    model:   str          = "mdal-proxy"
    choices: list[ChoiceResponse]
    usage:   UsageResponse = Field(default_factory=UsageResponse)

    @classmethod
    def from_content(cls, content: str) -> "ChatCompletionResponse":
        return cls(
            choices=[ChoiceResponse(message=ChatMessageResponse(content=content))]
        )


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    message: str
    type:    str
    code:    str | None = None


class ErrorResponse(BaseModel):
    """OpenAI-kompatibler Fehler-Body."""
    error: ErrorDetail

    @classmethod
    def make(cls, message: str, error_type: str, code: str | None = None) -> "ErrorResponse":
        return cls(error=ErrorDetail(message=message, type=error_type, code=code))
