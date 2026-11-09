"""Paired retrieval benchmark for the MAZMI 2.0 RAG changes (ablation study).

Compares the exact v1 retrieval configuration with each v2 change in isolation and
combined, on the same corpus and the same query vectors:

* chunking:        flat_v1  vs structured_v2
* lexical branch:  all_terms_v1 (websearch_to_tsquery) vs any_terms_v2 (OR of lexemes)
* diversity:       20 chunks/document (effectively off) vs 3 chunks/document

Metrics (answerable questions only): evidence Recall@3/@6 (fraction of gold phrases
contained in the top-k chunks), full-evidence hit rate, MRR of the first chunk that
contains a gold phrase, and document recall. Latencies are reported as p50/p95.

Evidence categories are explicit in the report:
* ``--embeddings ollama``    real EmbeddingGemma vectors via the configured Ollama.
* ``--embeddings synthetic`` deterministic hashed bag-of-words vectors: SQL/plumbing
                             evidence only, never a semantic-quality claim.

Safety: requires a database whose name ends in ``_eval``. Every run creates its own
schemas and drops only those schemas. No documents leave the machine.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from . import rag
from .config import settings

EVALS = Path(__file__).resolve().parents[1] / "evals"
MIGRATIONS = Path(__file__).resolve().parents[2] / "database" / "init"
CONFIGS = [
    ("flat_v1", "all_terms_v1", 20),  # exact v1 behaviour (baseline)
    ("structured_v2", "all_terms_v1", 20),
    ("flat_v1", "any_terms_v2", 20),
    ("flat_v1", "all_terms_v1", 3),
    ("structured_v2", "any_terms_v2", 20),
    ("structured_v2", "any_terms_v2", 3),  # v2 default
]


def squash(text: str) -> str:
    return " ".join(text.split())


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return round(ordered[index], 2)


def score_question(question: dict, rows: list[dict]) -> dict:
    contents = [squash(r["content"]) for r in rows]
    gold = question["gold"]
    found_at = []
    for _, phrase in gold:
        rank = next((i for i, c in enumerate(contents, 1) if squash(phrase) in c), None)
        found_at.append(rank)
    first = min((r for r in found_at if r), default=None)
    gold_docs = {doc for doc, _ in gold}
    return {
        "name": question["name"],
        "category": question["category"],
        "evidence_recall_at_3": sum(1 for r in found_at if r and r <= 3) / len(gold),
        "evidence_recall_at_6": sum(1 for r in found_at if r and r <= 6) / len(gold),
        "full_evidence_at_6": all(r and r <= 6 for r in found_at),
        "reciprocal_rank": 1 / first if first else 0.0,
        "document_recall_at_6": len(gold_docs & {r["filename"] for r in rows}) / len(gold_docs),
        "gold_ranks": found_at,
    }


@contextmanager
def isolated_schema(base_url: str):
    schema = "rag_eval_" + uuid4().hex[:12]
    with psycopg.connect(base_url, autocommit=True) as admin:
        admin.execute("CREATE EXTENSION IF NOT EXISTS vector")
        admin.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    url = make_conninfo(base_url, options=f"-c search_path={schema},public")
    try:
        with psycopg.connect(url) as conn:
            for path in sorted(MIGRATIONS.glob("*.sql")):
                conn.execute(path.read_text())
        yield url
    finally:
        with psycopg.connect(base_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def synthetic_client():
    from .demo import vector

    return NS(
        embeddings=NS(
            create=lambda *, model, input, dimensions: NS(
                data=[NS(index=i, embedding=vector(t, dimensions)) for i, t in enumerate(input)]
            )
        )
    )


def run(embeddings: str) -> dict:
    database = conninfo_to_dict(settings.database_url).get("dbname", "")
    if not database.endswith("_eval"):
        raise ValueError("Requires a dedicated database ending in _eval")
    if embeddings == "ollama" and (settings.embedding_provider != "ollama" or settings.demo_mode):
        raise ValueError("--embeddings ollama requires EMBEDDING_PROVIDER=ollama")
    if embeddings == "synthetic":
        rag.client = synthetic_client()
        settings.embedding_provider = "openai"  # Label only; never contacted.
        settings.embedding_revision = "synthetic-hash"
    corpus = json.loads((EVALS / "v2_retrieval_corpus.json").read_text())
    base_url = settings.database_url
    collection = rag.embedding_collection()
    query_vectors, query_ms = {}, []
    for question in corpus["questions"]:
        started = time.perf_counter()
        query_vectors[question["name"]] = Vector(rag.embed_query(question["question"]))
        query_ms.append((time.perf_counter() - started) * 1000)
    report_configs, indexing = [], {}
    for chunking in ("flat_v1", "structured_v2"):
        settings.chunking_strategy = chunking
        with isolated_schema(base_url) as url, psycopg.connect(url) as conn:
            register_vector(conn)
            workspace = conn.execute(
                "INSERT INTO workspaces(name,slug) VALUES ('Eval',%s) RETURNING id",
                (uuid4().hex,),
            ).fetchone()[0]
            lengths, embed_ms = [], 0.0
            for doc in corpus["documents"]:
                pages = rag.extract_pages(doc["filename"], doc["text"].encode())
                chunks = rag.chunk_pages(pages, doc["filename"])
                started = time.perf_counter()
                vectors = rag.embed_texts([c.content for c in chunks])
                embed_ms += (time.perf_counter() - started) * 1000
                document = conn.execute(
                    "INSERT INTO documents(workspace_id,filename,status,embedding_collection,"
                    "embedding_dimensions,chunk_count) VALUES (%s,%s,'ready',%s,%s,%s)"
                    " RETURNING id",
                    (workspace, doc["filename"], collection, len(vectors[0]), len(chunks)),
                ).fetchone()[0]
                for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                    lengths.append(len(chunk.content))
                    conn.execute(
                        "INSERT INTO document_chunks(document_id,workspace_id,page_number,"
                        "chunk_index,content,section,embedding) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (
                            document,
                            workspace,
                            chunk.page,
                            index,
                            chunk.content,
                            chunk.section,
                            Vector(vector),
                        ),
                    )
            indexing[chunking] = {
                "chunks": len(lengths),
                "mean_chunk_chars": round(statistics.mean(lengths), 1),
                "max_chunk_chars": max(lengths),
                "embedding_ms_total": round(embed_ms, 1),
            }
            conn.commit()
            for config_chunking, lexical, cap in CONFIGS:
                if config_chunking != chunking:
                    continue
                settings.lexical_query_mode = lexical
                settings.retrieval_max_chunks_per_document = cap
                scored, latencies, negatives = [], [], []
                for question in corpus["questions"]:
                    meta = {}
                    started = time.perf_counter()
                    rows = rag.retrieve(
                        conn,
                        str(workspace),
                        question["question"],
                        limit=6,
                        diagnostics=meta,
                        prepared=(collection, query_vectors[question["name"]]),
                    )
                    latencies.append((time.perf_counter() - started) * 1000)
                    if question["gold"]:
                        scored.append(score_question(question, rows))
                    else:
                        negatives.append(
                            {
                                "name": question["name"],
                                "category": question["category"],
                                "retrieved": len(rows),
                                "top_vector_score": round(
                                    max((r["score"] for r in rows), default=0.0), 4
                                ),
                            }
                        )
                n = len(scored)
                report_configs.append(
                    {
                        "config": {
                            "chunking": chunking,
                            "lexical_query_mode": lexical,
                            "max_chunks_per_document": cap,
                        },
                        "label": "v1 baseline"
                        if (chunking, lexical, cap) == CONFIGS[0]
                        else "v2 default"
                        if (chunking, lexical, cap) == CONFIGS[-1]
                        else "ablation",
                        "answerable_questions": n,
                        "evidence_recall_at_3": round(
                            sum(s["evidence_recall_at_3"] for s in scored) / n, 4
                        ),
                        "evidence_recall_at_6": round(
                            sum(s["evidence_recall_at_6"] for s in scored) / n, 4
                        ),
                        "full_evidence_hit_rate_at_6": round(
                            sum(s["full_evidence_at_6"] for s in scored) / n, 4
                        ),
                        "mrr": round(sum(s["reciprocal_rank"] for s in scored) / n, 4),
                        "document_recall_at_6": round(
                            sum(s["document_recall_at_6"] for s in scored) / n, 4
                        ),
                        "retrieval_sql_ms_p50": percentile(latencies, 0.5),
                        "retrieval_sql_ms_p95": percentile(latencies, 0.95),
                        "per_question": scored,
                        "non_answerable_observations": negatives,
                    }
                )
    return {
        "date": datetime.now(UTC).date().isoformat(),
        "evidence_category": "real_embeddings_synthetic_corpus"
        if embeddings == "ollama"
        else "synthetic_vectors_plumbing_only",
        "embedding_model": settings.embedding_model if embeddings == "ollama" else "hashed-bow",
        "corpus": {
            "documents": len(corpus["documents"]),
            "questions": len(corpus["questions"]),
            "answerable": sum(1 for q in corpus["questions"] if q["gold"]),
            "note": corpus["purpose"],
        },
        "query_embedding_ms_p50": percentile(query_ms, 0.5),
        "query_embedding_ms_p95": percentile(query_ms, 0.95),
        "indexing": indexing,
        "configs": report_configs,
        "limitations": [
            "Small synthetic corpus written for this benchmark; not representative of a "
            "large or real document base.",
            "Retrieval metrics only: they do not measure answer correctness or abstention.",
            "Single run on one machine; latencies are indicative, not a throughput claim.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", choices=["ollama", "synthetic"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.embeddings)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            [
                {
                    k: c[k]
                    for k in (
                        "label",
                        "config",
                        "evidence_recall_at_6",
                        "full_evidence_hit_rate_at_6",
                        "mrr",
                    )
                }
                for c in report["configs"]
            ],
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
