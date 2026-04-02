"""Unit-Tests für mdal.llm.adapter — OpenAICompatibleAdapter."""

import pytest
import respx
import httpx

from mdal.interfaces.llm import LLMAdapterProtocol
from mdal.llm.adapter import (
    LLMResponseError,
    LLMUnavailableError,
    OpenAICompatibleAdapter,
    embedding_adapter_from_config,
    llm_adapter_from_config,
)
from mdal.config import EmbeddingConfig, LLMConfig


BASE_URL = "http://localhost:11434"


# ---------------------------------------------------------------------------
# Protocol-Konformität (Rust-Migration: Interface muss erfüllt sein)
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    def test_adapter_implements_protocol(self):
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="llama3.2")
        assert isinstance(adapter, LLMAdapterProtocol)


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------

class TestComplete:
    @respx.mock
    def test_returns_content_from_response(self):
        respx.post(f"{BASE_URL}/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "Hallo Welt"}}]
            })
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="llama3.2")
        result = adapter.complete([{"role": "user", "content": "Hi"}])
        assert result == "Hallo Welt"

    @respx.mock
    def test_sends_stream_false(self):
        route = respx.post(f"{BASE_URL}/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}]
            })
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="llama3.2")
        adapter.complete([{"role": "user", "content": "test"}])
        assert route.calls[0].request.content
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["stream"] is False

    @respx.mock
    def test_sends_configured_model(self):
        route = respx.post(f"{BASE_URL}/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}]
            })
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="gemma2")
        adapter.complete([{"role": "user", "content": "test"}])
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["model"] == "gemma2"

    @respx.mock
    def test_server_error_raises_unavailable(self):
        respx.post(f"{BASE_URL}/v1/chat/completions").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="llama3.2")
        with pytest.raises(LLMUnavailableError):
            adapter.complete([{"role": "user", "content": "hi"}])

    @respx.mock
    def test_client_error_raises_response_error(self):
        respx.post(f"{BASE_URL}/v1/chat/completions").mock(
            return_value=httpx.Response(400, text="Bad Request")
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="llama3.2")
        with pytest.raises(LLMResponseError):
            adapter.complete([{"role": "user", "content": "hi"}])

    def test_connect_error_raises_unavailable(self):
        adapter = OpenAICompatibleAdapter(url="http://127.0.0.1:1", model="llama3.2", timeout=1)
        with pytest.raises(LLMUnavailableError):
            adapter.complete([{"role": "user", "content": "hi"}])

    @respx.mock
    def test_malformed_response_raises_response_error(self):
        respx.post(f"{BASE_URL}/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"unexpected": "format"})
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="llama3.2")
        with pytest.raises(LLMResponseError):
            adapter.complete([{"role": "user", "content": "hi"}])

    @respx.mock
    def test_api_key_sent_as_bearer(self):
        route = respx.post(f"{BASE_URL}/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}]
            })
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="llama3.2", api_key="sk-test")
        adapter.complete([{"role": "user", "content": "hi"}])
        assert route.calls[0].request.headers["Authorization"] == "Bearer sk-test"


# ---------------------------------------------------------------------------
# embed()
# ---------------------------------------------------------------------------

class TestEmbed:
    @respx.mock
    def test_returns_embedding_vector(self):
        respx.post(f"{BASE_URL}/v1/embeddings").mock(
            return_value=httpx.Response(200, json={
                "data": [{"embedding": [0.1, 0.2, 0.3]}]
            })
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="nomic-embed-text")
        result = adapter.embed("Testtext")
        assert result == [0.1, 0.2, 0.3]

    @respx.mock
    def test_embed_server_error_raises_unavailable(self):
        respx.post(f"{BASE_URL}/v1/embeddings").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="nomic-embed-text")
        with pytest.raises(LLMUnavailableError):
            adapter.embed("text")

    @respx.mock
    def test_embed_malformed_response_raises(self):
        respx.post(f"{BASE_URL}/v1/embeddings").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="nomic-embed-text")
        with pytest.raises(LLMResponseError):
            adapter.embed("text")


# ---------------------------------------------------------------------------
# health_check()
# ---------------------------------------------------------------------------

class TestHealthCheck:
    @respx.mock
    def test_returns_true_on_200(self):
        respx.get(f"{BASE_URL}/v1/models").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="llama3.2")
        assert adapter.health_check() is True

    @respx.mock
    def test_returns_false_on_non_200(self):
        respx.get(f"{BASE_URL}/v1/models").mock(
            return_value=httpx.Response(503)
        )
        adapter = OpenAICompatibleAdapter(url=BASE_URL, model="llama3.2")
        assert adapter.health_check() is False

    def test_returns_false_on_connect_error(self):
        adapter = OpenAICompatibleAdapter(url="http://127.0.0.1:1", model="llama3.2")
        assert adapter.health_check() is False


# ---------------------------------------------------------------------------
# Factory-Funktionen
# ---------------------------------------------------------------------------

class TestFactories:
    def test_llm_adapter_from_config(self):
        config = LLMConfig(url=BASE_URL, model="llama3.2")
        adapter = llm_adapter_from_config(config)
        assert isinstance(adapter, OpenAICompatibleAdapter)

    def test_embedding_adapter_from_config(self):
        config = EmbeddingConfig(url=BASE_URL, model="nomic-embed-text")
        adapter = embedding_adapter_from_config(config)
        assert isinstance(adapter, OpenAICompatibleAdapter)
