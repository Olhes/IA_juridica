"""One-off copy from PostgreSQL into empty SurrealDB tables."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import uuid
from contextlib import ExitStack, nullcontext
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
    rows = result[0] if result else []
    for row in rows:
        key = row["id"].id
        row["__pk"] = _pk_string(tuple(key)) if isinstance(key, list) else str(key)
    return rows


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
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true", help="copy into empty target tables")
    mode.add_argument("--verify-only", action="store_true", help="compare counts and checksums")
    parser.add_argument("--sat-only", action="store_true", help="only process the published SAT corpus")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    schemas = ("sat_graph",) if args.sat_only else TABLES
    failures = []
    try:
        with ExitStack() as stack:
            pg = stack.enter_context(_pg_connect())
            with pg.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                for schema in schemas:
                    database, tables = TABLES[schema]
                    with _surreal_connect(database) as target, target.timeout(300):
                        context = target.begin_transaction() if args.apply else nullcontext(target)
                        with context as db:
                            for table, pk in tables:
                                source = _fetch_pg(cur, schema, table, pk)
                                before = _surreal_rows(db, table)
                                if args.apply:
                                    if before:
                                        raise RuntimeError(f"Target {database}.{table} contains data")
                                    for start in range(0, len(source), args.batch_size):
                                        batch = _to_surreal_rows(table, source[start : start + args.batch_size], pk)
                                        db.query(f"INSERT INTO {table} $rows", {"rows": batch}).execute()
                                rows = _surreal_rows(db, table) if args.apply else before
                                ok = len(source) == len(rows) and _checksum(source) == _checksum(rows)
                                label = f"{schema}.{table}"
                                print(f"{label}: pg={len(source)} surreal={len(rows)} {'OK' if ok else 'MISMATCH'}")
                                if not ok:
                                    if args.apply:
                                        raise RuntimeError(f"Count or checksum mismatch in {label}")
                                    failures.append(label)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
