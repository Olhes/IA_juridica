"""Select the same SAT store for chat, review and backend ingestion."""
from config.settings import settings


def runtime_sat_store():
    backend = str(getattr(settings, "DATABASE_BACKEND", "surrealdb") or "").strip().lower()
    if backend.startswith("surreal"):
        from .surreal import SurrealSATGraphStore
        return SurrealSATGraphStore()
    from .postgres import PostgresSATGraphStore
    return PostgresSATGraphStore()
