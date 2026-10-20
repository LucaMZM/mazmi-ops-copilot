from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector

from .config import settings


@contextmanager
def get_conn():
    conn = psycopg.connect(settings.database_url, connect_timeout=5)
    try:
        register_vector(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_demo_workspace_id(conn) -> str:
    row = conn.execute("SELECT id FROM workspaces WHERE slug = %s", ("mazmi-demo",)).fetchone()
    if not row:
        raise RuntimeError("Demo workspace is missing")
    return str(row[0])
