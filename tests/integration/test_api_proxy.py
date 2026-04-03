"""
Integrations-Tests für den MDAL API-Proxy.

Testet die FastAPI-Routen mit echtem ASGI-Transport (kein Netzwerk).
Der PipelineOrchestrator wird durch einen Mock ersetzt — die Proxy-Logik
(Routing, Fehlerbehandlung, Request/Response-Format) steht im Fokus.

Teste:
  - POST /v1/chat/completions — Erfolgsfall
  - POST /v1/chat/completions — stream=True abgelehnt (F6)
  - POST /v1/chat/completions — RetryLimitError → 503
  - POST /v1/chat/completions — LLMUnavailableError → 503
  - POST /v1/chat/completions — Fingerprint fehlt → 503
  - POST /v1/chat/completions — Sprachauswahl via Header
  - GET /health — LLM erreichbar
  - GET /health — LLM nicht erreichbar → 503
  - OpenAI-kompatibler Response-Body
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from mdal.llm.adapter import LLMUnavailableError
from mdal.proxy.app import app
from mdal.retry import RetryLimitError
from mdal.session import SessionContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_app_state():
    """Stellt sicher dass App-State zwischen Tests sauber ist."""
    yield
    # Cleanup
    for attr in ("pipeline", "audit", "default_language"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


def setup_app(pipeline_mock: MagicMock, language: str = "de") -> None:
    """Konfiguriert App-State für Tests."""
    app.state.pipeline         = pipeline_mock
    app.state.audit            = None
    app.state.default_language = language


def make_pipeline_mock(return_value: str = "Gute Antwort.") -> MagicMock:
    mock = MagicMock()
    mock.process.return_value = return_value
    mock._llm.health_check.return_value = True
    return mock


EXAMPLE_REQUEST = {
    "model":    "llama3.2",
    "messages": [{"role": "user", "content": "Hallo!"}],
}


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_returns_ok_when_llm_reachable(self):
        pipeline = make_pipeline_mock()
        setup_app(pipeline)

        with TestClient(app) as client:
            response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_returns_503_when_llm_unreachable(self):
        pipeline = make_pipeline_mock()
        pipeline._llm.health_check.return_value = False
        setup_app(pipeline)

        with TestClient(app) as client:
            response = client.get("/health")

        assert response.status_code == 503


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — Erfolg
# ---------------------------------------------------------------------------

class TestChatCompletionsSuccess:
    def test_returns_openai_compatible_response(self):
        pipeline = make_pipeline_mock("Die Analyse zeigt ein klares Ergebnis.")
        setup_app(pipeline)

        with TestClient(app) as client:
            response = client.post("/v1/chat/completions", json=EXAMPLE_REQUEST)

        assert response.status_code == 200
        body = response.json()
        assert body["object"] == "chat.completion"
        assert "choices" in body
        assert body["choices"][0]["message"]["role"] == "assistant"
        assert body["choices"][0]["message"]["content"] == "Die Analyse zeigt ein klares Ergebnis."
        assert body["choices"][0]["finish_reason"] == "stop"

    def test_response_contains_id_and_created(self):
        setup_app(make_pipeline_mock())

        with TestClient(app) as client:
            response = client.post("/v1/chat/completions", json=EXAMPLE_REQUEST)

        body = response.json()
        assert "id" in body
        assert body["id"].startswith("chatcmpl-")
        assert "created" in body
        assert isinstance(body["created"], int)

    def test_pipeline_called_with_correct_messages(self):
        pipeline = make_pipeline_mock()
        setup_app(pipeline)

        with TestClient(app) as client:
            client.post("/v1/chat/completions", json={
                "model":    "llama3.2",
                "messages": [
                    {"role": "system", "content": "Du bist ein Assistent."},
                    {"role": "user",   "content": "Analysiere die Daten."},
                ],
            })

        pipeline.process.assert_called_once()
        call_kwargs = pipeline.process.call_args[1]
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — Sprache
# ---------------------------------------------------------------------------

class TestLanguageSelection:
    def test_uses_config_default_language(self):
        pipeline = make_pipeline_mock()
        setup_app(pipeline, language="de")

        with TestClient(app) as client:
            client.post("/v1/chat/completions", json=EXAMPLE_REQUEST)

        call_kwargs = pipeline.process.call_args[1]
        assert call_kwargs["language"] == "de"

    def test_header_overrides_default_language(self):
        pipeline = make_pipeline_mock()
        setup_app(pipeline, language="de")

        with TestClient(app) as client:
            client.post(
                "/v1/chat/completions",
                json=EXAMPLE_REQUEST,
                headers={"X-MDAL-Language": "en"},
            )

        call_kwargs = pipeline.process.call_args[1]
        assert call_kwargs["language"] == "en"


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — Fehlerbehandlung
# ---------------------------------------------------------------------------

class TestChatCompletionsErrors:
    def test_stream_true_returns_400(self):
        setup_app(make_pipeline_mock())

        with TestClient(app) as client:
            response = client.post("/v1/chat/completions", json={
                **EXAMPLE_REQUEST,
                "stream": True,
            })

        assert response.status_code == 400

    def test_retry_limit_error_returns_503(self):
        pipeline = make_pipeline_mock()
        pipeline.process.side_effect = RetryLimitError("sess-1", 3)
        setup_app(pipeline)

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/v1/chat/completions", json=EXAMPLE_REQUEST)

        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "retry_limit_exceeded"

    def test_llm_unavailable_returns_503(self):
        pipeline = make_pipeline_mock()
        pipeline.process.side_effect = LLMUnavailableError("LLM nicht erreichbar")
        setup_app(pipeline)

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/v1/chat/completions", json=EXAMPLE_REQUEST)

        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "llm_unavailable"

    def test_missing_fingerprint_returns_503(self):
        pipeline = make_pipeline_mock()
        pipeline.process.side_effect = KeyError("de")
        setup_app(pipeline)

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/v1/chat/completions", json=EXAMPLE_REQUEST)

        assert response.status_code == 503

    def test_extra_fields_accepted(self):
        """OpenAI-kompatible Felder wie temperature werden akzeptiert."""
        setup_app(make_pipeline_mock())

        with TestClient(app) as client:
            response = client.post("/v1/chat/completions", json={
                **EXAMPLE_REQUEST,
                "temperature": 0.7,
                "max_tokens":  512,
            })

        assert response.status_code == 200

    def test_missing_messages_returns_422(self):
        setup_app(make_pipeline_mock())

        with TestClient(app) as client:
            response = client.post("/v1/chat/completions", json={"model": "llama3.2"})

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Audit-Integration
# ---------------------------------------------------------------------------

class TestAuditIntegration:
    def test_audit_write_called_on_success(self):
        pipeline    = make_pipeline_mock("Ergebnis.")
        audit_mock  = MagicMock()
        setup_app(pipeline)
        app.state.audit = audit_mock

        with TestClient(app) as client:
            client.post("/v1/chat/completions", json=EXAMPLE_REQUEST)

        assert audit_mock.write.call_count == 2
        event_types = [call[0][0] for call in audit_mock.write.call_args_list]
        assert "request_received"   in event_types
        assert "response_delivered" in event_types

    def test_no_audit_configured_does_not_crash(self):
        setup_app(make_pipeline_mock())
        app.state.audit = None  # explizit kein Audit

        with TestClient(app) as client:
            response = client.post("/v1/chat/completions", json=EXAMPLE_REQUEST)

        assert response.status_code == 200
