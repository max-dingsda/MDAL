"""
OpenAI-compatible LLM adapter (NF4 — model agnosticity).

A single adapter class for all OpenAI-compatible endpoints:
Ollama, OpenAI, Anthropic (via compatible proxy), Azure OpenAI, etc.

The system runs with two instances:
  - llm_adapter:       for chat completions (production LLM)
  - embedding_adapter: for embedding computations (embedding model)

Both can point to the same endpoint (e.g. Ollama) or to different ones.
"""

from __future__ import annotations

import httpx

from mdal.config import EmbeddingConfig, LLMConfig
from mdal.interfaces.llm import LLMAdapterProtocol


class AdapterError(Exception):
    """Base class for adapter errors — evaluated by the retry logic."""


class LLMUnavailableError(AdapterError):
    """LLM endpoint not reachable — may trigger fallback mechanism (F9)."""


class LLMResponseError(AdapterError):
    """LLM responded but with an unexpected format or error code."""


class OpenAICompatibleAdapter:
    """
    Implements LLMAdapterProtocol against any OpenAI-compatible endpoint.

    Ollama-specific notes:
    - Chat completions: POST /v1/chat/completions  (OpenAI-compatible since Ollama 0.1.24)
    - Embeddings:       POST /v1/embeddings        (OpenAI-compatible)
    - Models:           GET  /v1/models            (for health_check)
    """

    def __init__(
        self,
        url: str,
        model: str,
        api_key: str | None = None,
        timeout: int = 60,
    ) -> None:
        self._url    = url.rstrip("/")
        self._model  = model
        self._timeout = timeout
        self._headers: dict[str, str] = {}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    # ------------------------------------------------------------------
    # LLMAdapterProtocol
    # ------------------------------------------------------------------

    def complete(self, messages: list[dict], **kwargs) -> str:
        """
        Sends a chat completion request.

        - stream=False enforced: MDAL only processes complete outputs (F6).
        - Streaming from the LLM is buffered in the API proxy — this adapter
          always receives complete responses.
        """
        payload = {
            "model":  self._model,
            "messages": messages,
            "stream": False,
            **kwargs,
        }
        try:
            response = httpx.post(
                f"{self._url}/v1/chat/completions",
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.ConnectError as exc:
            raise LLMUnavailableError(
                f"LLM endpoint not reachable: {self._url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError(
                f"LLM endpoint timeout after {self._timeout}s: {self._url}"
            ) from exc

        self._raise_for_status(response)

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMResponseError(
                f"Unexpected response format from LLM: {response.text[:200]}"
            ) from exc

    def embed(self, text: str) -> list[float]:
        """
        Computes the embedding vector for the given text.

        Uses the configured model of this adapter instance —
        for the embedding adapter this is a dedicated embedding model
        (e.g. nomic-embed-text), not the chat model.
        """
        payload = {"model": self._model, "input": text}
        try:
            response = httpx.post(
                f"{self._url}/v1/embeddings",
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.ConnectError as exc:
            raise LLMUnavailableError(
                f"Embedding endpoint not reachable: {self._url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError(
                f"Embedding endpoint timeout after {self._timeout}s: {self._url}"
            ) from exc

        self._raise_for_status(response)

        try:
            return response.json()["data"][0]["embedding"]
        except (KeyError, IndexError) as exc:
            raise LLMResponseError(
                f"Unexpected embedding response format: {response.text[:200]}"
            ) from exc

    def health_check(self) -> bool:
        """Checks whether the endpoint is reachable and operational."""
        try:
            response = httpx.get(
                f"{self._url}/v1/models",
                headers=self._headers,
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 500:
            raise LLMUnavailableError(
                f"LLM server error {response.status_code}: {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise LLMResponseError(
                f"LLM client error {response.status_code}: {response.text[:200]}"
            )

    def __repr__(self) -> str:
        return f"OpenAICompatibleAdapter(url={self._url!r}, model={self._model!r})"


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def llm_adapter_from_config(config: LLMConfig) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        url=config.url,
        model=config.model,
        api_key=config.api_key,
        timeout=config.timeout,
    )


def embedding_adapter_from_config(config: EmbeddingConfig) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        url=config.url,
        model=config.model,
        api_key=config.api_key,
        timeout=config.timeout,
    )
