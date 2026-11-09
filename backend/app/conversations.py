"""Conversation history, rename and archive. Always scoped to the session workspace.

Archiving is a soft delete: the conversation leaves the sidebar but its messages,
proposals and audit references are preserved for traceability.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from .audit import audit
from .auth import CurrentUser
from .db import get_conn
from .schemas import StrictModel

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = Field(default=None, strict=True)


@router.get("")
def conversations(user: CurrentUser, archived: bool = Query(False)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id,title,created_at,updated_at,archived_at FROM conversations"
            " WHERE workspace_id=%s AND (archived_at IS NOT NULL)=%s"
            " ORDER BY updated_at DESC, id LIMIT 50",
            (user.workspace_id, archived),
        ).fetchall()
    return [
        {
            "id": str(r[0]),
            "title": r[1],
            "created_at": r[2],
            "updated_at": r[3],
            "archived": r[4] is not None,
        }
        for r in rows
    ]


@router.get("/{conversation_id}")
def conversation(conversation_id: UUID, user: CurrentUser):
    with get_conn() as conn:
        found = conn.execute(
            "SELECT title,archived_at FROM conversations WHERE id=%s AND workspace_id=%s",
            (conversation_id, user.workspace_id),
        ).fetchone()
        if not found:
            raise HTTPException(404, "Conversación no encontrada")
        rows = conn.execute(
            "SELECT role,content,sources,created_at FROM messages WHERE conversation_id=%s"
            " ORDER BY id",
            (conversation_id,),
        ).fetchall()
        actions = conn.execute(
            "SELECT id,action_name,payload FROM pending_actions WHERE conversation_id=%s"
            " AND workspace_id=%s AND status='PENDING' AND requested_by=%s ORDER BY created_at",
            (conversation_id, user.workspace_id, user.user_id),
        ).fetchall()
    return {
        "title": found[0],
        "archived": found[1] is not None,
        "messages": [
            {"role": r[0], "content": r[1], "sources": r[2], "created_at": r[3]} for r in rows
        ],
        "pending_actions": [{"id": str(r[0]), "name": r[1], "payload": r[2]} for r in actions],
    }


@router.patch("/{conversation_id}")
def update_conversation(conversation_id: UUID, payload: ConversationUpdate, user: CurrentUser):
    if payload.title is None and payload.archived is None:
        raise HTTPException(400, "Indica un título o el estado de archivo")
    with get_conn() as conn:
        row = conn.execute(
            "UPDATE conversations SET"
            " title=coalesce(%s::text,title),"
            " archived_at=CASE WHEN %s::boolean IS NULL THEN archived_at"
            "                  WHEN %s::boolean THEN coalesce(archived_at, now()) ELSE NULL END"
            " WHERE id=%s AND workspace_id=%s RETURNING id,title,archived_at",
            (
                payload.title,
                payload.archived,
                payload.archived,
                conversation_id,
                user.workspace_id,
            ),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Conversación no encontrada")
        changes = {}
        if payload.title is not None:
            changes["renamed"] = True
        if payload.archived is not None:
            changes["archived"] = payload.archived
        audit(conn, user, "conversation.updated", changes, conversation_id)
    return {"id": str(row[0]), "title": row[1], "archived": row[2] is not None}
