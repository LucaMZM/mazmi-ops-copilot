"""Manual local readiness is authenticated, bounded and never implied by config."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from test_pipeline import api as api

from app import check_local, main, runtime
from app.config import settings


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "generation_provider", "ollama")
    monkeypatch.setattr(settings, "embedding_provider", "ollama")
    monkeypatch.setattr(settings, "embedding_dimensions", 768)
    monkeypatch.setattr(runtime, "_last_check", None)


def passed():
    return {
        "status": "passed",
        "duration_ms": 12,
        "checks": {"embeddings": {"collection": "ollama:embeddinggemma:768:fixture-digest"}},
    }


def test_readiness_requires_authentication_and_origin(api, monkeypatch):
    monkeypatch.setattr(check_local, "run_checks", lambda **kw: pytest.fail("must not infer"))
    with TestClient(main.app) as client:
        assert client.post("/api/system/check-local").status_code == 401
    assert (
        api.post("/api/system/check-local", headers={"Origin": "https://evil.invalid"}).status_code
        == 403
    )


def test_configured_is_not_verified_and_get_does_not_infer(api, local, monkeypatch):
    monkeypatch.setattr(check_local, "run_checks", lambda **kw: pytest.fail("GET must not infer"))
    data = api.get("/api/system").json()
    assert data["generation"]["state"] == "configured"
    assert data["generation"]["verification"] == "not_checked"
    assert data["embeddings"]["collection"] is None


def test_explicit_probe_records_only_fixed_fixture_success(api, local, monkeypatch):
    calls = []

    def check(**kw):
        calls.append(kw)
        return passed()

    monkeypatch.setattr(check_local, "run_checks", check)
    data = api.post("/api/system/check-local").json()
    assert calls == [{"full": False}]
    assert data["generation"]["verification"] == data["embeddings"]["verification"] == "passed"
    datetime.fromisoformat(data["generation"]["checked_at"])
    assert data["embeddings"]["collection"] == "ollama:embeddinggemma:768:fixture-digest"
    assert api.get("/api/system").json()["generation"] == data["generation"]
    assert len(calls) == 1


def test_failed_probe_never_exposes_provider_bodies_or_claims_success(api, local, monkeypatch):
    monkeypatch.setattr(
        check_local,
        "run_checks",
        lambda **kw: {
            "status": "failed",
            "error": "PRIVATE-PROVIDER-BODY",
            "models": {"secret": "PRIVATE"},
            "checks": {"embeddings": {"collection": "must-not-be-active"}},
        },
    )
    response = api.post("/api/system/check-local")
    assert response.status_code == 200 and "PRIVATE" not in response.text
    data = response.json()
    assert data["generation"]["verification"] == "failed"
    assert data["embeddings"]["collection"] is None


def test_config_change_and_expiry_clear_historical_verification(api, local, monkeypatch):
    monkeypatch.setattr(check_local, "run_checks", lambda **kw: passed())
    api.post("/api/system/check-local")
    monkeypatch.setattr(settings, "ollama_chat_model", "different:tag")
    assert api.get("/api/system").json()["generation"]["verification"] == "not_checked"
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen3:4b")
    old = runtime._last_check
    monkeypatch.setattr(runtime, "_last_check", (old[0], old[1] - 301, old[2]))
    assert api.get("/api/system").json()["generation"]["verification"] == "not_checked"


def test_concurrent_probe_is_rejected_and_failed_exception_releases_lock(api, local, monkeypatch):
    monkeypatch.setattr(check_local, "run_checks", lambda **kw: pytest.fail("must not infer"))
    with runtime._check_lock:
        assert api.post("/api/system/check-local").status_code == 409

    def fail(**kw):
        raise RuntimeError("PRIVATE-WORKER-EXCEPTION")

    monkeypatch.setattr(check_local, "run_checks", fail)
    response = api.post("/api/system/check-local")
    assert response.status_code == 502 and "PRIVATE" not in response.text
    monkeypatch.setattr(check_local, "run_checks", lambda **kw: passed())
    assert api.post("/api/system/check-local").json()["generation"]["verification"] == "passed"


@pytest.mark.parametrize("demo,cloud", [(True, False), (False, True)])
def test_probe_rejects_demo_or_cloud_without_calling_model(api, monkeypatch, demo, cloud):
    monkeypatch.setattr(settings, "demo_mode", demo)
    monkeypatch.setattr(settings, "generation_provider", "gemini" if cloud else "ollama")
    monkeypatch.setattr(check_local, "run_checks", lambda **kw: pytest.fail("must not infer"))
    assert api.post("/api/system/check-local").status_code == 400
