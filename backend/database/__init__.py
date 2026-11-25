"""Database exports for IA Juridica."""

from .adapter import SurrealAdapter, database_adapter, get_database_adapter
from .errors import DatabaseUnavailableError
from .redis_adapter import redis_adapter

__all__ = [
    "DatabaseUnavailableError",
    "SurrealAdapter",
    "database_adapter",
    "get_database_adapter",
    "redis_adapter",
]
