"""MAZMI Ops Copilot API.

Chat turns run in explicit phases so PostgreSQL never holds a transaction or row
lock while a provider computes embeddings or generates (tens of seconds locally):

1. ``preflight_chat``  – pure validation: tool gate, limits, provider requirements.
2. ``load_history``    – short read-only transaction (conversation scope + history).
3. ``gather_sources``  – query embedding without a connection, then a short SQL read.
4. ``answer``          – provider work, with no connection held.
5. ``persist_turn``    – one atomic write that re-checks scope, cited chunks and
                         idempotency, then stores messages, proposal and audit.

Cancellation (disconnect/timeout) is checked between phases and inside the final
transaction before commit, so an abandoned turn leaves no partial rows.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from io import BytesIO
from threading import BoundedSemaphore, Event, Lock, Thread
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from .agent import (
    READ_TOOL,
    TicketQueryError,
    answer,
    describe_execution,
    direct_ticket_query,
    explicit_ticket_limit,
    requested_tools,
)
from .audit import audit
from .auth import COOKIE, CurrentUser, Principal
from .auth import router as auth_router
from .config import settings
from .conversations import router as conversations_router
from .db import DatabaseBusy, close_pool, get_conn
from .documents import recover_interrupted_indexing
from .documents import router as documents_router
from .errors import provider_error
from .rag import mark_superseded, prepare_query, retrieve
from .schemas import (
    ActionDecision,
    ChatRequest,
    ChatResponse,
    PendingAction,
    Source,
    TicketPayload,
    VoiceRequest,
)
from .speech import synthesize, transcribe
from .streaming import StreamCancelled, sse_response

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _recover_in_background() -> None:
    try:
        recover_interrupted_indexing()
    except (psycopg.Error, DatabaseBusy) as exc:
        logger.error("Indexing recovery skipped: %s", type(exc).__name__)


def _warm_up_in_background() -> None:
    from .providers import Ollama

    loaded = Ollama().warm_up()
    logger.info("Ollama warm-up: %d of 2 models loaded", len(loaded))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup never waits on the database or on Ollama: both steps are best-effort and
    # asynchronous.
    Thread(target=_recover_in_background, daemon=True, name="mazmi-recovery").start()
    if settings.ollama_warmup:
        Thread(target=_warm_up_in_background, daemon=True, name="mazmi-warmup").start()
    yield
    await run_in_threadpool(close_pool)


app = FastAPI(title="MAZMI Ops Copilot API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(conversations_router)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = str(uuid4())
    started = time.perf_counter()
    origin = request.headers.get("origin")
    allowed = {x.strip() for x in settings.cors_origins.split(",")}
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        (origin and origin not in allowed) or (request.cookies.get(COOKIE) and not origin)
    ):
        return JSONResponse(status_code=403, content={"detail": "Origen no permitido"})
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }
        )
    )
    return response


@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    logger.error("Database failure: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "Base de datos no disponible. Comprueba PostgreSQL y el esquema."},
    )


@app.exception_handler(DatabaseBusy)
async def database_busy(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health")
def health():
    with get_conn() as conn:
        conn.execute("SELECT 1")
    return {
        "status": "ok",
        "version": app.version,
        "generation_provider": settings.generation_provider,
        "embedding_provider": settings.embedding_provider,
    }


@app.get("/api/system")
def system_status(user: CurrentUser):
    """Configuration only: never implies a live provider connection or exposes secrets."""
    from .runtime import configuration

    return configuration()


@app.post("/api/system/check-local")
def verify_local_provider(user: CurrentUser):
    """Explicit local fixture inference. Never invoked by a settings GET."""
    from .runtime import LocalCheckBusy, configuration, verify_local

    try:
        verify_local()
    except LocalCheckBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise provider_error(exc) from exc
    return configuration()


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class ChatCancelled(StreamCancelled):
    pass


def check_cancelled(cancelled: Event | None) -> None:
    if cancelled is not None and cancelled.is_set():
        raise ChatCancelled("Consulta cancelada antes de persistir")


_slot_lock = Lock()
_slots: tuple[int, BoundedSemaphore] | None = None


def _generation_slots() -> BoundedSemaphore:
    global _slots
    with _slot_lock:
        if _slots is None or _slots[0] != settings.chat_max_concurrent:
            _slots = (settings.chat_max_concurrent, BoundedSemaphore(settings.chat_max_concurrent))
        return _slots[1]


@contextmanager
def generation_slot(emit: Callable | None, cancelled: Event | None):
    """Bound concurrent model-backed turns; queue briefly, then fail clearly (503)."""
    slots = _generation_slots()
    if not slots.acquire(blocking=False):
        if emit:
            emit(
                {
                    "type": "status",
                    "stage": "queued",
                    "text": "En cola: el modelo está atendiendo otra consulta…",
                }
            )
        deadline = time.monotonic() + settings.chat_queue_timeout_seconds
        while True:
            check_cancelled(cancelled)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HTTPException(
                    503,
                    "El copiloto está atendiendo otras consultas. Inténtalo de nuevo en unos"
                    " segundos.",
                )
            if slots.acquire(timeout=min(0.25, remaining)):
                break
    try:
        yield
    finally:
        slots.release()


def preflight_chat(payload: ChatRequest) -> bool:
    """Validate a turn before any write or stream: returns True for model-free reads.

    Exact, unfiltered ticket reads are answered from the database with zero model calls.
    Every other turn reaches the local Ollama server; an unreachable server or missing
    model is reported as a sanitized 503 by the provider adapter.
    """
    try:
        tools = requested_tools(payload.message, payload.mode)
        limit = explicit_ticket_limit(payload.message) if tools == [READ_TOOL] else None
        direct_read = tools == [READ_TOOL] and (
            direct_ticket_query(payload.message, limit) is not None
        )
    except TicketQueryError as exc:
        raise HTTPException(400, str(exc)) from exc
    return direct_read


def check_conversation(conversation_id, user: Principal) -> None:
    if conversation_id is None:
        return
    with get_conn() as conn:
        if not conn.execute(
            "SELECT 1 FROM conversations WHERE id=%s AND workspace_id=%s",
            (conversation_id, user.workspace_id),
        ).fetchone():
            raise HTTPException(404, "Conversación no encontrada")


def _stored_response(conn, user: Principal, request_id: UUID) -> ChatResponse | None:
    row = conn.execute(
        "SELECT workspace_id,response FROM chat_requests WHERE user_id=%s AND request_id=%s",
        (user.user_id, request_id),
    ).fetchone()
    if not row:
        return None
    if str(row[0]) != user.workspace_id:
        raise HTTPException(409, "Ese identificador de petición pertenece a otro workspace")
    response = ChatResponse.model_validate(row[1])
    if response.pending_action is not None:
        status = conn.execute(
            "SELECT status FROM pending_actions WHERE id=%s AND workspace_id=%s",
            (response.pending_action.id, user.workspace_id),
        ).fetchone()
        if not status or status[0] != "PENDING":
            # Replays never resurrect an action that has since been decided.
            response.pending_action = None
    return response


def replay_chat(payload: ChatRequest, user: Principal) -> ChatResponse | None:
    if payload.client_request_id is None:
        return None
    with get_conn() as conn:
        return _stored_response(conn, user, payload.client_request_id)


def load_history(conversation_id: str | None, user: Principal) -> list[dict]:
    if not conversation_id:
        return []
    with get_conn() as conn:
        if not conn.execute(
            "SELECT 1 FROM conversations WHERE id=%s AND workspace_id=%s",
            (conversation_id, user.workspace_id),
        ).fetchone():
            raise HTTPException(404, "Conversación no encontrada")
        rows = conn.execute(
            "SELECT role,content FROM messages WHERE conversation_id=%s ORDER BY id DESC LIMIT 12",
            (conversation_id,),
        ).fetchall()
    return [{"role": r[0], "content": r[1][:4000]} for r in reversed(rows)]


def gather_sources(payload: ChatRequest, history: list[dict], user: Principal):
    retrieval_query = "\n".join(
        [m["content"] for m in history if m["role"] == "user"][-2:] + [payload.message]
    )[-12000:]
    started = time.perf_counter()
    prepared = prepare_query(retrieval_query)  # Provider call: no connection held.
    embedding_ms = int((time.perf_counter() - started) * 1000)
    diagnostics: dict = {}
    with get_conn() as conn:
        sources = retrieve(
            conn,
            user.workspace_id,
            retrieval_query,
            limit=6,
            diagnostics=diagnostics,
            lexical_query=payload.message,
            prepared=prepared,
        )
        mark_superseded(conn, user.workspace_id, sources)
    diagnostics["embedding_ms"] = embedding_ms
    return sources, diagnostics, int((time.perf_counter() - started) * 1000)


def read_tickets_for(user: Principal):
    def read_tickets(limit):
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id,title,priority,status FROM tickets WHERE workspace_id=%s"
                " ORDER BY created_at DESC,id DESC LIMIT %s",
                (user.workspace_id, limit),
            ).fetchall()
        return [{"id": r[0], "title": r[1], "priority": r[2], "status": r[3]} for r in rows]

    return read_tickets


def validate_pending(pending: dict | None, payload: ChatRequest) -> dict | None:
    if not pending:
        return None
    if (
        payload.mode != "DO"
        or pending.get("name") != "create_ticket"
        or "create_ticket"
        not in {tool["name"] for tool in requested_tools(payload.message, payload.mode)}
    ):
        raise HTTPException(502, "Propuesta de acción no permitida")
    try:
        payload_data = TicketPayload.model_validate(pending["payload"]).model_dump()
    except (ValidationError, KeyError, TypeError) as exc:
        raise HTTPException(502, "Propuesta de acción no válida") from exc
    return {"name": "create_ticket", "payload": payload_data}


def persist_turn(
    payload: ChatRequest,
    user: Principal,
    conversation_id: str | None,
    text: str,
    sources: list[dict],
    pending: dict | None,
    meta: dict,
    cancelled: Event | None,
) -> ChatResponse:
    workspace_id = user.workspace_id
    with get_conn() as conn:
        request_id = payload.client_request_id
        if request_id is not None:
            # Serialize duplicates of the same request; the loser replays the winner.
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"chat:{user.user_id}:{request_id}",),
            )
            stored = _stored_response(conn, user, request_id)
            if stored is not None:
                return stored
        if conversation_id:
            if not conn.execute(
                "SELECT 1 FROM conversations WHERE id=%s AND workspace_id=%s FOR UPDATE",
                (conversation_id, workspace_id),
            ).fetchone():
                raise HTTPException(404, "Conversación no encontrada")
        else:
            conversation_id = str(
                conn.execute(
                    "INSERT INTO conversations(workspace_id,title) VALUES (%s,%s) RETURNING id",
                    (workspace_id, payload.message[:70]),
                ).fetchone()[0]
            )
        chunk_ids = sorted({s["chunk_id"] for s in sources})
        if chunk_ids:
            # Evidence must still exist, be ready and belong to this workspace at commit.
            alive = conn.execute(
                "SELECT count(*) FROM document_chunks c JOIN documents d ON d.id=c.document_id"
                " WHERE c.id = ANY(%s) AND c.workspace_id=%s AND d.workspace_id=%s"
                " AND d.status='ready' AND c.embedding_collection=d.embedding_collection",
                (chunk_ids, workspace_id, workspace_id),
            ).fetchone()[0]
            if alive != len(chunk_ids):
                raise HTTPException(
                    409,
                    "Un documento consultado se eliminó o cambió durante la respuesta. No se"
                    " guardó nada; vuelve a preguntar.",
                )
        conn.execute(
            "INSERT INTO messages(conversation_id,role,content) VALUES (%s,'user',%s)",
            (conversation_id, payload.message),
        )
        for tool_event in meta["tools"]:
            audit(conn, user, "tool.completed", tool_event, conversation_id)
        pending_action = None
        if pending:
            action_id = str(
                conn.execute(
                    "INSERT INTO pending_actions(workspace_id,conversation_id,action_name,payload,"
                    "requested_by) VALUES (%s,%s,%s,%s::jsonb,%s) RETURNING id",
                    (
                        workspace_id,
                        conversation_id,
                        pending["name"],
                        json.dumps(pending["payload"]),
                        user.user_id,
                    ),
                ).fetchone()[0]
            )
            audit(
                conn,
                user,
                "action.proposed",
                {"action_id": action_id, "name": pending["name"], "payload": pending["payload"]},
                conversation_id,
            )
            pending_action = PendingAction(
                id=action_id, name=pending["name"], payload=pending["payload"]
            )
        public_sources = [
            Source(
                chunk_id=s["chunk_id"],
                document_id=s["document_id"],
                filename=s["filename"],
                page=s["page"],
                excerpt=s["excerpt"],
                score=s["score"],
                section=s.get("section"),
                superseded=bool(s.get("superseded")),
            )
            for s in sources
        ]
        conn.execute(
            "INSERT INTO messages(conversation_id,role,content,sources)"
            " VALUES (%s,'assistant',%s,%s::jsonb)",
            (conversation_id, text, json.dumps([s.model_dump() for s in public_sources])),
        )
        conn.execute(
            "UPDATE conversations SET updated_at=now(), archived_at=NULL WHERE id=%s",
            (conversation_id,),
        )
        audit(
            conn,
            user,
            "chat.completed",
            {"mode": payload.mode, **meta},
            conversation_id,
            meta["duration_ms"],
        )
        response = ChatResponse(
            conversation_id=conversation_id,
            answer=text,
            sources=public_sources,
            pending_action=pending_action,
        )
        if request_id is not None:
            conn.execute(
                "DELETE FROM chat_requests WHERE user_id=%s AND created_at < now()-interval '1 day'",
                (user.user_id,),
            )
            conn.execute(
                "INSERT INTO chat_requests(user_id,request_id,workspace_id,conversation_id,response)"
                " VALUES (%s,%s,%s,%s,%s::jsonb)",
                (
                    user.user_id,
                    request_id,
                    workspace_id,
                    conversation_id,
                    response.model_dump_json(),
                ),
            )
        # Last checkpoint inside the transaction: a disconnect now rolls everything back.
        check_cancelled(cancelled)
        return response


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, user: CurrentUser):
    return run_chat(payload, user)


def run_chat(
    payload: ChatRequest,
    user: Principal,
    emit: Callable | None = None,
    cancelled: Event | None = None,
) -> ChatResponse:
    direct_read = preflight_chat(payload)
    replayed = replay_chat(payload, user)
    if replayed is not None:
        return replayed
    conversation_id = str(payload.conversation_id) if payload.conversation_id else None
    history = load_history(conversation_id, user)
    tools = requested_tools(payload.message, payload.mode)
    read_tickets = read_tickets_for(user)
    try:
        if direct_read:
            sources, retrieval_meta, retrieval_ms = [], {"strategy": "tool_request_no_documents"}, 0
            text, pending, meta = answer(
                payload.message, sources, payload.mode, history, read_tickets, emit
            )
        else:
            with generation_slot(emit, cancelled):
                check_cancelled(cancelled)
                if tools:
                    sources = []
                    retrieval_meta = {"strategy": "tool_request_no_documents", "selected": []}
                    retrieval_ms = 0
                else:
                    if emit:
                        emit({"type": "status", "stage": "retrieving", "text": "Buscando fuentes…"})
                    sources, retrieval_meta, retrieval_ms = gather_sources(payload, history, user)
                    check_cancelled(cancelled)
                text, pending, meta = answer(
                    payload.message, sources, payload.mode, history, read_tickets, emit
                )
    except (ChatCancelled, HTTPException, psycopg.Error, DatabaseBusy):
        raise
    except Exception as exc:
        raise provider_error(exc) from exc
    check_cancelled(cancelled)
    pending = validate_pending(pending, payload)
    meta.update(
        {
            "generation_provider": settings.generation_provider,
            "retrieval_ms": retrieval_ms,
            "retrieval": retrieval_meta,
            "retrieved_chunks": len(sources),
            "source_chunk_ids": [s["chunk_id"] for s in sources],
        }
    )
    if emit:
        emit({"type": "status", "stage": "saving", "text": "Guardando la respuesta…"})
    return persist_turn(payload, user, conversation_id, text, sources, pending, meta, cancelled)


@app.post("/api/chat/stream")
async def stream_chat(payload: ChatRequest, user: CurrentUser, request: Request):
    # Validation errors keep real HTTP status codes; only accepted turns stream.
    await run_in_threadpool(preflight_chat, payload)
    await run_in_threadpool(check_conversation, payload.conversation_id, user)

    def work(emit, cancelled):
        return run_chat(payload, user, emit, cancelled).model_dump(mode="json")

    return sse_response(
        request,
        work,
        timeout=settings.chat_stream_timeout_seconds,
        cancelled_exc=ChatCancelled,
        initial=[{"type": "status", "stage": "accepted", "text": "Consulta recibida…"}],
    )


# ---------------------------------------------------------------------------
# Human approval
# ---------------------------------------------------------------------------

STATUS_LABELS = {"EXECUTED": "ejecutada", "REJECTED": "rechazada", "APPROVED": "aprobada"}


@app.get("/api/actions")
def list_actions(user: CurrentUser):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id,action_name,payload,status,created_at,conversation_id,resolved_at"
            " FROM pending_actions WHERE workspace_id=%s AND requested_by=%s"
            " ORDER BY created_at DESC LIMIT 50",
            (user.workspace_id, user.user_id),
        ).fetchall()
    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "payload": r[2],
            "status": r[3],
            "created_at": r[4],
            "conversation_id": str(r[5]) if r[5] else None,
            "resolved_at": r[6],
        }
        for r in rows
    ]


@app.post("/api/actions/{action_id}/decision")
def decide_action(action_id: UUID, payload: ActionDecision, user: CurrentUser):
    action_id = str(action_id)
    with get_conn() as conn:
        workspace_id = user.workspace_id
        row = conn.execute(
            "SELECT action_name,payload,status,conversation_id FROM pending_actions"
            " WHERE id=%s AND workspace_id=%s AND requested_by=%s FOR UPDATE",
            (action_id, workspace_id, user.user_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Acción no encontrada")
        action_name, args, status, conversation_id = row
        if status != "PENDING":
            # Exactly-once: a repeated or concurrent decision never re-executes.
            raise HTTPException(
                409, f"La acción ya fue resuelta ({STATUS_LABELS.get(status, status.lower())})."
            )
        if not payload.approved:
            conn.execute(
                "UPDATE pending_actions SET status='REJECTED',resolved_at=now() WHERE id=%s",
                (action_id,),
            )
            audit(
                conn,
                user,
                "action.rejected",
                {"action_id": action_id, "name": action_name, "arguments": args},
                conversation_id,
            )
            conn.execute(
                "INSERT INTO messages(conversation_id,role,content) VALUES (%s,'assistant',%s)",
                (conversation_id, "Acción rechazada por el usuario. No se ejecutó."),
            )
            return {"status": "rejected"}

        if action_name != "create_ticket":
            raise HTTPException(400, "Tool no soportada")
        try:
            args = TicketPayload.model_validate(args).model_dump()
        except ValidationError as exc:
            raise HTTPException(409, "La acción almacenada no es válida") from exc
        ticket = conn.execute(
            "INSERT INTO tickets(workspace_id,title,description,priority) VALUES (%s,%s,%s,%s)"
            " RETURNING id,title,priority,status",
            (workspace_id, args["title"], args["description"], args["priority"]),
        ).fetchone()
        conn.execute(
            "UPDATE pending_actions SET status='EXECUTED',resolved_at=now() WHERE id=%s",
            (action_id,),
        )
        audit(
            conn,
            user,
            "action.executed",
            {
                "action_id": action_id,
                "name": action_name,
                "arguments": args,
                "ticket_id": ticket[0],
            },
            conversation_id,
        )
        conn.execute(
            "INSERT INTO messages(conversation_id,role,content) VALUES (%s,'assistant',%s)",
            (
                conversation_id,
                f"Acción ejecutada tras confirmación humana. Ticket #{ticket[0]}: {ticket[1]}",
            ),
        )
        result = {
            "status": "executed",
            "ticket": {
                "id": ticket[0],
                "title": ticket[1],
                "priority": ticket[2],
                "status": ticket[3],
            },
        }
    # Render the committed receipt without another model call. Formatting must
    # never roll back a confirmed action or cause a second execution.
    try:
        result["summary"] = describe_execution(action_name, args, result)
    except (RuntimeError, ValueError):
        result["summary"] = f"Ticket #{ticket[0]} creado tras tu confirmación."
    return result


@app.get("/api/activity")
def activity(user: CurrentUser):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id,event_type,actor,details,duration_ms,created_at FROM audit_events"
            " WHERE workspace_id=%s ORDER BY created_at DESC, id DESC LIMIT 50",
            (user.workspace_id,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "type": r[1],
            "actor": r[2],
            "details": r[3],
            "duration_ms": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


@app.get("/api/tickets")
def tickets(user: CurrentUser):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id,title,priority,status,created_at FROM tickets WHERE workspace_id=%s"
            " ORDER BY created_at DESC LIMIT 50",
            (user.workspace_id,),
        ).fetchall()
    return [
        {"id": r[0], "title": r[1], "priority": r[2], "status": r[3], "created_at": r[4]}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Optional voice
# ---------------------------------------------------------------------------


@app.post("/api/voice/speak")
def speak(payload: VoiceRequest, user: CurrentUser):
    try:
        data, media_type = synthesize(payload.text)
    except Exception as exc:
        raise provider_error(exc) from exc
    return StreamingResponse(BytesIO(data), media_type=media_type)


@app.post("/api/voice/transcribe")
async def voice_transcribe(file: Annotated[UploadFile, File()], user: CurrentUser):
    data = await file.read(10 * 1024 * 1024 + 1)
    await file.close()
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Audio vacío o mayor de 10 MB")
    try:
        return {"text": await run_in_threadpool(transcribe, data)}
    except Exception as exc:
        raise provider_error(exc) from exc
