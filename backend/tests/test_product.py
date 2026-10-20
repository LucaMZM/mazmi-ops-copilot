"""Product contracts: same PostgreSQL/auth/security paths in demo and normal operation."""

from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_pipeline import api as api  # shared existing real PostgreSQL fixture

from app import main
from app.config import Settings, settings
from app.providers import embeddings_client, generation_client, require_config
from app.schemas import ChatRequest


def test_demo_cannot_start_in_production_or_business_database():
    for env, url in [
        ("production", "postgresql://localhost/test_demo"),
        ("development", "postgresql://localhost/business"),
    ]:
        with pytest.raises(ValidationError, match="dedicated database"):
            Settings(_env_file=None, demo_mode=True, app_env=env, database_url=url)


def test_demo_requires_explicit_activation():
    assert not Settings(_env_file=None).demo_mode
    assert Settings(_env_file=None).app_env == "production"


def test_config_never_returns_keys_or_claims_a_live_connection(api, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "PRIVATE-SERVER-KEY")
    response = api.get("/api/system")
    assert response.status_code == 200 and "PRIVATE-SERVER-KEY" not in response.text
    assert response.json()["generation"]["verification"] == "not_checked"
    assert "database_url" not in response.text and "api_key" not in response.text


def test_config_missing_key_and_ollama_does_not_probe(api, monkeypatch):
    monkeypatch.setattr(settings, "generation_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "embedding_provider", "ollama")
    result = api.get("/api/system").json()
    assert result["generation"]["state"] == "not_configured"
    assert result["embeddings"]["collection"] is None
    assert result["embeddings"]["verification"] == "not_checked"


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
    assert set(rows[0]) == {"id", "name", "payload", "status", "created_at", "conversation_id"}
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


def test_demo_provider_uses_real_rag_and_human_approval(api, monkeypatch):
    # Dedicated connection in the test fixture is isolated by schema. Guard is
    # tested separately against actual names; only here use a controlled override.
    monkeypatch.setattr(Settings, "guard_demo", lambda self: self)
    monkeypatch.setattr(settings, "demo_mode", True)
    from app import agent, rag

    monkeypatch.setattr(agent, "client", generation_client())
    monkeypatch.setattr(rag, "client", embeddings_client())
    monkeypatch.setattr(settings, "openai_api_key", "")
    require_config("gemini")
    doc = api.post(
        "/api/documents",
        files={"file": ("demo.txt", "Las vacaciones son 25 días laborables.".encode())},
    )
    assert doc.status_code == 200
    assert api.get("/api/system").json()["demo"] is True
    health = api.get("/health").json()
    assert health["generation_provider"] == health["embedding_provider"] == "demo"
    with main.get_conn() as conn:
        assert (
            conn.execute("SELECT embedding_collection FROM documents")
            .fetchone()[0]
            .startswith("demo:")
        )
    response = api.post("/api/chat", json={"message": "¿Cuántos días de vacaciones hay?"})
    assert "[1]" in response.json()["answer"]
    response = api.post("/api/chat/stream", json={"message": "Crea un ticket", "mode": "DO"})
    assert "pending_action" in response.text and api.get("/api/tickets").json() == []
    action = api.get("/api/actions").json()[0]["id"]
    assert api.post(f"/api/actions/{action}/decision", json={"approved": False}).status_code == 200
    assert api.get("/api/actions").json()[0]["status"] == "REJECTED"
    assert api.get("/api/tickets").json() == []


def test_demo_seed_refuses_populated_database_before_migrating(api, monkeypatch):
    from app import migrate
    from app.demo import seed

    monkeypatch.setattr(Settings, "guard_demo", lambda self: self)
    invoked = []
    monkeypatch.setattr(migrate, "migrate", lambda: invoked.append(True))
    with pytest.raises(RuntimeError, match="empty database"):
        seed()
    assert invoked == []
    assert api.get("/api/auth/me").status_code == 200
