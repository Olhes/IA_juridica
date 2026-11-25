"""Select the shared SurrealDB SAT store for chat, review, and ingestion."""


def runtime_sat_store():
    from .surreal import SurrealSATGraphStore

    return SurrealSATGraphStore()
