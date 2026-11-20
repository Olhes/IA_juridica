"""Initialize the versioned SAT corpus on an empty SurrealDB database."""

from __future__ import annotations

import gzip
from pathlib import Path
import sys

from surrealdb.errors import NotFoundError

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.surreal_connection import connect_surreal


SNAPSHOT = Path(__file__).resolve().parents[1] / "docs" / "sat_graph.surql.gz"
# Counts from the PostgreSQL SAT-only dump used to generate this native export.
EXPECTED_ROWS = {
    "sat_chat_revision": 1,
    "sat_documents": 12,
    "sat_edges": 94371,
    "sat_meta": 1,
    "sat_nodes": 39823,
    "sat_parses": 4,
    "sat_reviews": 0,
}
REVISION_QUERY = "SELECT VALUE id FROM sat_nodes WHERE kind = 'DocumentaryRevision' LIMIT 1"


def _has_revisions(connection) -> bool:
    try:
        return bool(connection.query(REVISION_QUERY).execute()[0])
    except NotFoundError:
        return False


def bootstrap(connection, snapshot: Path = SNAPSHOT) -> str:
    if _has_revisions(connection):
        return "present"

    # Recheck after opening the transaction. CREATE makes concurrent imports
    # conflict at commit, and a preexisting partial corpus is left for recovery.
    with connection.timeout(300), connection.begin_transaction() as transaction:
        if _has_revisions(transaction):
            return "present"
        transaction.query("DEFINE TABLE IF NOT EXISTS sat_bootstrap SCHEMALESS").execute()
        claim = transaction.query("SELECT * FROM sat_bootstrap:seed").execute()[0]
        if claim:
            raise RuntimeError("El corpus SAT registrado en SurrealDB perdió sus revisiones; restaura un respaldo.")
        for table in EXPECTED_ROWS:
            try:
                existing = transaction.query(f"SELECT VALUE id FROM {table} LIMIT 1").execute()[0]
            except NotFoundError:
                existing = []
            if existing:
                raise RuntimeError("Existe un corpus SAT parcial; revisa el volumen antes de inicializar.")
        transaction.query("CREATE sat_bootstrap:seed SET format = 'sat_graph.surql.gz'").execute()

        # The native export emits one DEFINE or INSERT per line. Replay each
        # statement in the same transaction to limit the size of each RPC.
        with gzip.open(snapshot, "rt", encoding="utf-8") as statements:
            for line in statements:
                statement = line.strip()
                if statement and not statement.startswith("--") and statement != "OPTION IMPORT;":
                    transaction.query(statement).execute()
        for table, expected in EXPECTED_ROWS.items():
            rows = transaction.query(f"SELECT VALUE count() FROM {table} GROUP ALL").execute()[0]
            if (rows[0] if rows else 0) != expected:
                raise RuntimeError(f"El respaldo SAT no coincide con el conteo esperado de {table}.")
        if not _has_revisions(transaction):
            raise RuntimeError("El respaldo SAT no contiene revisiones publicadas.")
    return "restored"


def main():
    with connect_surreal("sat_graph") as connection:
        print(bootstrap(connection))


if __name__ == "__main__":
    main()
