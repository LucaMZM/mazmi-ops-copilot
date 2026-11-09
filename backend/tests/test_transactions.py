"""Transaction boundaries, concurrency and idempotency against real PostgreSQL.

Provider calls are doubles; database behaviour (locks, rollbacks, constraints) is real.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace as NS
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_pipeline import api as api  # shared real PostgreSQL fixture
from test_pipeline import propose

from app import agent, main, rag
from app.config import settings


def upload(api, name="politica.txt", text="El acceso requiere aprobación previa."):
    response = api.post("/api/documents", files={"file": (name, text.encode(), "text/plain")})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def lock_is_free(sql, params):
    """Try to take a row lock from an independent session without waiting."""
    with psycopg.connect(settings.database_url, autocommit=False) as conn:
        try:
            conn.execute("SET lock_timeout = '200ms'")
            conn.execute(sql, params).fetchall()
            return True
        except psycopg.errors.LockNotAvailable:
            return False
        finally:
            conn.rollback()


def test_no_lock_or_transaction_is_held_during_model_inference(api, monkeypatch):
    upload(api)
    first = api.post("/api/chat", json={"message": "¿Qué dice la política de acceso?"}).json()
    conversation = first["conversation_id"]
    observed = {}
    original = agent.client.responses.create

    def assessing(**kwargs):
        observed["conversation_free"] = lock_is_free(
            "SELECT 1 FROM conversations WHERE id=%s FOR UPDATE NOWAIT", (conversation,)
        )
        with psycopg.connect(settings.database_url) as conn:
            observed["idle_in_tx"] = conn.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()"
                " AND state LIKE 'idle in transaction%%' AND pid<>pg_backend_pid()"
            ).fetchone()[0]
        return original(**kwargs)

    monkeypatch.setattr(agent.client.responses, "create", assessing)
    response = api.post(
        "/api/chat",
        json={"message": "¿Y quién aprueba el acceso?", "conversation_id": conversation},
    )
    assert response.status_code == 200, response.text
    assert observed == {"conversation_free": True, "idle_in_tx": 0}


def test_document_deleted_during_inference_persists_nothing(api, monkeypatch):
    doc = upload(api)
    original = agent.client.responses.create

    def delete_then_answer(**kwargs):
        with psycopg.connect(settings.database_url) as conn:
            conn.execute("DELETE FROM documents WHERE id=%s", (doc,))
        return original(**kwargs)

    monkeypatch.setattr(agent.client.responses, "create", delete_then_answer)
    response = api.post("/api/chat", json={"message": "¿Qué dice la política de acceso?"})
    assert response.status_code == 409
    assert "No se guardó nada" in response.json()["detail"]
    assert api.get("/api/conversations").json() == []
    assert not any(e["type"] == "chat.completed" for e in api.get("/api/activity").json())


def test_same_request_id_replays_without_second_model_call_or_proposal(api, monkeypatch):
    calls = []
    proposal = NS(
        status="completed",
        output=[
            NS(
                type="function_call",
                name="create_ticket",
                arguments='{"title":"Revisar acceso","description":"Revisión","priority":"HIGH"}',
            )
        ],
        output_text="",
        usage=None,
    )

    def create(**kwargs):
        calls.append(1)
        return proposal

    monkeypatch.setattr(agent.client.responses, "create", create)
    body = {"message": "Crea un ticket de acceso", "mode": "DO", "client_request_id": str(uuid4())}
    first = api.post("/api/chat", json=body)
    second = api.post("/api/chat", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(calls) == 1
    assert len(api.get("/api/actions").json()) == 1
    # After a decision, a replay never shows the action as still actionable.
    action = first.json()["pending_action"]["id"]
    assert api.post(f"/api/actions/{action}/decision", json={"approved": True}).status_code == 200
    assert api.post("/api/chat", json=body).json()["pending_action"] is None
    assert len(api.get("/api/tickets").json()) == 1


def test_concurrent_duplicate_requests_create_exactly_one_proposal(api, monkeypatch):
    barrier = Barrier(2)

    def create(**kwargs):
        barrier.wait(timeout=5)  # Both requests are inside inference at the same time.
        return NS(
            status="completed",
            output=[
                NS(
                    type="function_call",
                    name="create_ticket",
                    arguments='{"title":"Doble clic","description":"Duplicado","priority":"LOW"}',
                )
            ],
            output_text="",
            usage=None,
        )

    monkeypatch.setattr(agent.client.responses, "create", create)
    body = {"message": "Crea un ticket", "mode": "DO", "client_request_id": str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: api.post("/api/chat", json=body), range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json() == results[1].json()
    assert len(api.get("/api/actions").json()) == 1
    assert len(api.get("/api/conversations").json()) == 1


def test_request_id_cannot_cross_workspaces(api, monkeypatch):
    propose_body = {"message": "Lista los tickets", "client_request_id": str(uuid4())}
    assert api.post("/api/chat", json=propose_body).status_code == 200
    other = api.post("/api/auth/workspaces", json={"name": "Otro"}).json()["id"]
    assert api.post("/api/auth/workspace", json={"workspace_id": other}).status_code == 200
    assert api.post("/api/chat", json=propose_body).status_code == 409


def test_reindex_holds_no_lock_while_embedding_and_respects_deletion(api, monkeypatch):
    doc = upload(api)
    seen = {}
    original = rag.client.embeddings.create

    def embed(**kwargs):
        seen["free"] = lock_is_free("SELECT 1 FROM documents WHERE id=%s FOR UPDATE NOWAIT", (doc,))
        return original(**kwargs)

    monkeypatch.setattr(rag.client.embeddings, "create", embed)
    assert api.post(f"/api/documents/{doc}/reindex").status_code == 200
    assert seen["free"] is True

    def delete_during_embed(**kwargs):
        with psycopg.connect(settings.database_url) as conn:
            conn.execute("DELETE FROM documents WHERE id=%s", (doc,))
        return original(**kwargs)

    monkeypatch.setattr(rag.client.embeddings, "create", delete_during_embed)
    assert api.post(f"/api/documents/{doc}/reindex").status_code == 404
    assert api.get("/api/documents").json() == []


def test_generation_queue_rejects_when_saturated(api, monkeypatch):
    upload(api)
    monkeypatch.setattr(settings, "chat_max_concurrent", 1)
    monkeypatch.setattr(settings, "chat_queue_timeout_seconds", 0.3)
    entered, release = Event(), Event()
    original = agent.client.responses.create

    def slow(**kwargs):
        entered.set()
        release.wait(5)
        return original(**kwargs)

    monkeypatch.setattr(agent.client.responses, "create", slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(api.post, "/api/chat", json={"message": "¿Qué dice la política?"})
        assert entered.wait(5)
        busy = api.post("/api/chat", json={"message": "¿Quién aprueba el acceso?"})
        release.set()
        assert first.result().status_code == 200
    assert busy.status_code == 503
    # Model-free exact reads are never queued behind inference.
    assert api.post("/api/chat", json={"message": "Lista los tickets"}).status_code == 200


def test_interrupted_indexing_is_recovered_as_failed(api):
    workspace = api.get("/api/auth/me").json()["workspace_id"]
    with main.get_conn() as conn:
        conn.execute(
            "INSERT INTO documents(workspace_id,filename,status,created_at,embedding_collection)"
            " VALUES (%s,'old.txt','processing',now()-interval '1 hour','x'),"
            " (%s,'new.txt','processing',now(),'x')",
            (workspace, workspace),
        )
    from app.documents import recover_interrupted_indexing

    assert recover_interrupted_indexing() == 1
    states = {d["filename"]: d["status"] for d in api.get("/api/documents").json()}
    assert states == {"old.txt": "failed", "new.txt": "processing"}


def test_conversation_rename_archive_and_isolation(api, monkeypatch):
    conversation = propose(api, monkeypatch)["conversation_id"]
    path = f"/api/conversations/{conversation}"
    assert api.patch(path, json={"title": "Acceso de incorporación"}).json()["title"] == (
        "Acceso de incorporación"
    )
    assert api.patch(path, json={}).status_code == 400
    assert api.patch(path, json={"archived": "yes"}).status_code == 422
    assert api.patch(path, json={"archived": True}).json()["archived"] is True
    assert api.get("/api/conversations").json() == []
    archived = api.get("/api/conversations?archived=true").json()
    assert [c["id"] for c in archived] == [conversation]
    # Archived history stays readable and its proposal remains decidable.
    assert api.get(path).json()["archived"] is True
    assert len(api.get("/api/actions").json()) == 1

    other = TestClient(main.app, headers={"Origin": "http://localhost:3000"})
    assert (
        other.post(
            "/api/auth/register",
            json={
                "email": "intruso@example.com",
                "password": "intruso-password-1",
                "workspace_name": "Intruso",
            },
        ).status_code
        == 201
    )
    assert other.get(path).status_code == 404
    assert other.patch(path, json={"title": "pwned"}).status_code == 404
    assert api.get(path).json()["title"] == "Acceso de incorporación"
    events = [e["type"] for e in api.get("/api/activity").json()]
    assert events.count("conversation.updated") == 2


def test_pool_survives_more_sequential_requests_than_its_size(api):
    for _ in range(settings.db_pool_max + 5):
        assert api.get("/api/documents").status_code == 200


def test_migration_005_backfills_existing_conversations_and_is_repeatable():
    import os
    from pathlib import Path

    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL required")
    schema = "mig005_" + uuid4().hex
    folder = Path(__file__).resolve().parents[2] / "database/init"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        scoped = make_conninfo(url, options=f"-c search_path={schema},public")
        with psycopg.connect(scoped) as conn:
            for path in sorted(folder.glob("00[1-4]_*.sql")):
                conn.execute(path.read_text())
            workspace = conn.execute("SELECT id FROM workspaces LIMIT 1").fetchone()[0]
            conversation = conn.execute(
                "INSERT INTO conversations(workspace_id,title,created_at)"
                " VALUES (%s,'Antigua',now()-interval '3 days') RETURNING id",
                (workspace,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO messages(conversation_id,role,content,created_at)"
                " VALUES (%s,'user','hola',now()-interval '1 day')",
                (conversation,),
            )
            before = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
            migration = (folder / "005_v2_reliability.sql").read_text()
            conn.execute(migration)
            conn.execute(migration)  # Idempotent if re-run.
            updated, archived = conn.execute(
                "SELECT updated_at::date = (now()-interval '1 day')::date, archived_at"
                " FROM conversations WHERE id=%s",
                (conversation,),
            ).fetchone()
            assert updated is True and archived is None
            assert conn.execute("SELECT count(*) FROM messages").fetchone()[0] == before
            assert conn.execute("SELECT to_regclass('chat_requests')").fetchone()[0]
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
