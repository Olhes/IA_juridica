"""Database exports for IA Juridica."""

from .adapter import database_adapter, get_database_adapter, uses_surreal
from .errors import DatabaseUnavailableError
from .redis_adapter import redis_adapter

# Backward-compatible module attribute pointing at the selected adapter.
postgres_adapter = database_adapter

__all__ = [
    "DatabaseUnavailableError",
    "database_adapter",
    "get_database_adapter",
    "postgres_adapter",
    "redis_adapter",
    "uses_surreal",
]
