"""
OpenAI-kompatibler LLM Adapter (NF4 — Modell-Agnostizität).

Eine einzige Adapter-Klasse für alle OpenAI-kompatiblen Endpunkte:
Ollama, OpenAI, Anthropic (via compatible proxy), Azure OpenAI, etc.

Das System wird mit zwei Instanzen betrieben:
  - llm_adapter:       für Chat-Completions (Produktiv-LLM)
  - embedding_adapter: für Embedding-Berechnungen (Embedding-Modell)

Beide können auf denselben Endpunkt zeigen (z.B. Ollama) oder auf verschiedene.
"""

from __future__ import annotations

import httpx

from mdal.config import EmbeddingConfig, LLMConfig
from mdal.interfaces.llm import LLMAdapterProtocol


class AdapterError(Exception):
    """Basisklasse für Adapter-Fehler — wird von der Retry-Logik ausgewertet."""


class LLMUnavailableError(AdapterError):
    """LLM-Endpunkt nicht erreichbar — löst ggf. Fallback-Mechanismus aus (F9)."""


class LLMResponseError(AdapterError):
    """LLM hat geantwortet aber mit einem unerwarteten Format oder Fehlercode."""


class OpenAICompatibleAdapter:
    """
    Implementiert LLMAdapterProtocol gegen jeden OpenAI-kompatiblen Endpunkt.

    Ollama-spezifische Hinweise:
    - Chat-Completions: POST /v1/chat/completions  (OpenAI-kompatibel ab Ollama 0.1.24)
    - Embeddings:       POST /v1/embeddings        (OpenAI-kompatibel)
    - Models:           GET  /v1/models            (für health_check)
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
        Sendet eine Chat-Completion-Anfrage.

        - stream=False erzwungen: MDAL prüft erst vollständige Outputs (F6).
        - Streaming vom LLM wird im API-Proxy gepuffert — dieser Adapter
          sieht immer vollständige Antworten.
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
                f"LLM-Endpunkt nicht erreichbar: {self._url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError(
                f"LLM-Endpunkt Timeout nach {self._timeout}s: {self._url}"
            ) from exc

        self._raise_for_status(response)

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMResponseError(
                f"Unerwartetes Antwort-Format vom LLM: {response.text[:200]}"
            ) from exc

    def embed(self, text: str) -> list[float]:
        """
        Berechnet den Embedding-Vektor für den gegebenen Text.

        Verwendet das konfigurierte Modell dieser Adapter-Instanz —
        beim Embedding-Adapter ist das ein dediziertes Embedding-Modell
        (z.B. nomic-embed-text), nicht das Chat-Modell.
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
                f"Embedding-Endpunkt nicht erreichbar: {self._url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError(
                f"Embedding-Endpunkt Timeout nach {self._timeout}s: {self._url}"
            ) from exc

        self._raise_for_status(response)

        try:
            return response.json()["data"][0]["embedding"]
        except (KeyError, IndexError) as exc:
            raise LLMResponseError(
                f"Unerwartetes Embedding-Antwort-Format: {response.text[:200]}"
            ) from exc

    def health_check(self) -> bool:
        """Prüft ob der Endpunkt erreichbar und betriebsbereit ist."""
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
    # Internes
    # ------------------------------------------------------------------

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 500:
            raise LLMUnavailableError(
                f"LLM-Server-Fehler {response.status_code}: {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise LLMResponseError(
                f"LLM-Client-Fehler {response.status_code}: {response.text[:200]}"
            )

    def __repr__(self) -> str:
        return f"OpenAICompatibleAdapter(url={self._url!r}, model={self._model!r})"


# ---------------------------------------------------------------------------
# Factory-Funktionen
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
