from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from openai import OpenAIError
from pgvector import Vector
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from .agent import answer, describe_execution, requested_tools
from .auth import COOKIE, CurrentUser, Principal
from .auth import router as auth_router
from .config import settings
from .db import get_conn
from .providers import ProviderUnavailable, require_config
from .rag import embed_texts, embedding_collection, extract_pages, retrieve, split_text
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

app = FastAPI(title="MAZMI Ops Copilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


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


def audit(
    conn,
    user: Principal,
    event: str,
    details: dict,
    conversation_id=None,
    duration_ms=None,
):
    conn.execute(
        "INSERT INTO audit_events(workspace_id,user_id,conversation_id,event_type,actor,details,duration_ms) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)",
        (
            user.workspace_id,
            user.user_id,
            conversation_id,
            event,
            user.email,
            json.dumps(details, default=str),
            duration_ms,
        ),
    )


@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    logger.error("Database failure: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "Base de datos no disponible. Comprueba PostgreSQL y el esquema."},
    )


def require_provider(role="generation"):
    try:
        require_config(
            settings.embedding_provider if role == "embedding" else settings.generation_provider
        )
    except ProviderUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


def provider_error(exc):
    from .providers import ProviderQuotaExceeded

    if isinstance(exc, ProviderQuotaExceeded):
        return HTTPException(429, str(exc))
    if isinstance(exc, ProviderUnavailable):
        return HTTPException(503, str(exc))
    # Do not expose upstream errors: they may contain credentials or document content.
    logger.error("Provider failure: %s", type(exc).__name__)
    return HTTPException(
        502, "El proveedor de IA no pudo completar la solicitud. Inténtalo de nuevo."
    )


@app.get("/health")
def health():
    with get_conn() as conn:
        conn.execute("SELECT 1")
    return {
        "status": "ok",
        "openai_configured": bool(settings.openai_api_key),
        "generation_provider": "demo" if settings.demo_mode else settings.generation_provider,
        "embedding_provider": "demo" if settings.demo_mode else settings.embedding_provider,
    }


@app.get("/api/system")
def system_status(user: CurrentUser):
    """Configuration only: never implies a live provider connection or exposes secrets."""
    from .runtime import configuration

    return configuration()


@app.get("/api/documents/{document_id}/chunks")
def document_chunks(document_id: UUID, user: CurrentUser, offset: int = Query(0, ge=0)):
    with get_conn() as conn:
        doc = conn.execute(
            "SELECT filename,chunk_count FROM documents WHERE id=%s AND workspace_id=%s",
            (document_id, user.workspace_id),
        ).fetchone()
        if not doc:
            raise HTTPException(404, "Documento no encontrado")
        rows = conn.execute(
            "SELECT id,page_number,chunk_index,content FROM document_chunks WHERE document_id=%s AND workspace_id=%s ORDER BY chunk_index LIMIT 25 OFFSET %s",
            (document_id, user.workspace_id, offset),
        ).fetchall()
    return {
        "filename": doc[0],
        "total": doc[1],
        "offset": offset,
        "chunks": [{"id": r[0], "page": r[1], "index": r[2], "content": r[3]} for r in rows],
    }


@app.get("/api/actions")
def list_actions(user: CurrentUser):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id,action_name,payload,status,created_at,conversation_id FROM pending_actions WHERE workspace_id=%s AND requested_by=%s ORDER BY created_at DESC LIMIT 50",
            (user.workspace_id, user.user_id),
        ).fetchall()
    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "payload": r[2],
            "status": r[3],
            "created_at": r[4],
            "conversation_id": str(r[5]),
        }
        for r in rows
    ]


@app.get("/api/documents")
def list_documents(user: CurrentUser):
    with get_conn() as conn:
        workspace_id = user.workspace_id
        rows = conn.execute(
            "SELECT id, filename, page_count, chunk_count, status, created_at, mime_type, size_bytes, error, embedding_model, indexed_at, embedding_collection, embedding_dimensions FROM documents WHERE workspace_id=%s ORDER BY created_at DESC",
            (workspace_id,),
        ).fetchall()
    return [
        {
            "id": str(r[0]),
            "filename": r[1],
            "pages": r[2],
            "chunks": r[3],
            "status": r[4],
            "created_at": r[5],
            "mime_type": r[6],
            "size_bytes": r[7],
            "error": r[8],
            "embedding_model": r[9],
            "indexed_at": r[10],
            "embedding_collection": r[11],
            "embedding_dimensions": r[12],
        }
        for r in rows
    ]


@app.post("/api/documents")
async def upload_document(file: Annotated[UploadFile, File()], user: CurrentUser):
    raw = await file.read(20 * 1024 * 1024 + 1)
    await file.close()
    filename = Path((file.filename or "document").replace("\\", "/")).name
    filename = "".join(c for c in filename if c.isprintable())[:200]
    return await run_in_threadpool(index_document, filename, file.content_type, raw, user)


def index_document(filename: str, content_type: str | None, raw: bytes, user: Principal):
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "El archivo supera 20 MB")
    supported = {
        ".pdf": {"application/pdf"},
        ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        ".txt": {"text/plain"},
        ".md": {"text/markdown", "text/plain"},
    }
    ext = Path(filename).suffix.lower()
    if ext not in supported or (
        content_type and content_type not in supported[ext] | {"application/octet-stream"}
    ):
        raise HTTPException(400, "Extensión o MIME no admitido. Usa PDF, DOCX, TXT o MD.")
    require_provider("embedding")
    try:
        collection = embedding_collection()
    except Exception as exc:
        raise provider_error(exc) from exc
    with get_conn() as conn:
        doc_id = conn.execute(
            "INSERT INTO documents(workspace_id,filename,mime_type,size_bytes,status,embedding_model,embedding_collection,embedding_dimensions) VALUES (%s,%s,%s,%s,'processing',%s,%s,%s) RETURNING id",
            (
                user.workspace_id,
                filename,
                content_type,
                len(raw),
                settings.embedding_model,
                collection,
                settings.vector_dimensions,
            ),
        ).fetchone()[0]
    started = time.perf_counter()
    try:
        try:
            pages = extract_pages(filename, raw)
        except Exception as exc:
            raise HTTPException(
                400,
                "No se pudo extraer texto. Comprueba que el archivo no esté dañado, cifrado o sea un PDF escaneado.",
            ) from exc
        prepared = [(page, chunk) for page, text in pages for chunk in split_text(text)]
        if not prepared:
            raise HTTPException(400, "El documento no contiene texto extraíble")
        if len(prepared) > settings.max_document_chunks:
            raise HTTPException(413, "Demasiados fragmentos; divide el documento")
        embeddings = []
        for i in range(0, len(prepared), 64):
            embeddings.extend(embed_texts([x[1] for x in prepared[i : i + 64]]))
        if collection != embedding_collection():
            raise RuntimeError("El modelo cambió durante la indexación")
        with get_conn() as conn:
            # A deletion during indexing must not resurrect the document.
            if not conn.execute(
                "SELECT id FROM documents WHERE id=%s AND workspace_id=%s FOR UPDATE",
                (doc_id, user.workspace_id),
            ).fetchone():
                raise HTTPException(409, "Documento eliminado durante la indexación")
            for index, ((page, content), embedding) in enumerate(
                zip(prepared, embeddings, strict=True)
            ):
                conn.execute(
                    "INSERT INTO document_chunks(document_id,workspace_id,page_number,chunk_index,content,embedding) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        doc_id,
                        user.workspace_id,
                        page,
                        index,
                        content,
                        Vector(embedding),
                    ),
                )
            conn.execute(
                "UPDATE documents SET status='ready',page_count=%s,chunk_count=%s,indexed_at=now() WHERE id=%s",
                (len(pages), len(prepared), doc_id),
            )
            audit(
                conn,
                user,
                "document.indexed",
                {
                    "document_id": str(doc_id),
                    "filename": filename,
                    "chunks": len(prepared),
                    "model": settings.embedding_model,
                    "embedding_collection": collection,
                },
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
    except Exception as exc:
        detail = (
            str(exc)
            if isinstance(exc, ProviderUnavailable)
            else exc.detail
            if isinstance(exc, HTTPException)
            else "No se pudo completar la indexación; vuelve a subir el archivo"
        )
        with get_conn() as conn:
            conn.execute(
                "UPDATE documents SET status='failed',error=%s WHERE id=%s AND workspace_id=%s",
                (detail, doc_id, user.workspace_id),
            )
            audit(
                conn,
                user,
                "document.failed",
                {"document_id": str(doc_id), "error": detail},
            )
        if isinstance(exc, HTTPException):
            raise
        raise provider_error(exc) from exc
    return {
        "id": str(doc_id),
        "filename": filename,
        "pages": len(pages),
        "chunks": len(prepared),
        "status": "ready",
    }


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: UUID, user: CurrentUser):
    with get_conn() as conn:
        row = conn.execute(
            "DELETE FROM documents WHERE id=%s AND workspace_id=%s RETURNING filename",
            (document_id, user.workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Documento no encontrado")
        audit(
            conn,
            user,
            "document.deleted",
            {"document_id": str(document_id), "filename": row[0]},
        )
    return {"status": "deleted"}


@app.post("/api/documents/{document_id}/reindex")
def reindex_document(document_id: UUID, user: CurrentUser):
    require_provider("embedding")
    try:
        collection = embedding_collection()
        with get_conn() as conn:
            doc = conn.execute(
                "SELECT id FROM documents WHERE id=%s AND workspace_id=%s FOR UPDATE",
                (document_id, user.workspace_id),
            ).fetchone()
            if not doc:
                raise HTTPException(404, "Documento no encontrado")
            chunks = conn.execute(
                "SELECT id,content FROM document_chunks WHERE document_id=%s AND workspace_id=%s ORDER BY chunk_index FOR UPDATE",
                (document_id, user.workspace_id),
            ).fetchall()
            if not chunks:
                raise HTTPException(409, "Sin texto conservado; vuelve a subir el documento")
            vectors = []
            for offset in range(0, len(chunks), 64):
                vectors.extend(embed_texts([row[1] for row in chunks[offset : offset + 64]]))
            if collection != embedding_collection():
                raise RuntimeError("El modelo cambió durante la reindexación")
            conn.execute(
                "UPDATE documents SET embedding_model=%s,embedding_collection=%s,embedding_dimensions=%s,status='ready',error=NULL,indexed_at=now() WHERE id=%s",
                (settings.embedding_model, collection, settings.vector_dimensions, document_id),
            )
            for row, vector in zip(chunks, vectors, strict=True):
                conn.execute(
                    "UPDATE document_chunks SET embedding=%s,embedding_collection=%s WHERE id=%s",
                    (Vector(vector), collection, row[0]),
                )
            audit(
                conn,
                user,
                "document.reindexed",
                {
                    "document_id": str(document_id),
                    "embedding_collection": collection,
                    "chunks": len(chunks),
                },
            )
        return {"status": "ready", "embedding_collection": collection}
    except HTTPException:
        raise
    except Exception as exc:
        raise provider_error(exc) from exc


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, user: CurrentUser):
    return run_chat(payload, user)


class ChatCancelled(RuntimeError):
    pass


def run_chat(
    payload: ChatRequest,
    user: Principal,
    emit: Callable | None = None,
    cancelled: Event | None = None,
):
    require_provider()
    with get_conn() as conn:
        workspace_id = user.workspace_id
        conversation_id = str(payload.conversation_id) if payload.conversation_id else None
        if (
            conversation_id
            and not conn.execute(
                "SELECT id FROM conversations WHERE id=%s AND workspace_id=%s FOR UPDATE",
                (conversation_id, workspace_id),
            ).fetchone()
        ):
            raise HTTPException(404, "Conversación no encontrada")
        if not conversation_id:
            conversation_id = str(
                conn.execute(
                    "INSERT INTO conversations(workspace_id,title) VALUES (%s,%s) RETURNING id",
                    (workspace_id, payload.message[:70]),
                ).fetchone()[0]
            )
        history_rows = conn.execute(
            "SELECT role,content FROM messages WHERE conversation_id=%s ORDER BY id DESC LIMIT 12",
            (conversation_id,),
        ).fetchall()
        history = [{"role": r[0], "content": r[1][:4000]} for r in reversed(history_rows)]
        conn.execute(
            "INSERT INTO messages(conversation_id,role,content) VALUES (%s,'user',%s)",
            (conversation_id, payload.message),
        )
        try:
            retrieval_query = "\n".join(
                [m["content"] for m in history if m["role"] == "user"][-2:] + [payload.message]
            )[-12000:]
            retrieval_started = time.perf_counter()
            retrieval_meta = {}
            if requested_tools(payload.message, payload.mode):
                sources = []
                retrieval_meta = {"strategy": "tool_request_no_documents", "selected": []}
            else:
                sources = retrieve(
                    conn,
                    workspace_id,
                    retrieval_query,
                    limit=6,
                    diagnostics=retrieval_meta,
                    lexical_query=payload.message,
                )
            retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)

            def read_tickets(limit):
                rows = conn.execute(
                    "SELECT id,title,description,priority,status FROM tickets WHERE workspace_id=%s ORDER BY created_at DESC LIMIT %s",
                    (workspace_id, limit),
                ).fetchall()
                return [
                    {
                        "id": r[0],
                        "title": r[1],
                        "description": r[2],
                        "priority": r[3],
                        "status": r[4],
                    }
                    for r in rows
                ]

            text, pending, meta = answer(
                payload.message, sources, payload.mode, history, read_tickets, emit
            )
            meta.update(
                {
                    "generation_provider": "demo" if settings.demo_mode else settings.generation_provider,
                    "retrieval_ms": retrieval_ms,
                    "retrieval": retrieval_meta,
                    "retrieved_chunks": len(sources),
                    "source_chunk_ids": [s["chunk_id"] for s in sources],
                }
            )
            if cancelled and cancelled.is_set():
                raise ChatCancelled("Consulta cancelada antes de persistir")
            for tool_event in meta["tools"]:
                audit(conn, user, "tool.completed", tool_event, conversation_id)
        except ChatCancelled:
            raise
        except Exception as exc:
            raise provider_error(exc) from exc

        pending_action = None
        if pending:
            if payload.mode != "DO" or pending["name"] != "create_ticket":
                raise HTTPException(502, "Propuesta de acción no permitida")
            pending["payload"] = TicketPayload.model_validate(pending["payload"]).model_dump()
            action_id = str(
                conn.execute(
                    "INSERT INTO pending_actions(workspace_id,conversation_id,action_name,payload,requested_by) VALUES (%s,%s,%s,%s::jsonb,%s) RETURNING id",
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
                {
                    "action_id": action_id,
                    "name": pending["name"],
                    "payload": pending["payload"],
                },
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
            )
            for s in sources
        ]
        conn.execute(
            "INSERT INTO messages(conversation_id,role,content,sources) VALUES (%s,'assistant',%s,%s::jsonb)",
            (
                conversation_id,
                text,
                json.dumps([s.model_dump() for s in public_sources]),
            ),
        )
        audit(
            conn,
            user,
            "chat.completed",
            {"mode": payload.mode, **meta},
            conversation_id,
            meta["duration_ms"],
        )
        return ChatResponse(
            conversation_id=conversation_id,
            answer=text,
            sources=public_sources,
            pending_action=pending_action,
        )


@app.post("/api/actions/{action_id}/decision")
def decide_action(action_id: UUID, payload: ActionDecision, user: CurrentUser):
    action_id = str(action_id)
    with get_conn() as conn:
        workspace_id = user.workspace_id
        row = conn.execute(
            "SELECT action_name,payload,status,conversation_id FROM pending_actions WHERE id=%s AND workspace_id=%s AND requested_by=%s FOR UPDATE",
            (action_id, workspace_id, user.user_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Acción no encontrada")
        action_name, args, status, conversation_id = row
        if status != "PENDING":
            raise HTTPException(409, "La acción ya fue resuelta")
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
            "INSERT INTO tickets(workspace_id,title,description,priority) VALUES (%s,%s,%s,%s) RETURNING id,title,priority,status",
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
    # Execution is committed before the optional model narration. A provider failure
    # must never roll back a confirmed action or cause a second execution.
    try:
        result["summary"] = describe_execution(action_name, args, result)
    except (OpenAIError, RuntimeError, ValueError):
        result["summary"] = f"Ticket #{ticket[0]} creado tras tu confirmación."
    return result


@app.get("/api/activity")
def activity(user: CurrentUser):
    with get_conn() as conn:
        workspace_id = user.workspace_id
        rows = conn.execute(
            "SELECT id,event_type,actor,details,duration_ms,created_at FROM audit_events WHERE workspace_id=%s ORDER BY created_at DESC LIMIT 50",
            (workspace_id,),
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
        workspace_id = user.workspace_id
        rows = conn.execute(
            "SELECT id,title,priority,status,created_at FROM tickets WHERE workspace_id=%s ORDER BY created_at DESC LIMIT 50",
            (workspace_id,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "priority": r[2],
            "status": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


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


@app.get("/api/conversations")
def conversations(user: CurrentUser):
    with get_conn() as conn:
        workspace_id = user.workspace_id
        rows = conn.execute(
            "SELECT id,title,created_at FROM conversations WHERE workspace_id=%s ORDER BY created_at DESC LIMIT 50",
            (workspace_id,),
        ).fetchall()
    return [{"id": str(r[0]), "title": r[1], "created_at": r[2]} for r in rows]


@app.get("/api/conversations/{conversation_id}")
def conversation(conversation_id: UUID, user: CurrentUser):
    with get_conn() as conn:
        workspace_id = user.workspace_id
        if not conn.execute(
            "SELECT id FROM conversations WHERE id=%s AND workspace_id=%s",
            (conversation_id, workspace_id),
        ).fetchone():
            raise HTTPException(404, "Conversación no encontrada")
        rows = conn.execute(
            "SELECT role,content,sources FROM messages WHERE conversation_id=%s ORDER BY id",
            (conversation_id,),
        ).fetchall()
        actions = conn.execute(
            "SELECT id,action_name,payload FROM pending_actions WHERE conversation_id=%s AND workspace_id=%s AND status='PENDING' AND requested_by=%s ORDER BY created_at",
            (conversation_id, workspace_id, user.user_id),
        ).fetchall()
    return {
        "messages": [{"role": r[0], "content": r[1], "sources": r[2]} for r in rows],
        "pending_actions": [{"id": str(r[0]), "name": r[1], "payload": r[2]} for r in actions],
    }


@app.post("/api/chat/stream")
def stream_chat(payload: ChatRequest, user: CurrentUser, request: Request):
    require_provider()
    events: Queue = Queue()
    cancelled = Event()

    def emit(event):
        if cancelled.is_set():
            raise ChatCancelled("Cliente desconectado")
        events.put(event)

    def work():
        try:
            response = run_chat(payload, user, emit, cancelled)
            emit({"type": "done", "data": response.model_dump()})
        except ChatCancelled:
            pass
        except HTTPException as exc:
            events.put({"type": "error", "message": str(exc.detail)})
        except (OpenAIError, RuntimeError, ValueError, psycopg.Error) as exc:
            logger.error("Chat failed: %s", type(exc).__name__)
            events.put({"type": "error", "message": "No se pudo completar la respuesta"})
        finally:
            events.put(None)

    Thread(target=work, daemon=True).start()

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = events.get_nowait()
                except Empty:
                    await asyncio.sleep(0.05)
                    continue
                if event is None:
                    break
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        finally:
            # A synchronous provider call may finish before observing this flag.
            # Checkpoints before writes roll back an abandoned chat transaction.
            cancelled.set()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
