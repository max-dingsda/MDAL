"""
LLM Adapter Protocol — Nahtstelle für spätere Rust-Extraktion (via PyO3).

Alle LLM-Interaktionen laufen ausschließlich über dieses Interface.
Kein anderer Systemteil darf direkt HTTP-Calls zu einem LLM machen.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMAdapterProtocol(Protocol):
    """
    Einheitliche Schnittstelle zu jedem OpenAI-kompatiblen LLM-Endpunkt.
    Implementierungen: OpenAICompatibleAdapter (Python), zukünftig Rust via PyO3.
    """

    def complete(self, messages: list[dict], **kwargs) -> str:
        """
        Schickt eine Chat-Completion-Anfrage und gibt den Antwort-Text zurück.
        Streaming ist hier nicht vorgesehen — vollständiger Output wird erwartet (F6).
        """
        ...

    def embed(self, text: str) -> list[float]:
        """
        Berechnet den Embedding-Vektor für den gegebenen Text.
        Wird von einem dedizierten Embedding-Modell erledigt (separate Adapter-Instanz).
        """
        ...

    def health_check(self) -> bool:
        """Prüft ob der Endpunkt erreichbar ist."""
        ...
