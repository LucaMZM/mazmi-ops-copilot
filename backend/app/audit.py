"""Append-only audit events. Always written inside the caller's transaction."""

import json


def audit(conn, user, event: str, details: dict, conversation_id=None, duration_ms=None):
    conn.execute(
        "INSERT INTO audit_events(workspace_id,user_id,conversation_id,event_type,actor,details,"
        "duration_ms) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)",
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
