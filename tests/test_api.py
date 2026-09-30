import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health_ok(client):
    with patch("main.ollama_client.health_check", new=AsyncMock(return_value=True)):
        resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["ollama_reachable"] is True


def test_health_degraded_when_ollama_down(client):
    with patch("main.ollama_client.health_check", new=AsyncMock(return_value=False)):
        resp = client.get("/api/health")
    assert resp.json()["status"] == "degraded"


def test_health_reports_openrouter_availability(client):
    with (
        patch("main.ollama_client.health_check", new=AsyncMock(return_value=True)),
        patch("main.openrouter_client.is_available", return_value=True),
    ):
        resp = client.get("/api/health")
    assert resp.json()["openrouter_available"] is True


def test_review_rejects_empty_code(client):
    resp = client.post("/api/review", json={"code": "   "})
    assert resp.status_code == 400


def test_review_rejects_missing_code_field(client):
    resp = client.post("/api/review", json={})
    assert resp.status_code == 422


async def _fake_stream(*_args, **_kwargs):
    for token in ["Looks", " good", "."]:
        yield token


def test_review_streams_tokens(client):
    with patch("main.ollama_client.stream_generate", new=_fake_stream):
        resp = client.post("/api/review", json={"code": "print(1)"})
    assert resp.status_code == 200
    assert "Looks good." in resp.text.replace("data: ", "").replace("\n\n", "")


def test_explain_streams_tokens(client):
    with patch("main.ollama_client.stream_generate", new=_fake_stream):
        resp = client.post("/api/explain", json={"code": "print(1)", "language": "python"})
    assert resp.status_code == 200


def test_models_endpoint_surfaces_ollama_failure(client):
    with patch("main.ollama_client.list_models", new=AsyncMock(side_effect=Exception("down"))):
        resp = client.get("/api/models")
    assert resp.status_code == 502


def test_fix_streams_tokens(client):
    with patch("main.ollama_client.stream_generate", new=_fake_stream):
        resp = client.post("/api/fix", json={"code": "print(1)"})
    assert resp.status_code == 200
    assert "Looks good." in resp.text.replace("data: ", "").replace("\n\n", "")


def test_fix_rejects_empty_code(client):
    resp = client.post("/api/fix", json={"code": "   "})
    assert resp.status_code == 400


# ── Provider-aware tests ──────────────────────────────────────────


def test_providers_endpoint(client):
    with (
        patch("main.ollama_client.health_check", new=AsyncMock(return_value=True)),
        patch("main.openrouter_client.is_available", return_value=False),
    ):
        resp = client.get("/api/providers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ollama"] is True
    assert body["openrouter"] is False


def test_providers_openrouter_available(client):
    with (
        patch("main.ollama_client.health_check", new=AsyncMock(return_value=True)),
        patch("main.openrouter_client.is_available", return_value=True),
    ):
        resp = client.get("/api/providers")
    assert resp.json()["openrouter"] is True


def test_models_ollama_returns_list(client):
    with patch(
        "main.ollama_client.list_models",
        new=AsyncMock(return_value=["llama3:8b", "qwen2.5:7b"]),
    ):
        resp = client.get("/api/models?provider=ollama")
    assert resp.status_code == 200
    models = resp.json()["models"]
    assert len(models) == 2
    assert models[0]["id"] == "llama3:8b"
    assert models[0]["label"] == "llama3:8b"


def test_models_openrouter_returns_curated_list(client):
    resp = client.get("/api/models?provider=openrouter")
    assert resp.status_code == 200
    models = resp.json()["models"]
    assert len(models) == 5
    ids = [m["id"] for m in models]
    assert "qwen/qwen-2.5-coder-32b-instruct:free" in ids
    assert "mistralai/mistral-7b-instruct:free" in ids
    assert "openrouter/free" in ids


def test_review_with_openrouter_provider(client):
    with patch("main.openrouter_client.stream_generate", new=_fake_stream):
        resp = client.post(
            "/api/review",
            json={"code": "print(1)", "provider": "openrouter"},
        )
    assert resp.status_code == 200
    assert "Looks good." in resp.text.replace("data: ", "").replace("\n\n", "")


def test_review_openrouter_error_surfaces_in_sse(client):
    async def _error_stream(*_a, **_k):
        raise main.openrouter_client.OpenRouterError("rate limit hit")
        yield  # make it an async generator  # noqa: E501

    with patch("main.openrouter_client.stream_generate", new=_error_stream):
        resp = client.post(
            "/api/review",
            json={"code": "print(1)", "provider": "openrouter"},
        )
    assert resp.status_code == 200  # SSE stream itself is 200
    assert "rate limit hit" in resp.text


def test_default_provider_is_ollama(client):
    """When no provider is specified, Ollama is used."""
    with patch("main.ollama_client.stream_generate", new=_fake_stream):
        resp = client.post("/api/review", json={"code": "print(1)"})
    assert resp.status_code == 200
    assert "Looks good." in resp.text.replace("data: ", "").replace("\n\n", "")
