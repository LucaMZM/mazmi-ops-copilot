"""HTTP regressions for the provider gate, SSE contract and workspace isolation.

Real PostgreSQL through the shared ``api`` fixture; providers are doubles only.
"""

import json
from types import SimpleNamespace as NS
from uuid import uuid4

from fastapi.testclient import TestClient
from test_pipeline import api as api  # shared real PostgreSQL fixture

from app import agent, main, rag


def sse_events(response):
    """Parse a complete SSE body exactly as a browser would: frames split by a blank line."""
    events = []
    for frame in response.text.replace("\r\n", "\n").split("\n\n"):
        data = [line[5:].lstrip() for line in frame.split("\n") if line.startswith("data:")]
        if data:
            events.append(json.loads("\n".join(data)))
    return events


def seed_tickets(workspace, titles):
    with main.get_conn() as conn:
        for title in titles:
            conn.execute(
                "INSERT INTO tickets(workspace_id,title,description,priority) VALUES (%s,%s,'x','LOW')",
                (workspace, title),
            )


def unconfigure_provider(monkeypatch):
    monkeypatch.setattr(agent, "client", None)


def test_stream_direct_read_works_without_configured_provider(api, monkeypatch):
    workspace = api.get("/api/auth/me").json()["workspace_id"]
    seed_tickets(workspace, ["Primero", "Segundo"])
    unconfigure_provider(monkeypatch)
    response = api.post("/api/chat/stream", json={"message": "Lista los tickets"})
    assert response.status_code == 200, response.text
    events = sse_events(response)
    assert [e["type"] for e in events][-1] == "done"
    done = events[-1]["data"]
    assert "#" in done["answer"] and "Segundo" in done["answer"]
    assert done["sources"] == [] and done["pending_action"] is None
    completed = next(e for e in api.get("/api/activity").json() if e["type"] == "chat.completed")
    assert completed["details"]["model_calls"] == 0


def test_stream_direct_read_with_configured_provider_needs_no_model(api, monkeypatch):
    workspace = api.get("/api/auth/me").json()["workspace_id"]
    seed_tickets(workspace, ["Configurado"])

    def forbidden(**kwargs):
        raise AssertionError("exact ticket reads must not call the model")

    monkeypatch.setattr(agent.client.responses, "create", forbidden)
    response = api.post("/api/chat/stream", json={"message": "Muestra los tickets"})
    assert response.status_code == 200
    assert sse_events(response)[-1]["type"] == "done"


def test_model_query_with_unreachable_ollama_is_a_sanitized_503(api, monkeypatch):
    from app.providers import ProviderUnavailable

    def unreachable(**kwargs):
        raise ProviderUnavailable("No se puede conectar con Ollama. Inicia el servicio local.")

    monkeypatch.setattr(agent.client.responses, "create", unreachable)
    monkeypatch.setattr(rag.client, "embeddings", NS(create=unreachable), raising=False)
    question = {"message": "¿Cuál es la política de acceso?"}
    response = api.post("/api/chat", json=question)
    assert response.status_code == 503 and "Ollama" in response.json()["detail"]
    streamed = api.post("/api/chat/stream", json=question)
    error = next(e for e in sse_events(streamed) if e["type"] == "error")
    assert error["status"] == 503 and "Ollama" in error["message"]
    assert api.get("/api/conversations").json() == []


def test_stream_invalid_limit_is_a_400_before_streaming(api, monkeypatch):
    unconfigure_provider(monkeypatch)
    response = api.post("/api/chat/stream", json={"message": "Lista los últimos 50 tickets"})
    assert response.status_code == 400
    assert "entre 1 y 20" in response.json()["detail"]


def test_stream_requires_session_origin_and_isolates_workspaces(api, monkeypatch):
    anonymous = TestClient(main.app, headers={"Origin": "http://localhost:3000"})
    assert (
        anonymous.post("/api/chat/stream", json={"message": "Lista los tickets"}).status_code == 401
    )
    foreign = TestClient(main.app, headers={"Origin": "https://evil.example"})
    foreign.cookies = api.cookies
    assert foreign.post("/api/chat/stream", json={"message": "x"}).status_code == 403

    mine = api.get("/api/auth/me").json()["workspace_id"]
    seed_tickets(mine, ["MINE-1"])
    other = TestClient(main.app, headers={"Origin": "http://localhost:3000"})
    assert (
        other.post(
            "/api/auth/register",
            json={
                "email": "other@example.com",
                "password": "other-password-123",
                "workspace_name": "O",
            },
        ).status_code
        == 201
    )
    seed_tickets(other.get("/api/auth/me").json()["workspace_id"], ["THEIRS-1"])
    unconfigure_provider(monkeypatch)
    answer = sse_events(api.post("/api/chat/stream", json={"message": "Lista los tickets"}))[-1]
    assert "MINE-1" in answer["data"]["answer"] and "THEIRS-1" not in answer["data"]["answer"]
    # A conversation id from another workspace is not found, never appended to.
    conversation = answer["data"]["conversation_id"]
    response = other.post(
        "/api/chat/stream", json={"message": "Lista los tickets", "conversation_id": conversation}
    )
    assert response.status_code == 404
    response = other.post(
        "/api/chat/stream", json={"message": "Lista los tickets", "conversation_id": str(uuid4())}
    )
    assert response.status_code == 404


def test_stream_unexpected_worker_failure_ends_with_sanitized_error(api, monkeypatch):
    def broken(*args, **kwargs):
        raise KeyError("private document text")

    monkeypatch.setattr(main, "answer", broken)
    monkeypatch.setattr(agent.client.responses, "create", lambda **kw: NS())
    response = api.post("/api/chat/stream", json={"message": "¿Qué dice la política?"})
    events = sse_events(response)
    assert events[-1]["type"] == "error"
    assert "private" not in response.text
    assert api.get("/api/conversations").json() == []
