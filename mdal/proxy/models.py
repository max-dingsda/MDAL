"""
OpenAI-compatible request/response models for the MDAL proxy (F19).

The proxy implements the OpenAI Chat Completions API surface so that
any OpenAI-compatible client can proxy against MDAL without modification.

PoC limitations:
  - stream=True is not supported (F6: complete outputs only)
  - usage fields are set to 0 (no token counting in the proxy)
  - function_call / tools are passed through but not evaluated
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
    """A single message in OpenAI conversation format."""
    role:    str
    content: str


class ChatCompletionRequest(BaseModel):
    """
    OpenAI /v1/chat/completions request body.

    Fields that MDAL does not evaluate are passed through as `extra_fields`
    (e.g. temperature, max_tokens) and forwarded to the backend LLM.
    """
    model:    str
    messages: list[ChatMessage]
    stream:   bool = False

    model_config = {"extra": "allow"}

    def messages_as_dicts(self) -> list[dict[str, str]]:
        """Converts messages for the LLM adapter."""
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
    """Placeholder — token counting does not take place in the proxy."""
    prompt_tokens:     int = 0
    completion_tokens: int = 0
    total_tokens:      int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible response structure."""
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
    """OpenAI-compatible error body."""
    error: ErrorDetail

    @classmethod
    def make(cls, message: str, error_type: str, code: str | None = None) -> "ErrorResponse":
        return cls(error=ErrorDetail(message=message, type=error_type, code=code))
