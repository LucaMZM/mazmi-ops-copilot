"""Paired retrieval benchmark on real PostgreSQL; fixture writes always roll back.

DATABASE_URL=... python -m app.evaluate [--live]
Offline vectors deliberately collapse similar procedures: this is a deterministic
regression benchmark, not an estimate of OpenAI semantic quality.
"""

import argparse
import json
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from . import rag
from .config import settings


def offline_embeddings(**kwargs):
    vocabulary = ("vacacion", "gasto", "producción", "código", "auditoría")
    data = []
    for i, text in enumerate(kwargs["input"]):
        values = [float(word in text.lower()) for word in vocabulary]
        values.append(float(not any(values)))
        # Unknown queries/documents are not zero vectors (undefined cosine).
        data.append(SimpleNamespace(index=i, embedding=values + [0.0] * (1536 - len(values))))
    return SimpleNamespace(data=data)


def baseline(conn, workspace, query):
    """Frozen pre-hybrid SQL and threshold, with an ID tie-break for reproducibility."""
    vector = Vector(rag.embed_query(query))
    rows = conn.execute(
        """SELECT c.id,d.filename,c.content,1-(c.embedding <=> %s) AS score
           FROM document_chunks c JOIN documents d ON d.id=c.document_id
           WHERE c.workspace_id=%s AND d.status='ready' AND d.embedding_collection=%s AND c.embedding_collection=d.embedding_collection
           ORDER BY c.embedding <=> %s,c.id LIMIT 6""",
        (vector, workspace, rag.embedding_collection(), vector),
    ).fetchall()
    return [
        {"chunk_id": r[0], "filename": r[1], "content": r[2], "score": r[3]}
        for r in rows
        if r[3] >= settings.retrieval_min_score
    ]


def evaluate(live=False):
    if live and settings.embedding_provider == "openai" and not settings.openai_api_key:
        raise RuntimeError("--live requiere OPENAI_API_KEY")
    dataset = json.loads((Path(__file__).resolve().parents[1] / "evals/cases.json").read_text())
    original = rag.client
    original_provider, original_dimensions = (
        settings.embedding_provider,
        settings.embedding_dimensions,
    )
    if not live:
        settings.embedding_provider, settings.embedding_dimensions = "openai", 1536
        rag.client = SimpleNamespace(embeddings=SimpleNamespace(create=offline_embeddings))
    results = {"before_vector": [], "after_hybrid": []}
    try:
        with psycopg.connect(settings.database_url) as conn:
            register_vector(conn)
            try:
                workspace = conn.execute(
                    "INSERT INTO workspaces(name,slug) VALUES (%s,%s) RETURNING id",
                    ("Evaluation", str(uuid4())),
                ).fetchone()[0]
                for doc in dataset["documents"]:
                    document = conn.execute(
                        "INSERT INTO documents(workspace_id,filename,status,embedding_model,embedding_collection,embedding_dimensions) VALUES (%s,%s,'ready',%s,%s,%s) RETURNING id",
                        (
                            workspace,
                            doc["filename"],
                            settings.embedding_model,
                            rag.embedding_collection(),
                            settings.vector_dimensions,
                        ),
                    ).fetchone()[0]
                    chunks = rag.split_text(doc["text"])
                    for index, (chunk, vector) in enumerate(
                        zip(chunks, rag.embed_texts(chunks), strict=True)
                    ):
                        conn.execute(
                            "INSERT INTO document_chunks(workspace_id,document_id,chunk_index,content,embedding) VALUES (%s,%s,%s,%s,%s)",
                            (workspace, document, index, chunk, Vector(vector)),
                        )
                for case in dataset["cases"]:
                    for name, search in (
                        ("before_vector", baseline),
                        ("after_hybrid", rag.retrieve),
                    ):
                        started = time.perf_counter()
                        sources = search(conn, str(workspace), case["question"])
                        elapsed = (time.perf_counter() - started) * 1000
                        ranking = [s["filename"] for s in sources]
                        expected = case["expected_source"]
                        rank = ranking.index(expected) + 1 if expected in ranking else None
                        results[name].append(
                            {
                                "question": case["question"],
                                "kind": case.get("kind", "known_answer"),
                                "expected_source": expected,
                                "sources": ranking,
                                "rank": rank,
                                "fact_in_context": bool(expected)
                                and any(
                                    case["expected_fact"].casefold() in s["content"].casefold()
                                    for s in sources
                                ),
                                "no_evidence": not sources,
                                "retrieval_ms": round(elapsed, 3),
                            }
                        )
            finally:
                conn.rollback()
    finally:
        rag.client = original
        settings.embedding_provider, settings.embedding_dimensions = (
            original_provider,
            original_dimensions,
        )
    report = {
        "mode": "live-embeddings" if live else "deterministic-embeddings",
        "k": 6,
        "documents": len(dataset["documents"]),
        "cases": len(dataset["cases"]),
    }
    for name, rows in results.items():
        known = [r for r in rows if r["expected_source"]]
        unknown = [r for r in rows if not r["expected_source"]]
        report[name] = {
            "recall_at_6": sum(r["rank"] is not None for r in known) / len(known),
            "mrr": sum(1 / r["rank"] if r["rank"] else 0 for r in known) / len(known),
            "source_top1_accuracy": sum(r["rank"] == 1 for r in known) / len(known),
            "source_precision": sum((1 / len(r["sources"])) if r["rank"] else 0 for r in known)
            / len(known),
            "unanswerable_no_evidence_rate": sum(r["no_evidence"] for r in unknown) / len(unknown),
            "answerable_false_abstention_rate": sum(r["no_evidence"] for r in known) / len(known),
            "mean_retrieval_ms": round(sum(r["retrieval_ms"] for r in rows) / len(rows), 3),
            "cases": rows,
        }
    report["limitations"] = (
        "Small synthetic benchmark, one expected source per answerable query. "
        "No-evidence rate is a retrieval abstention proxy, not semantic answer correctness. "
        "Latency is a single local run including embeddings; no production SLA. "
        "Injection resistance is tested separately with adversarial provider doubles."
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.live), ensure_ascii=False, indent=2))
