"""Read-only RAG diagnostics for the turns of one conversation.

The numbers already exist: every answered turn writes a ``chat.completed`` audit event with
retrieval ranks, timings, model calls and the evidence-check trace. This module only reads
those events back for a conversation of the session workspace, and passes them through an
allow-list so no text can leave: no prompts, no document content, no answer lead, no
arguments. Nothing here touches retrieval, abstention or approval behaviour.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from .auth import CurrentUser
from .db import get_conn

router = APIRouter(prefix="/api/conversations", tags=["diagnostics"])

TURN_LIMIT = 50

_NUMBER = (int, float)
_TURN_NUMBERS = (
    "duration_ms",
    "retrieval_ms",
    "retrieved_chunks",
    "model_calls",
    "input_tokens",
    "output_tokens",
)
_TURN_LABELS = (
    "mode",
    "model",
    "generation_provider",
    "evidence_policy",
    "abstention_reason",
    "answer_lead_withheld",
)
_RETRIEVAL_NUMBERS = (
    "duration_ms",
    "embedding_ms",
    "vector_candidates",
    "lexical_candidates",
    "unique_candidates",
)
_RETRIEVAL_LABELS = ("strategy", "lexical_query_mode", "embedding_collection", "abstention_reason")
_SELECTED_FIELDS = (
    "chunk_id",
    "score",
    "rrf_score",
    "vector_rank",
    "lexical_rank",
    "lexical_score",
)
_ASSESSMENT_FIELDS = (
    "selection",
    "quotes",
    "attempts",
    "quotes_snapped",
    "quotes_verified",
    "numeric_conflict",
    "answer_echoes_question",
    "version_retry",
    "answer_check",
)
_CALL_FIELDS = (
    "prompt_eval_count",
    "eval_count",
    "total_duration",
    "load_duration",
    "prompt_eval_duration",
    "eval_duration",
    "done_reason",
)


def _label(value) -> str | None:
    # Short identifiers only (enums, model names); anything longer is not a label.
    return value if isinstance(value, str) and len(value) <= 120 else None


def _number(value):
    return value if isinstance(value, _NUMBER) and not isinstance(value, bool) else None


def _scalar(value):
    if isinstance(value, bool):
        return value
    return _number(value) if _number(value) is not None else _label(value)


def _ids(value) -> list[int]:
    if not isinstance(value, list):
        return []
    return [i for i in value if isinstance(i, int) and not isinstance(i, bool)]


def sanitize_turn(details: dict) -> dict:
    """Keep only numbers, flags and short labels from a ``chat.completed`` record."""
    details = details if isinstance(details, dict) else {}
    turn: dict = {k: _number(details.get(k)) for k in _TURN_NUMBERS}
    turn.update({k: _label(details.get(k)) for k in _TURN_LABELS})
    turn["citations"] = _ids(details.get("citations"))
    turn["source_chunk_ids"] = _ids(details.get("source_chunk_ids"))
    turn["superseded_ignored"] = _ids(details.get("superseded_ignored"))
    turn["model_assessment_performed"] = details.get("model_assessment_performed") is True
    retrieval = details.get("retrieval") if isinstance(details.get("retrieval"), dict) else {}
    turn["retrieval"] = {
        **{k: _number(retrieval.get(k)) for k in _RETRIEVAL_NUMBERS},
        **{k: _label(retrieval.get(k)) for k in _RETRIEVAL_LABELS},
        "selected": [
            {k: _number(item.get(k)) for k in _SELECTED_FIELDS}
            for item in retrieval.get("selected", [])
            if isinstance(item, dict)
        ][:20],
    }
    assessment = details.get("assessment") if isinstance(details.get("assessment"), dict) else {}
    turn["assessment"] = {k: _scalar(assessment[k]) for k in _ASSESSMENT_FIELDS if k in assessment}
    calls = details.get("provider_metrics_by_call")
    if not isinstance(calls, list):
        single = details.get("provider_metrics")
        calls = [single] if isinstance(single, dict) else []
    turn["model_calls_detail"] = [
        {k: _scalar(call.get(k)) for k in _CALL_FIELDS if k in call}
        for call in calls
        if isinstance(call, dict)
    ][:8]
    turn["tools"] = [
        {
            "name": _label(tool.get("name")),
            "result_count": _number(tool.get("result_count")),
            "duration_ms": _number(tool.get("duration_ms")),
        }
        for tool in details.get("tools", [])
        if isinstance(tool, dict)
    ][:4]
    return turn


@router.get("/{conversation_id}/diagnostics")
def conversation_diagnostics(conversation_id: UUID, user: CurrentUser):
    """Diagnostics of the answered turns of one conversation, oldest first."""
    with get_conn() as conn:
        if not conn.execute(
            "SELECT 1 FROM conversations WHERE id=%s AND workspace_id=%s",
            (conversation_id, user.workspace_id),
        ).fetchone():
            raise HTTPException(404, "Conversación no encontrada")
        rows = conn.execute(
            "SELECT details,duration_ms,created_at FROM audit_events"
            " WHERE workspace_id=%s AND conversation_id=%s AND event_type='chat.completed'"
            " ORDER BY created_at, id LIMIT %s",
            (user.workspace_id, conversation_id, TURN_LIMIT),
        ).fetchall()
    return [
        {**sanitize_turn(details), "recorded_ms": duration, "created_at": created}
        for details, duration, created in rows
    ]
