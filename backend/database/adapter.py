"""Shared database adapter factory for SurrealDB.

``get_database_adapter`` returns one shared :class:`SurrealAdapter` instance so
live WebSocket connections are reused across requests instead of leaking a pair
of sockets on every call.
"""

from database.errors import DatabaseUnavailableError
from database.surreal_adapter import SurrealAdapter

_ORIGINAL_ADAPTER = SurrealAdapter
_default_adapter: SurrealAdapter | None = None


def get_database_adapter(adapter_factory=None):
    """Return the shared SurrealDB adapter instance.

    ``adapter_factory`` is an optional hook used by callers that expose a
    module-level ``SurrealAdapter`` symbol so tests can inject fakes without
    replacing the shared singleton.
    """
    if adapter_factory is not None and adapter_factory is not _ORIGINAL_ADAPTER:
        return adapter_factory()

    global _default_adapter
    if _default_adapter is None:
        _default_adapter = SurrealAdapter()
    return _default_adapter


database_adapter = get_database_adapter()

__all__ = [
    "get_database_adapter",
    "database_adapter",
    "SurrealAdapter",
    "DatabaseUnavailableError",
]
