from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from docx import Document as DocxDocument
from pgvector import Vector
from pypdf import PdfReader

from .chunking import structured_chunks
from .config import settings
from .providers import embeddings_client

client = embeddings_client()


def split_text(text: str, chunk_size: int = 1200, overlap: int = 220) -> list[str]:
    if chunk_size < 1 or not 0 <= overlap < chunk_size // 2:
        raise ValueError("overlap debe ser menor que la mitad de chunk_size")
    clean = " ".join(text.replace("\x00", " ").split())
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        if end < len(clean):
            boundary = clean.rfind(". ", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary + 1
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


@dataclass(frozen=True)
class Chunk:
    page: int | None
    content: str
    section: str | None = None


def chunk_pages(pages: list[tuple[int | None, str]], filename: str = "") -> list[Chunk]:
    """Split extracted pages into stored chunks (page metadata only when real)."""
    if settings.chunking_strategy == "flat_v1":
        return [Chunk(page, chunk) for page, text in pages for chunk in split_text(text)]
    return [Chunk(page, chunk.content, chunk.section) for page, chunk in structured_chunks(pages)]


def _docx_text(doc) -> str:
    """Body text in document order: headings (by style), paragraphs, list items, tables."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    lines: list[str] = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(child, doc)
            text = paragraph.text.strip()
            if not text:
                lines.append("")
                continue
            style = (paragraph.style.name if paragraph.style is not None else "") or ""
            level = re.match(r"(?:Heading|Título|Titulo)\s*(\d)", style)
            if style == "Title" or level:
                lines.extend(["", "#" * (int(level[1]) if level else 1) + " " + text, ""])
            elif "List" in style:
                lines.append("- " + text)
            else:
                lines.extend([text, ""])
        elif tag == "tbl":
            lines.append("")
            for row in Table(child, doc).rows:
                cells = [" ".join(cell.text.split()).replace("|", "/") for cell in row.cells]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
    return "\n".join(lines)


def extract_pages(filename: str, raw: bytes) -> list[tuple[int | None, str]]:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        reader = PdfReader(BytesIO(raw))
        return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    if ext == ".docx":
        with ZipFile(BytesIO(raw)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("DOCX descomprimido demasiado grande")
        doc = DocxDocument(BytesIO(raw))
        if settings.chunking_strategy == "flat_v1":
            return [
                (
                    None,
                    "\n".join(
                        [p.text for p in doc.paragraphs]
                        + [
                            " | ".join(cell.text for cell in row.cells)
                            for table in doc.tables
                            for row in table.rows
                        ]
                    ),
                )
            ]
        return [(None, _docx_text(doc))]
    if ext in {".txt", ".md"}:
        return [(None, raw.decode("utf-8-sig"))]
    raise ValueError("Formato no soportado. Usa PDF, DOCX, TXT o MD.")


def embedding_revision():
    """Digest of the installed embedding model; part of every collection identity."""
    return client.digest(settings.embedding_model)


def embedding_collection():
    return (
        f"ollama:{settings.embedding_model}:{settings.vector_dimensions}:"
        f"{embedding_revision()}:retrieval-prefix-v1"
    )


def embed_texts(texts: list[str], *, query=False) -> list[list[float]]:
    before = embedding_collection()
    inputs = texts
    if settings.embedding_model.split(":")[0] == "embeddinggemma":
        # EmbeddingGemma's documented retrieval prompts.
        prefix = "task: search result | query: " if query else "title: none | text: "
        inputs = [prefix + text for text in texts]
    result = client.embeddings.create(
        model=settings.embedding_model, input=inputs, dimensions=settings.vector_dimensions
    )
    ordered = sorted(result.data, key=lambda item: item.index)
    if [item.index for item in ordered] != list(range(len(texts))) or any(
        len(item.embedding) != settings.vector_dimensions
        or not all(math.isfinite(v) for v in item.embedding)
        or not any(item.embedding)
        for item in ordered
    ):
        raise RuntimeError("Respuesta de embeddings incompatible con la colección configurada")
    if before != embedding_collection():
        raise RuntimeError("El modelo cambió durante el embedding; vuelve a intentarlo")
    return [item.embedding for item in ordered]


def embed_query(text: str) -> list[float]:
    return embed_texts([text], query=True)[0]


LEXEME = re.compile(r"^[\w-]{2,40}$")


def any_terms_query(conn, text: str) -> str | None:
    """OR of the Spanish lexemes in ``text`` (already stemmed, stop words removed).

    ``websearch_to_tsquery`` ANDs every term, so a natural question ("¿Cuántos días de
    vacaciones hay?") only matches chunks containing *all* its words. An OR query keeps
    any chunk that shares vocabulary; ``ts_rank_cd`` still ranks fuller matches first.
    Lexemes are produced by PostgreSQL and filtered to word characters before quoting.
    """
    lexemes = conn.execute(
        "SELECT tsvector_to_array(to_tsvector('spanish', %s))", (text[:2000],)
    ).fetchone()[0]
    safe = [lexeme for lexeme in lexemes if LEXEME.match(lexeme)][:48]
    return " | ".join(f"'{lexeme}'" for lexeme in safe) or None


def prepare_query(query: str) -> tuple[str, Vector]:
    """Embed a retrieval query outside any database transaction.

    Returns the collection identity observed before and after the provider call, so
    a configuration/model change during the call can never mix collections.
    """
    collection = embedding_collection()
    vector = Vector(embed_query(query))
    if collection != embedding_collection():
        raise RuntimeError("La colección cambió durante la consulta")
    return collection, vector


# A document that says it was replaced is not a current source (see evidence.visible_passages).
# PostgreSQL ARE, case-insensitive. Deliberately narrow: "sustituye a la versión de 2023" in a
# NEW policy must not mark that new policy as obsolete.
SUPERSEDED_SQL = (
    r"(sustituid[oa] por|reemplazad[oa] por|derogad[oa]|ya no est[aá] en vigor|"
    r"no est[aá] en vigor|versi[oó]n obsoleta|documento obsoleto|solo como hist[oó]rico)"
)


def mark_superseded(conn, workspace_id: str, sources: list[dict]) -> list[dict]:
    """Flag every source whose document text declares itself replaced or no longer in force."""
    ids = sorted({s["document_id"] for s in sources})
    flagged = (
        {
            str(row[0])
            for row in conn.execute(
                "SELECT DISTINCT document_id FROM document_chunks"
                " WHERE workspace_id=%s AND document_id = ANY(%s::uuid[]) AND content ~* %s",
                (workspace_id, ids, SUPERSEDED_SQL),
            ).fetchall()
        }
        if ids
        else set()
    )
    for source in sources:
        source["superseded"] = source["document_id"] in flagged
    return sources


def retrieve(
    conn,
    workspace_id: str,
    query: str,
    limit: int = 6,
    *,
    diagnostics=None,
    lexical_query=None,
    prepared: tuple[str, Vector] | None = None,
) -> list[dict]:
    """Workspace-scoped exact vector candidates + Spanish FTS, fused with RRF.

    Exact scoped distance avoids HNSW post-filter starvation across tenants.
    This deliberately favors recall for the current small corpus; benchmark before scaling.
    Cosine score remains separate from the fusion score (neither is confidence).
    """
    if not 1 <= limit <= 20:
        raise ValueError("limit debe estar entre 1 y 20")
    started = time.perf_counter()
    collection, vector = prepared if prepared is not None else prepare_query(query)
    candidate_limit = max(24, limit * 4)
    columns = "c.id,c.document_id,d.filename,c.page_number,c.content,c.section"
    filters = """c.workspace_id=%s AND d.workspace_id=%s
                 AND d.status='ready' AND d.embedding_collection=%s
                 AND c.embedding_collection=d.embedding_collection"""
    args = (workspace_id, workspace_id, collection)
    semantic = conn.execute(
        f"""WITH scoped AS MATERIALIZED (
            SELECT {columns},c.embedding FROM document_chunks c
            JOIN documents d ON d.id=c.document_id WHERE {filters}
        ) SELECT id,document_id,filename,page_number,content,section,
                 1-(embedding <=> %s) AS score
          FROM scoped ORDER BY embedding <=> %s,id LIMIT %s""",
        (*args, vector, vector, candidate_limit),
    ).fetchall()
    lexical_text = lexical_query if lexical_query is not None else query
    if settings.lexical_query_mode == "all_terms_v1":
        tsquery_sql, tsquery_arg = "websearch_to_tsquery('spanish',%s)", lexical_text
    else:
        tsquery_sql, tsquery_arg = "to_tsquery('simple',%s)", any_terms_query(conn, lexical_text)
    lexical = []
    if tsquery_arg:
        lexical = conn.execute(
            f"""WITH scoped AS MATERIALIZED (
                SELECT {columns},c.embedding,c.search_vector FROM document_chunks c
                JOIN documents d ON d.id=c.document_id WHERE {filters}
            ) SELECT id,document_id,filename,page_number,content,section,
                     1-(embedding <=> %s) AS score,ts_rank_cd(search_vector,q) AS lexical_score
              FROM scoped,{tsquery_sql} q
              WHERE search_vector @@ q ORDER BY lexical_score DESC,id LIMIT %s""",
            (*args, vector, tsquery_arg, candidate_limit),
        ).fetchall()
    semantic = [r for r in semantic if math.isfinite(r[6]) and r[6] >= settings.retrieval_min_score]
    candidates = {}
    for kind, rows in (("vector", semantic), ("lexical", lexical)):
        for rank, row in enumerate(rows, 1):
            item = candidates.setdefault(
                row[0],
                {
                    "chunk_id": row[0],
                    "document_id": str(row[1]),
                    "filename": row[2],
                    "page": row[3],
                    "excerpt": row[4],
                    "content": row[4],
                    "section": row[5],
                    "score": float(row[6]) if math.isfinite(row[6]) else 0.0,
                    "rrf_score": 0.0,
                    "vector_rank": None,
                    "lexical_rank": None,
                    "lexical_score": 0.0,
                },
            )
            item["rrf_score"] += 1 / (60 + rank)
            item[kind + "_rank"] = rank
            if kind == "lexical":
                item["lexical_score"] = float(row[7])
    ranked, seen = [], set()
    for item in sorted(candidates.values(), key=lambda s: (-s["rrf_score"], s["chunk_id"])):
        fingerprint = hashlib.sha256(" ".join(item["content"].casefold().split()).encode()).digest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        ranked.append(item)
    # Diversity: cap chunks per document in a first pass so a second relevant document
    # is not crowded out; then fill remaining slots in rank order (no recall loss when a
    # single document is relevant).
    cap = settings.retrieval_max_chunks_per_document
    selected, per_document, overflow = [], {}, []
    for item in ranked:
        if per_document.get(item["document_id"], 0) < cap:
            per_document[item["document_id"]] = per_document.get(item["document_id"], 0) + 1
            selected.append(item)
        else:
            overflow.append(item)
        if len(selected) == limit:
            break
    for item in overflow:
        if len(selected) == limit:
            break
        selected.append(item)
    selected.sort(key=lambda s: (-s["rrf_score"], s["chunk_id"]))
    meta = {
        "strategy": "hybrid_rrf_v2",
        "lexical_query_mode": settings.lexical_query_mode,
        "embedding_collection": collection,
        "vector_candidates": len(semantic),
        "lexical_candidates": len(lexical),
        "unique_candidates": len(candidates),
        "selected": [
            {
                k: s[k]
                for k in (
                    "chunk_id",
                    "document_id",
                    "score",
                    "rrf_score",
                    "vector_rank",
                    "lexical_rank",
                    "lexical_score",
                )
            }
            for s in selected
        ],
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "abstention_reason": None if selected else "no_retrieval_evidence",
    }
    if diagnostics is not None:
        diagnostics.update(meta)
    logging.getLogger(__name__).info("retrieval %s", json.dumps(meta))
    return selected
