"""Adapter selection for the configured database backend.

SurrealDB is the default backend; PostgreSQL stays selectable as a rollback
target. ``get_database_adapter`` returns one shared instance per backend: the
SurrealDB adapter owns live websocket connections, so building a new one per
request leaked a pair of sockets on every call and eventually poisoned the
asyncio loop on shutdown.
"""

from config.settings import settings
from database.postgres_adapter_final import DatabaseUnavailableError, PostgreSQLAdapter
from database.surreal_adapter import SurrealAdapter

_ORIGINAL_POSTGRES_ADAPTER = PostgreSQLAdapter
_default_adapters: dict = {}


def uses_surreal() -> bool:
    backend = str(getattr(settings, "DATABASE_BACKEND", "surrealdb") or "")
    return backend.lower().startswith("surreal")


def get_database_adapter(postgres_factory=None):
    """Return the shared adapter for the configured backend.

    ``postgres_factory`` is an optional hook used by callers that keep a
    module-level ``PostgreSQLAdapter`` symbol (tests replace it with fakes).
    A patched factory always yields a fresh instance; the unpatched class
    resolves to the shared adapter so connections are reused, not leaked.
    """
    if postgres_factory is not None and postgres_factory is not _ORIGINAL_POSTGRES_ADAPTER:
        return postgres_factory()

    backend = "surrealdb" if uses_surreal() else "postgresql"
    adapter = _default_adapters.get(backend)
    if adapter is None:
        adapter = SurrealAdapter() if backend == "surrealdb" else PostgreSQLAdapter()
        _default_adapters[backend] = adapter
    return adapter


database_adapter = get_database_adapter()

__all__ = [
    "get_database_adapter",
    "database_adapter",
    "uses_surreal",
    "SurrealAdapter",
    "PostgreSQLAdapter",
    "DatabaseUnavailableError",
]
