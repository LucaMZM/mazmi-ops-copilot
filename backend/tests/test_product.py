"""Product contracts: authenticated local-AI configuration, inspector and approval scoping."""

from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_pipeline import api as api  # shared existing real PostgreSQL fixture

from app import main
from app.config import Settings
from app.schemas import ChatRequest


def test_defaults_are_local_ollama_with_no_cloud_options():
    config = Settings(_env_file=None)
    assert config.app_env == "production"
    assert config.generation_provider == config.embedding_provider == "ollama"
    assert config.ollama_reasoning == "off" and config.evidence_mode == "quoted_v6"
    assert not any("openai" in name or "gemini" in name for name in Settings.model_fields)
    assert not any(name.startswith("demo") for name in Settings.model_fields)


def test_legacy_reasoning_names_are_still_accepted():
    assert Settings(_env_file=None, ollama_reasoning="no_think_directive").ollama_reasoning == "off"
    assert Settings(_env_file=None, ollama_reasoning="model_default").ollama_reasoning == "on"


def test_config_reports_local_models_without_probing_or_secrets(api):
    response = api.get("/api/system")
    assert response.status_code == 200
    data = response.json()
    assert data["generation"] == {
        "provider": "ollama",
        "model": "qwen3:4b",
        "verification": "not_checked",
    }
    assert data["embeddings"]["collection"] is None
    assert data["runtime"]["local_endpoint"] is True
    assert "demo" not in data and "database_url" not in response.text
    assert "api_key" not in response.text and "key" not in {k.lower() for k in data["generation"]}
    health = api.get("/health").json()
    assert health["generation_provider"] == health["embedding_provider"] == "ollama"


def test_new_product_endpoints_require_session():
    with TestClient(main.app) as client:
        for path in ["/api/system", "/api/actions", f"/api/documents/{uuid4()}/chunks"]:
            assert client.get(path).status_code == 401


def test_chunk_inspector_pagination_and_workspace_boundaries(api):
    text = "Policy sentence. " * 2600
    doc = api.post("/api/documents", files={"file": ("policy.txt", text.encode())}).json()["id"]
    page = api.get(f"/api/documents/{doc}/chunks").json()
    assert len(page["chunks"]) == 25 and page["total"] > 25
    assert all("embedding" not in c for c in page["chunks"])
    more = api.get(f"/api/documents/{doc}/chunks?offset=25").json()
    assert more["chunks"][0]["index"] == 25
    assert api.get(f"/api/documents/{doc}/chunks?offset=-1").status_code == 422
    other = api.post("/api/auth/workspaces", json={"name": "Other"}).json()["id"]
    api.post("/api/auth/workspace", json={"workspace_id": other})
    assert api.get(f"/api/documents/{doc}/chunks").status_code == 404
    assert api.get("/api/documents").json() == []


def test_approvals_are_scoped_to_requester_and_workspace(api, monkeypatch):
    from test_pipeline import propose

    propose(api, monkeypatch)
    rows = api.get("/api/actions").json()
    assert len(rows) == 1 and rows[0]["status"] == "PENDING"
    assert set(rows[0]) == {
        "id",
        "name",
        "payload",
        "status",
        "created_at",
        "conversation_id",
        "resolved_at",
    }
    with main.get_conn() as conn:
        conn.execute("UPDATE pending_actions SET requested_by=NULL")
    assert api.get("/api/actions").json() == []


def test_cancelled_chat_rolls_back_conversation_and_proposal(api, monkeypatch):
    user = None
    with main.get_conn() as conn:
        r = conn.execute(
            "SELECT u.id,m.workspace_id,u.email FROM users u JOIN workspace_members m ON u.id=m.user_id"
        ).fetchone()
        from app.auth import Principal

        user = Principal(str(r[0]), str(r[1]), r[2])
    cancelled = Event()

    def fake_answer(*args):
        cancelled.set()
        return (
            "proposal",
            {
                "name": "create_ticket",
                "payload": {"title": "No", "description": "Cancelled", "priority": "LOW"},
            },
            {"tools": [], "duration_ms": 0},
        )

    monkeypatch.setattr(main, "answer", fake_answer)
    with pytest.raises(main.ChatCancelled):
        main.run_chat(ChatRequest(message="Crea un ticket", mode="DO"), user, cancelled=cancelled)
    assert api.get("/api/actions").json() == []
    assert api.get("/api/conversations").json() == []
