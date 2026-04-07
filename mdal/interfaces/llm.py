"""
LLM adapter protocol — interface for future Rust extraction (via PyO3).

All LLM interactions run exclusively through this interface.
No other part of the system may make direct HTTP calls to an LLM.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMAdapterProtocol(Protocol):
    """
    Unified interface to any OpenAI-compatible LLM endpoint.
    Implementations: OpenAICompatibleAdapter (Python), future Rust via PyO3.
    """

    def complete(self, messages: list[dict], **kwargs) -> str:
        """
        Sends a chat completion request and returns the response text.
        Streaming is not supported here — a complete output is expected (F6).
        """
        ...

    def embed(self, text: str) -> list[float]:
        """
        Computes the embedding vector for the given text.
        Handled by a dedicated embedding model (separate adapter instance).
        """
        ...

    def health_check(self) -> bool:
        """Checks whether the endpoint is reachable."""
        ...
