"""Document library: upload, indexing, reindexing, inspection and deletion.

Transaction policy: provider calls (embeddings) never run while a database
transaction or row lock is held. Each operation reads what it needs in a short
transaction, performs slow external work without a connection, then validates and
writes in one final transaction that re-checks the rows it depends on.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pgvector import Vector
from starlette.concurrency import run_in_threadpool

from .audit import audit
from .auth import CurrentUser, Principal
from .config import settings
from .db import get_conn
from .errors import provider_error
from .providers import ProviderUnavailable
from .rag import chunk_pages, embed_texts, embedding_collection, extract_pages

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
EMBED_BATCH = 64
SUPPORTED = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain", "text/x-markdown"},
}


def _document_row(r) -> dict:
    return {
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


@router.get("")
def list_documents(user: CurrentUser):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, page_count, chunk_count, status, created_at, mime_type,"
            " size_bytes, error, embedding_model, indexed_at, embedding_collection,"
            " embedding_dimensions FROM documents WHERE workspace_id=%s ORDER BY created_at DESC",
            (user.workspace_id,),
        ).fetchall()
    return [_document_row(r) for r in rows]


@router.get("/{document_id}/chunks")
def document_chunks(document_id: UUID, user: CurrentUser, offset: int = Query(0, ge=0)):
    with get_conn() as conn:
        doc = conn.execute(
            "SELECT filename,chunk_count FROM documents WHERE id=%s AND workspace_id=%s",
            (document_id, user.workspace_id),
        ).fetchone()
        if not doc:
            raise HTTPException(404, "Documento no encontrado")
        rows = conn.execute(
            "SELECT id,page_number,chunk_index,content,section FROM document_chunks"
            " WHERE document_id=%s AND workspace_id=%s ORDER BY chunk_index LIMIT 25 OFFSET %s",
            (document_id, user.workspace_id, offset),
        ).fetchall()
    return {
        "filename": doc[0],
        "total": doc[1],
        "offset": offset,
        "chunks": [
            {"id": r[0], "page": r[1], "index": r[2], "content": r[3], "section": r[4]}
            for r in rows
        ],
    }


@router.post("")
async def upload_document(file: Annotated[UploadFile, File()], user: CurrentUser):
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    filename = Path((file.filename or "document").replace("\\", "/")).name
    filename = "".join(c for c in filename if c.isprintable())[:200]
    return await run_in_threadpool(index_document, filename, file.content_type, raw, user)


def _embed_all(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        vectors.extend(embed_texts(texts[i : i + EMBED_BATCH]))
    return vectors


def index_document(filename: str, content_type: str | None, raw: bytes, user: Principal):
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "El archivo supera 20 MB")
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED or (
        content_type and content_type not in SUPPORTED[ext] | {"application/octet-stream"}
    ):
        raise HTTPException(400, "Extensión o MIME no admitido. Usa PDF, DOCX, TXT o MD.")
    try:
        collection = embedding_collection()
    except Exception as exc:
        raise provider_error(exc) from exc
    with get_conn() as conn:
        doc_id = conn.execute(
            "INSERT INTO documents(workspace_id,filename,mime_type,size_bytes,status,embedding_model,"
            "embedding_collection,embedding_dimensions) VALUES (%s,%s,%s,%s,'processing',%s,%s,%s)"
            " RETURNING id",
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
                "No se pudo extraer texto. Comprueba que el archivo no esté dañado, cifrado o sea"
                " un PDF escaneado.",
            ) from exc
        prepared = chunk_pages(pages, filename)
        if not prepared:
            raise HTTPException(400, "El documento no contiene texto extraíble")
        if len(prepared) > settings.max_document_chunks:
            raise HTTPException(413, "Demasiados fragmentos; divide el documento")
        embed_started = time.perf_counter()
        embeddings = _embed_all([chunk.content for chunk in prepared])
        embed_ms = int((time.perf_counter() - embed_started) * 1000)
        if collection != embedding_collection():
            raise RuntimeError("El modelo cambió durante la indexación")
        with get_conn() as conn:
            # A deletion during indexing must not resurrect the document.
            if not conn.execute(
                "SELECT id FROM documents WHERE id=%s AND workspace_id=%s FOR UPDATE",
                (doc_id, user.workspace_id),
            ).fetchone():
                raise HTTPException(409, "Documento eliminado durante la indexación")
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO document_chunks(document_id,workspace_id,page_number,chunk_index,"
                    "content,section,embedding) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    [
                        (
                            doc_id,
                            user.workspace_id,
                            chunk.page,
                            index,
                            chunk.content,
                            chunk.section,
                            Vector(vector),
                        )
                        for index, (chunk, vector) in enumerate(
                            zip(prepared, embeddings, strict=True)
                        )
                    ],
                )
            conn.execute(
                "UPDATE documents SET status='ready',error=NULL,page_count=%s,chunk_count=%s,"
                "indexed_at=now() WHERE id=%s",
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
                    "embedding_ms": embed_ms,
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
            audit(conn, user, "document.failed", {"document_id": str(doc_id), "error": detail})
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


@router.delete("/{document_id}")
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


def _fingerprint(rows) -> str:
    digest = hashlib.sha256()
    for chunk_id, content in rows:
        digest.update(f"{chunk_id}\x00{len(content)}\x00".encode())
        digest.update(content.encode())
    return digest.hexdigest()


@router.post("/{document_id}/reindex")
def reindex_document(document_id: UUID, user: CurrentUser):
    try:
        collection = embedding_collection()
        # 1. Short read: no lock is held while embeddings are computed.
        with get_conn() as conn:
            if not conn.execute(
                "SELECT 1 FROM documents WHERE id=%s AND workspace_id=%s",
                (document_id, user.workspace_id),
            ).fetchone():
                raise HTTPException(404, "Documento no encontrado")
            chunks = conn.execute(
                "SELECT id,content FROM document_chunks WHERE document_id=%s AND workspace_id=%s"
                " ORDER BY chunk_index",
                (document_id, user.workspace_id),
            ).fetchall()
        if not chunks:
            raise HTTPException(409, "Sin texto conservado; vuelve a subir el documento")
        # 2. Slow external work without a connection.
        vectors = _embed_all([row[1] for row in chunks])
        if collection != embedding_collection():
            raise RuntimeError("El modelo cambió durante la reindexación")
        # 3. Validate and write atomically; the deferred trigger checks consistency.
        with get_conn() as conn:
            if not conn.execute(
                "SELECT 1 FROM documents WHERE id=%s AND workspace_id=%s FOR UPDATE",
                (document_id, user.workspace_id),
            ).fetchone():
                raise HTTPException(404, "El documento se eliminó durante la reindexación")
            current = conn.execute(
                "SELECT id,content FROM document_chunks WHERE document_id=%s AND workspace_id=%s"
                " ORDER BY chunk_index FOR UPDATE",
                (document_id, user.workspace_id),
            ).fetchall()
            if _fingerprint(current) != _fingerprint(chunks):
                raise HTTPException(409, "El documento cambió durante la reindexación; reinténtalo")
            conn.execute(
                "UPDATE documents SET embedding_model=%s,embedding_collection=%s,"
                "embedding_dimensions=%s,status='ready',error=NULL,indexed_at=now() WHERE id=%s",
                (settings.embedding_model, collection, settings.vector_dimensions, document_id),
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE document_chunks SET embedding=%s,embedding_collection=%s WHERE id=%s",
                    [
                        (Vector(vector), collection, row[0])
                        for row, vector in zip(chunks, vectors, strict=True)
                    ],
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


def recover_interrupted_indexing() -> int:
    """Mark documents stuck in 'processing' after a crash/restart as failed.

    Indexing is synchronous and bounded by the HTTP request; anything still
    processing well beyond that window can never complete.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "UPDATE documents SET status='failed', error=%s WHERE status='processing'"
            " AND created_at < now() - interval '15 minutes' RETURNING id",
            ("Indexación interrumpida (reinicio del servidor). Vuelve a subir el archivo.",),
        ).fetchall()
    if rows:
        logger.info("Recovered %d interrupted indexing jobs", len(rows))
    return len(rows)
