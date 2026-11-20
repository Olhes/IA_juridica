"""Migrate every PostgreSQL-backed table into SurrealDB.

PostgreSQL is intentionally left untouched: it remains the rollback source.
Run with --apply to write, --verify-only to compare counts/checksums.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from surrealdb import RecordID, Surreal
from surrealdb.errors import NotFoundError

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.settings import settings  # noqa: E402

# schema -> (SurrealDB database, [(table, pk_columns), ...])
TABLES: dict[str, tuple[str, list[tuple[str, tuple[str, ...]]]]] = {
    "sat_graph": (
        "sat_graph",
        [
            ("sat_meta", ()),
            ("sat_nodes", ("id",)),
            ("sat_edges", ("id",)),
            ("sat_documents", ("evidence_id",)),
            ("sat_reviews", ("id",)),
            ("sat_parses", ("id",)),
            ("sat_chat_revision", ("id",)),
        ],
    ),
    "sat_candidates": (
        "sat_candidates",
        [
            ("sat_meta", ()),
            ("sat_nodes", ("id",)),
            ("sat_edges", ("id",)),
            ("sat_documents", ("evidence_id",)),
            ("sat_reviews", ("id",)),
            ("sat_parses", ("id",)),
        ],
    ),
    "sat_voyage": (
        "sat_voyage",
        [
            ("voyage_cache", ("key",)),
            ("voyage_usage", ("day",)),
            ("voyage_rate", ("scope", "model", "started")),
            ("voyage_cooldown", ("scope", "model")),
        ],
    ),
    "auth_schema": (
        "auth_schema",
        [
            ("users", ("id",)),
            ("roles", ("id",)),
            ("permissions", ("id",)),
            ("user_roles", ("id",)),
            ("role_permissions", ("id",)),
            ("user_sessions", ("id",)),
        ],
    ),
    "conversations_schema": (
        "conversations_schema",
        [("conversations", ("id",)), ("messages", ("id",))],
    ),
    "rag_schema": (
        "rag_schema",
        [("processed_documents", ("id",)), ("document_chunks", ("id",))],
    ),
    "legal_schema": (
        "legal_schema",
        [("legal_entities", ("id",)), ("legal_precedents", ("id",))],
    ),
}


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _pk_string(values: tuple[Any, ...]) -> str:
    parts = [_plain(v) for v in values]
    if len(parts) == 1:
        return str(parts[0])
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def _canonical(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _pg_connect() -> psycopg.Connection:
    url = settings.DATABASE_URL or ""
    if url:
        return psycopg.connect(
            url.replace("postgresql+psycopg://", "postgresql://", 1), connect_timeout=10
        )
    return psycopg.connect(
        host=settings.DATABASE_HOST,
        port=settings.DATABASE_PORT,
        dbname=settings.DATABASE_NAME,
        user=settings.DATABASE_USER,
        password=settings.DATABASE_PASSWORD,
        connect_timeout=10,
    )


def _surreal_connect(database: str) -> Surreal:
    url = getattr(settings, "SURREAL_URL", "ws://127.0.0.1:8010/rpc")
    user = getattr(settings, "SURREAL_USER", "root")
    password = getattr(settings, "SURREAL_PASSWORD", "root")
    namespace = getattr(settings, "SURREAL_NAMESPACE", "ia_juridica")
    conn = Surreal(url)
    conn.connect()
    conn.signin({"username": user, "password": password})
    conn.use(namespace, database)
    return conn


def _fetch_pg(cur: psycopg.Cursor, schema: str, table: str, pk: tuple[str, ...]) -> list[dict[str, Any]]:
    cur.execute(f'SELECT * FROM "{schema}"."{table}"')
    columns = [d.name for d in cur.description or []]
    rows: list[dict[str, Any]] = []
    for raw in cur.fetchall():
        row = {col: _plain(value) for col, value in zip(columns, raw)}
        row["__pk"] = _pk_string(tuple(row[c] for c in pk)) if pk else "singleton"
        rows.append(row)
    rows.sort(key=lambda r: r["__pk"])
    return rows


def _to_surreal_rows(table: str, rows: list[dict[str, Any]], pk: tuple[str, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        pk_value: Any = row["__pk"] if pk else "singleton"
        if len(pk) == 1:
            record_id = RecordID(table, pk_value)
        elif pk:
            record_id = RecordID(table, [row[c] for c in pk])
        else:
            record_id = RecordID(table, "singleton")
        payload["id"] = record_id
        if table in {"sat_nodes", "sat_edges"} and pk == ("id",):
            payload["nid"] = row["id"]
        if table == "sat_nodes":
            # Derived, indexable copies of JSON payload fields. They are not
            # part of the original PostgreSQL columns and are ignored by the
            # checksum comparison below.
            try:
                body = json.loads(row["payload"])
            except (TypeError, ValueError):
                body = {}
            if isinstance(body, dict):
                derived = {
                    "work_id": body.get("work_id"),
                    "resource_id": body.get("resource_id")
                    or (body.get("id") if row.get("kind") == "Resource" else None),
                    "payload_kind": body.get("kind"),
                    "provenance_state": body.get("provenance_state"),
                }
                for key, value in derived.items():
                    if value is not None:
                        payload[key] = value
        # Keep the original JSON text columns as strings: the store does json.loads().
        out.append(payload)
    return out


def _surreal_rows(conn: Surreal, table: str) -> list[dict[str, Any]]:
    try:
        result = conn.query(f"SELECT * FROM {table}").execute()
    except NotFoundError:
        return []
    return result[0] if result else []


def _strip_none(value: Any) -> Any:
    """SurrealDB NONE omits the field; SQL NULL reads back as Python None."""
    if isinstance(value, dict):
        return {k: _strip_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_none(v) for v in value]
    return value


def _checksum(rows: list[dict[str, Any]]) -> str:
    # SurrealDB encodes the primary key as a RecordID and adds `nid` on graph
    # tables, so both are excluded from the comparable payload.
    ignored = {"id", "nid", "work_id", "resource_id", "payload_kind", "provenance_state"}
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda r: str(r.get("__pk", r.get("id")))):
        comparable = _strip_none({k: v for k, v in row.items() if k not in ignored})
        digest.update(_canonical(comparable).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write data into SurrealDB")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--verify-only", action="store_true", help="only compare PostgreSQL and SurrealDB")
    args = parser.parse_args()

    pg = _pg_connect()
    targets: dict[str, Surreal] = {}
    failures: list[str] = []
    try:
        with pg.cursor() as cur:
            for schema, (database, tables) in TABLES.items():
                if database not in targets:
                    targets[database] = _surreal_connect(database)
                db = targets[database]
                print(f"\n=== {schema} -> {getattr(settings,'SURREAL_NAMESPACE','ia_juridica')}/{database} ===")
                for table, pk in tables:
                    source = _fetch_pg(cur, schema, table, pk)
                    src_sum = _checksum(source)
                    if args.apply:
                        db.query(f"REMOVE TABLE IF EXISTS {table};").execute()
                        for start in range(0, len(source), args.batch_size):
                            batch = _to_surreal_rows(table, source[start : start + args.batch_size], pk)
                            if batch:
                                db.query(f"INSERT INTO {table} $rows", {"rows": batch}).execute()
                    target = _surreal_rows(db, table)
                    tgt_sum = _checksum(target)
                    ok = len(source) == len(target) and src_sum == tgt_sum
                    status = "OK" if ok else "MISMATCH"
                    print(
                        f"  {table:<24} pg={len(source):>6} surreal={len(target):>6} "
                        f"{status} sha={src_sum[:12]}"
                    )
                    if not ok:
                        failures.append(f"{schema}.{table}: pg={len(source)} surreal={len(target)} "
                                        f"sha_pg={src_sum[:16]} sha_surreal={tgt_sum[:16]}")
    finally:
        for conn in targets.values():
            conn.close()
        pg.close()

    if failures:
        print("\nMISMATCHES:")
        for failure in failures:
            print(" -", failure)
        return 1
    print("\nAll tables migrated with count and checksum parity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
