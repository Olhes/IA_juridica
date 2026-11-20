"""Database initialization for IA Juridica.

The selected adapter (SurrealDB by default, PostgreSQL as rollback) owns the
application tables. Redis is initialized alongside it. Public function names are
kept unchanged because main.py imports them directly.
"""

import asyncio
from typing import Any, Dict

from .adapter import database_adapter, uses_surreal
from .redis_adapter import redis_adapter

# Backward-compatible module attribute: it now points at the selected adapter.
postgres_adapter = database_adapter


async def initialize_database():
    """Initialize the selected database adapter and Redis."""
    try:
        print("Initializing database system...")
        await database_adapter.initialize()
        await redis_adapter.initialize()
        print("Redis connected")

        db_health = await database_adapter.health_check()
        redis_health = await redis_adapter.health_check()
        label = "SurrealDB" if uses_surreal() else "PostgreSQL"
        print("Database initialized:")
        print(f"   {label}: {db_health['status']} ({db_health.get('version', 'unknown')})")
        print(f"   Redis: {redis_health['status']} (v{redis_health.get('version', 'unknown')})")
        return True
    except Exception as error:
        print(f"Error initializing database: {error}")
        raise


async def close_database():
    """Close the selected database adapter and Redis."""
    try:
        print("Closing database connections...")
        await database_adapter.close()
        await redis_adapter.close()
        print("Database connections closed")
    except Exception as error:
        print(f"Error closing database: {error}")


async def health_check() -> Dict[str, Any]:
    """Report health of the selected database and Redis."""
    try:
        db_health = await database_adapter.health_check()
        redis_health = await redis_adapter.health_check()

        overall_status = "healthy" if (
            db_health["status"] == "healthy" and redis_health["status"] == "healthy"
        ) else "partial" if redis_health["status"] == "healthy" else "unhealthy"

        result = {
            "overall_status": overall_status,
            # Legacy key retained for compatibility with existing consumers.
            "postgresql": db_health,
            "surrealdb": db_health if uses_surreal() else {"status": "unavailable"},
            "redis": redis_health,
            "timestamp": db_health["timestamp"],
        }
        return result
    except Exception as error:
        return {
            "overall_status": "unhealthy",
            "error": str(error),
            "timestamp": _now(),
        }


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def get_postgres_adapter():
    """Return the selected adapter when connected (name kept for compatibility)."""
    if database_adapter.is_connected():
        return database_adapter
    return None


__all__ = [
    "initialize_database",
    "close_database",
    "health_check",
    "postgres_adapter",
    "database_adapter",
    "redis_adapter",
    "get_postgres_adapter",
]
