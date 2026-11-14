"""One-time import of a reviewed SAT SQLite snapshot into shared PostgreSQL."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / ".env")

from ingestion.sat_graph.postgres import PostgresSATGraphStore
from database.postgres_connection import connect_postgres
from retrieval.voyage import VoyageProvider

TABLES = ("sat_nodes", "sat_edges", "sat_documents", "sat_reviews", "sat_parses")


def import_snapshot(store, path):
    """Copy all revisions atomically. Never replace an existing shared corpus."""
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        source.execute("BEGIN")
        if source.execute("SELECT version FROM sat_meta").fetchall() != [(1,)]:
            raise ValueError("Esquema SQLite SAT no soportado")
        if source.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("Snapshot SQLite SAT dañado")
        if source.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Snapshot SQLite SAT tiene referencias inválidas")
        kind = "CandidateParse" if store.candidates else "DocumentaryRevision"
        if not source.execute("SELECT 1 FROM sat_nodes WHERE kind=? LIMIT 1", (kind,)).fetchone():
            raise ValueError("El snapshot no contiene la clase de documentos esperada")
        store._initialize_schema()
        with store._transaction() as target:
            if any(target.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in TABLES):
                raise ValueError("El corpus PostgreSQL ya contiene datos; no se sobrescribió")
            counts = {}
            for table in TABLES:
                cursor = source.execute(f"SELECT * FROM {table}")
                placeholders = ",".join(["%s"] * len(cursor.description))
                with target.connection.cursor() as writer:
                    while rows := cursor.fetchmany(250):
                        writer.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
                counts[table] = target.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            return counts


def import_voyage(path):
    """Preserve cache and already-reserved provider quota without calling Voyage."""
    tables = ("voyage_cache", "voyage_usage", "voyage_rate", "voyage_cooldown")
    VoyageProvider("migration-no-network", connect=connect_postgres)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        source.execute("BEGIN")
        if source.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("Caché SQLite Voyage dañada")
        with connect_postgres() as target:
            target.execute("SELECT pg_advisory_xact_lock(6591427708186)")
            target.execute("SET LOCAL search_path TO sat_voyage, pg_catalog")
            if any(target.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in tables):
                raise ValueError("La caché PostgreSQL ya contiene datos; no se sobrescribió")
            counts = {}
            for table in tables:
                cursor = source.execute(f"SELECT * FROM {table}")
                placeholders = ",".join(["%s"] * len(cursor.description))
                with target.cursor() as writer:
                    while rows := cursor.fetchmany(250):
                        writer.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
                counts[table] = target.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-sqlite", type=Path, required=True)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--candidates", action="store_true", help="Migrar candidatos al esquema separado")
    target.add_argument("--voyage-cache", action="store_true", help="Migrar caché y cuotas de Voyage")
    args = parser.parse_args()
    counts = (import_voyage(args.from_sqlite) if args.voyage_cache else
              import_snapshot(PostgresSATGraphStore(candidates=args.candidates), args.from_sqlite))
    print(json.dumps(counts, indent=2))
