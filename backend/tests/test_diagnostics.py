"""RAG diagnostics: read back existing audit numbers, never text, never across workspaces."""

from uuid import uuid4

from test_pipeline import api as api  # shared real PostgreSQL fixture

from app.diagnostics import sanitize_turn


def test_sanitizer_keeps_numbers_and_labels_but_drops_text():
    raw = {
        "mode": "ASK",
        "model": "qwen3:4b",
        "duration_ms": 1200,
        "retrieval_ms": 90,
        "input_tokens": 812,
        "citations": [1, 2, "x"],
        "source_chunk_ids": [7, 9],
        "answer_lead": "Finanzas",  # document text: must not leave
        "prompt": "secreto",  # unknown key: must not leave
        "abstention_reason": "x" * 500,  # not a short label
        "assessment": {"selection": "sufficient", "quotes": 2, "quoted_text": "frase"},
        "retrieval": {
            "strategy": "hybrid_rrf_v2",
            "vector_candidates": 24,
            "embedding_ms": 41,
            "selected": [{"chunk_id": 7, "score": 0.61, "rrf_score": 0.03, "excerpt": "texto"}],
        },
        "provider_metrics_by_call": [
            {"eval_count": 40, "total_duration": 9_000_000, "done_reason": "stop", "message": "x"}
        ],
        "tools": [{"name": "get_tickets", "arguments": {"limit": 5}, "result_count": 3}],
    }
    turn = sanitize_turn(raw)
    text = repr(turn)
    for leaked in ("Finanzas", "secreto", "frase", "texto", "'message'", "arguments"):
        assert leaked not in text
    assert turn["model"] == "qwen3:4b" and turn["duration_ms"] == 1200
    assert turn["abstention_reason"] is None
    assert turn["citations"] == [1, 2] and turn["source_chunk_ids"] == [7, 9]
    assert turn["assessment"] == {"selection": "sufficient", "quotes": 2}
    assert turn["retrieval"]["selected"] == [
        {
            "chunk_id": 7,
            "score": 0.61,
            "rrf_score": 0.03,
            "vector_rank": None,
            "lexical_rank": None,
            "lexical_score": None,
        }
    ]
    assert turn["model_calls_detail"] == [
        {"eval_count": 40, "total_duration": 9_000_000, "done_reason": "stop"}
    ]
    assert turn["tools"] == [{"name": "get_tickets", "result_count": 3, "duration_ms": None}]


def test_sanitizer_tolerates_missing_or_malformed_details():
    turn = sanitize_turn({"retrieval": "nope", "assessment": [], "tools": "x"})
    assert turn["retrieval"]["selected"] == [] and turn["assessment"] == {}
    assert sanitize_turn(None)["model_calls_detail"] == []


def test_conversation_diagnostics_are_scoped_and_ordered(api):
    api.post(
        "/api/documents",
        files={"file": ("politica.txt", "La política exige aprobación humana.".encode())},
    )
    first = api.post("/api/chat", json={"message": "¿Qué exige la política?"}).json()
    conversation = first["conversation_id"]
    api.post("/api/chat", json={"message": "¿Y quién?", "conversation_id": conversation})
    turns = api.get(f"/api/conversations/{conversation}/diagnostics").json()
    assert len(turns) == 2
    assert turns[0]["source_chunk_ids"] == [s["chunk_id"] for s in first["sources"]]
    assert turns[0]["retrieval"]["strategy"] == "hybrid_rrf_v2"
    assert turns[0]["retrieval"]["selected"][0]["chunk_id"] == first["sources"][0]["chunk_id"]
    assert turns[0]["created_at"] <= turns[1]["created_at"]
    assert "aprobación humana" not in str(turns)
    assert api.get(f"/api/conversations/{uuid4()}/diagnostics").status_code == 404
    other = api.post("/api/auth/workspaces", json={"name": "Other"}).json()["id"]
    api.post("/api/auth/workspace", json={"workspace_id": other})
    assert api.get(f"/api/conversations/{conversation}/diagnostics").status_code == 404
