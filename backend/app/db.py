"""PostgreSQL access through a small bounded pool.

``get_conn()`` keeps its historical contract: one transaction per ``with`` block,
committed on success and rolled back on any exception. The pool adds connection
reuse, a hard upper bound on concurrent database sessions (back-pressure instead of
exhausting PostgreSQL) and server-side safety timeouts so an abandoned request can
never keep row locks indefinitely.
"""

from contextlib import contextmanager
from threading import Lock

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool, PoolTimeout

from .config import settings


class DatabaseBusy(RuntimeError):
    """Every pooled connection stayed busy for longer than the configured wait."""


_lock = Lock()
_pool: ConnectionPool | None = None
_pool_key: tuple | None = None


def _configure(conn: psycopg.Connection) -> None:
    register_vector(conn)
    # Session-level guards. set_config(..., false) persists for the pooled session.
    conn.execute(
        "SELECT set_config('statement_timeout', %s, false),"
        " set_config('idle_in_transaction_session_timeout', %s, false)",
        (f"{settings.db_statement_timeout_ms}ms", f"{settings.db_idle_transaction_timeout_ms}ms"),
    )
    conn.commit()


def _key() -> tuple:
    return (
        settings.database_url,
        settings.db_pool_max,
        settings.db_statement_timeout_ms,
        settings.db_idle_transaction_timeout_ms,
    )


def pool() -> ConnectionPool:
    """Return the process pool, recreating it if the effective configuration changed.

    Tests point ``settings.database_url`` at a fresh isolated schema per test; the key
    check closes the previous pool so connections never cross schemas.
    """
    global _pool, _pool_key
    with _lock:
        key = _key()
        if _pool is None or _pool_key != key:
            previous = _pool
            _pool = ConnectionPool(
                settings.database_url,
                min_size=1,
                max_size=settings.db_pool_max,
                kwargs={"connect_timeout": 5},
                configure=_configure,
                check=ConnectionPool.check_connection,
                timeout=settings.db_pool_timeout_seconds,
                name="mazmi",
                open=True,
            )
            _pool_key = key
            if previous is not None:
                previous.close(timeout=5)
        return _pool


def close_pool() -> None:
    global _pool, _pool_key
    with _lock:
        if _pool is not None:
            _pool.close(timeout=5)
        _pool, _pool_key = None, None


@contextmanager
def get_conn():
    try:
        context = pool().connection()
        conn = context.__enter__()
    except PoolTimeout as exc:
        raise DatabaseBusy("Base de datos ocupada; inténtalo de nuevo en unos segundos") from exc
    try:
        yield conn
    except BaseException as exc:
        context.__exit__(type(exc), exc, exc.__traceback__)
        raise
    else:
        context.__exit__(None, None, None)
