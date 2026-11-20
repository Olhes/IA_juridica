"""Connection helpers for the SurrealDB SAT storage adapter.

This module is intentionally independent of psycopg: it only depends on the
SurrealDB Python SDK and the shared application settings.
"""

import os
import threading
from contextlib import contextmanager
from queue import Empty, Full, Queue

from surrealdb import Surreal

from config.settings import settings


SURREAL_NAMESPACE = "ia_juridica"
SURREAL_DATABASES = (
    "sat_graph",
    "sat_candidates",
    "sat_voyage",
    "auth_schema",
    "conversations_schema",
    "rag_schema",
    "legal_schema",
)


def surreal_url() -> str:
    return getattr(settings, "SURREAL_URL", None) or "ws://127.0.0.1:8010/rpc"


def surreal_credentials() -> tuple[str, str]:
    user = getattr(settings, "SURREAL_USER", None) or "root"
    password = getattr(settings, "SURREAL_PASSWORD", None) or "root"
    return str(user), str(password)


def connect_surreal(database: str | None = None) -> Surreal:
    """Return a fresh connected/authenticated synchronous SurrealDB client."""
    conn = Surreal(surreal_url())
    conn.connect()
    try:
        user, password = surreal_credentials()
        conn.signin({"username": user, "password": password})
        conn.use(SURREAL_NAMESPACE, database or "sat_graph")
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise
    return conn


def close_surreal(conn) -> None:
    """Close a connection if it is still open; never raise during cleanup."""
    if conn is None:
        return
    try:
        if getattr(conn, "is_connected", False):
            conn.close()
    except Exception:
        pass


# SurrealDB WebSocket connections are meant to be long-lived: the official SDK
# docs recommend signing in once and sending many queries on the same socket.
# Opening a fresh connection costs ~50 ms here versus ~13 ms for a reused one.
_POOL_SIZE = max(1, int(os.getenv("SURREAL_POOL_SIZE", "8")))
_pools: dict[str, Queue] = {}
_pools_lock = threading.Lock()


def _pool_for(database: str) -> Queue:
    with _pools_lock:
        pool = _pools.get(database)
        if pool is None:
            pool = Queue(maxsize=_POOL_SIZE)
            _pools[database] = pool
        return pool


@contextmanager
def surreal_session(database: str | None = None):
    """Borrow a long-lived connection from a per-database pool.

    The connection is returned to the pool on success and discarded on error,
    so a broken socket never poisons later operations.
    """
    target = database or "sat_graph"
    pool = _pool_for(target)
    try:
        conn = pool.get_nowait()
    except Empty:
        conn = connect_surreal(target)
    broken = False
    try:
        yield conn
    except Exception:
        broken = True
        raise
    finally:
        if broken:
            close_surreal(conn)
        else:
            try:
                pool.put_nowait(conn)
            except Full:
                close_surreal(conn)


def close_all_surreal() -> None:
    """Drain every pool. Call on application shutdown."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        while True:
            try:
                close_surreal(pool.get_nowait())
            except Empty:
                break
