"""Small ordered, transactional SQL migration runner, safe on existing volumes."""

from pathlib import Path

import psycopg

from .config import settings


def migrate():
    folder = Path(__file__).resolve().parents[2] / "database" / "init"
    if not folder.exists():
        folder = Path("/app/migrations")
    with psycopg.connect(settings.database_url, connect_timeout=10) as conn:
        # Fail and roll back rather than waiting indefinitely on a busy existing DB.
        conn.execute("SET LOCAL lock_timeout = '5s'")
        conn.execute("SET LOCAL statement_timeout = '120s'")
        conn.execute("SELECT pg_advisory_xact_lock(7348221)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        for path in sorted(folder.glob("*.sql")):
            if not conn.execute(
                "SELECT 1 FROM schema_migrations WHERE name=%s", (path.name,)
            ).fetchone():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations(name) VALUES (%s)", (path.name,))


if __name__ == "__main__":
    migrate()
