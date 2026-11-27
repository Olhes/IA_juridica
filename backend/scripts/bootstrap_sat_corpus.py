"""Initialize or export the versioned SAT corpus snapshot for SurrealDB."""

from __future__ import annotations

import argparse
import base64
import gzip
from hashlib import file_digest
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import urllib.request

from surrealdb.errors import NotFoundError

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings
from database.surreal_connection import connect_surreal, surreal_credentials, surreal_url


SNAPSHOT = Path(__file__).resolve().parents[1] / "docs" / "sat_graph.surql.gz"
# Fallback counts for snapshots written before the embedded EXPECTED_ROWS header.
EXPECTED_ROWS = {
    "sat_chat_revision": 1,
    "sat_documents": 12,
    "sat_edges": 100419,
    "sat_meta": 1,
    "sat_nodes": 42531,
    "sat_parses": 4,
    "sat_reviews": 0,
}
SAT_TABLES = tuple(EXPECTED_ROWS)
EXPECTED_ROWS_PREFIX = "-- EXPECTED_ROWS: "
REVISION_QUERY = "SELECT VALUE id FROM sat_nodes WHERE kind = 'DocumentaryRevision' LIMIT 1"
DEFAULT_BATCH_MAX_BYTES = 512_000
DEFAULT_BATCH_MAX_STATEMENTS = 25
_EXPORT_LOCK = threading.Lock()
_SECTION_TABLE_RE = re.compile(r"^--\s+TABLE(?:\s+DATA)?:\s+(\S+)\s*$")
_INSERT_ARRAY_PREFIX_RE = re.compile(r"^INSERT\s+\[")
_OUTSIDE_DELIM_RE = re.compile(r"""['"`{}\[\]]""")
_QUOTE_DELIM_RES = {
    "'": re.compile(r"['\\]"),
    '"': re.compile(r'["\\]'),
    "`": re.compile(r"[`\\]"),
}


def _split_insert_statement(
    statement: str,
    max_bytes: int = DEFAULT_BATCH_MAX_BYTES,
) -> list[str]:
    """Split oversized ``INSERT [ {...}, ... ];`` statements into bounded array chunks."""
    if len(statement.encode("utf-8")) <= max_bytes:
        return [statement]
    match = _INSERT_ARRAY_PREFIX_RE.match(statement)
    if not match or not statement.endswith("];"):
        return [statement]

    body = statement[match.end() : -2]
    body_len = len(body)
    objects: list[str] = []
    in_quote: str | None = None
    depth = 0
    obj_start: int | None = None
    pos = 0

    while pos < body_len:
        if in_quote is not None:
            m = _QUOTE_DELIM_RES[in_quote].search(body, pos)
            if m is None:
                return [statement]
            ch = m.group(0)
            if ch == "\\":
                pos = m.end() + 1
            else:
                in_quote = None
                pos = m.end()
            continue

        m = _OUTSIDE_DELIM_RE.search(body, pos)
        if m is None:
            break
        idx = m.start()
        ch = m.group(0)
        pos = m.end()
        if ch in ("'", '"', "`"):
            in_quote = ch
        elif ch == "{":
            if depth == 0:
                obj_start = idx
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return [statement]
            if depth == 0 and obj_start is not None:
                objects.append(body[obj_start : idx + 1].strip())
                obj_start = None
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth < 0:
                return [statement]

    if in_quote is not None or depth != 0 or not objects:
        return [statement]

    chunks: list[str] = []
    current: list[str] = []
    # Fixed wrapper size for "INSERT [ " + " ];"
    wrapper_bytes = 12
    current_bytes = wrapper_bytes

    for obj in objects:
        obj_bytes = len(obj.encode("utf-8"))
        sep_bytes = 2 if current else 0
        if current and current_bytes + sep_bytes + obj_bytes > max_bytes:
            chunks.append(f"INSERT [ {', '.join(current)} ];")
            current = [obj]
            current_bytes = wrapper_bytes + obj_bytes
        else:
            current.append(obj)
            current_bytes += sep_bytes + obj_bytes

    if current:
        chunks.append(f"INSERT [ {', '.join(current)} ];")
    return chunks


def _statement_kind(statement: str) -> str:
    return "insert" if statement.startswith("INSERT ") else "ddl"


def _iter_statement_batches(
    snapshot: Path,
    *,
    max_bytes: int = DEFAULT_BATCH_MAX_BYTES,
    max_statements: int = DEFAULT_BATCH_MAX_STATEMENTS,
):
    """Yield bounded SurrealQL batches, keeping DDL separate from INSERT batches."""
    batch: list[str] = []
    batch_bytes = 0
    batch_kind: str | None = None

    with gzip.open(snapshot, "rt", encoding="utf-8") as statements:
        for line in statements:
            raw_statement = line.strip()
            if not raw_statement or raw_statement.startswith("--") or raw_statement == "OPTION IMPORT;":
                continue
            for statement in _split_insert_statement(raw_statement, max_bytes=max_bytes):
                kind = _statement_kind(statement)
                stmt_bytes = len(statement.encode("utf-8"))
                sep_bytes = 1 if batch else 0
                if batch and (
                    kind != batch_kind
                    or len(batch) >= max_statements
                    or batch_bytes + sep_bytes + stmt_bytes > max_bytes
                ):
                    yield "\n".join(batch)
                    batch = []
                    batch_bytes = 0
                    batch_kind = None
                batch.append(statement)
                batch_bytes += (1 if len(batch) > 1 else 0) + stmt_bytes
                batch_kind = kind

    if batch:
        yield "\n".join(batch)


def _has_revisions(connection) -> bool:
    try:
        return bool(connection.query(REVISION_QUERY).execute()[0])
    except NotFoundError:
        return False


def _filter_export_surql(raw_sql: str, allowed_tables: set[str]) -> str:
    """Keep header options and canonical SAT tables; drop transient/bootstrap tables."""
    kept: list[str] = []
    include_section = True
    pending_banner: list[str] = []

    for line in raw_sql.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == "-- ------------------------------":
            if pending_banner:
                pending_banner.append(line)
                if include_section:
                    kept.extend(pending_banner)
                pending_banner = []
            else:
                pending_banner = [line]
            continue
        if pending_banner:
            match = _SECTION_TABLE_RE.match(stripped)
            if match:
                include_section = match.group(1) in allowed_tables
            elif stripped.startswith("-- OPTION"):
                include_section = True
            pending_banner.append(line)
            continue
        if include_section:
            kept.append(line)

    if pending_banner and include_section:
        kept.extend(pending_banner)
    return "".join(kept)


def _parse_expected_rows(snapshot: Path) -> dict[str, int]:
    """Read embedded table counts from snapshot header, falling back to EXPECTED_ROWS."""
    with gzip.open(snapshot, "rt", encoding="utf-8") as stream:
        for _ in range(10):
            line = stream.readline()
            if not line:
                break
            if line.startswith(EXPECTED_ROWS_PREFIX):
                parsed = json.loads(line[len(EXPECTED_ROWS_PREFIX) :].strip())
                if (
                    isinstance(parsed, dict)
                    and set(parsed) == set(SAT_TABLES)
                    and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in parsed.values())
                ):
                    return parsed
                raise RuntimeError("Encabezado EXPECTED_ROWS inválido en el respaldo SAT.")
            if not line.strip().startswith("--") and line.strip():
                break
    return dict(EXPECTED_ROWS)


def _http_export_surql(database: str = "sat_graph") -> str:
    http_url = (
        surreal_url()
        .replace("ws://", "http://")
        .replace("wss://", "https://")
        .removesuffix("/rpc")
        + "/export"
    )
    user, password = surreal_credentials()
    auth = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        http_url,
        headers={
            "Accept": "application/octet-stream",
            "Authorization": f"Basic {auth}",
            "surreal-ns": settings.SURREAL_NAMESPACE,
            "surreal-db": database,
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8")


def _snapshot_sha256(snapshot: Path) -> str:
    with snapshot.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _recorded_snapshot_sha256(connection) -> str | None:
    try:
        rows = connection.query("SELECT VALUE snapshot_sha256 FROM sat_bootstrap:seed").execute()[0]
    except NotFoundError:
        return None
    if isinstance(rows, list):
        return rows[0] if rows and isinstance(rows[0], str) else None
    return rows if isinstance(rows, str) else None


def _record_snapshot_sha256(executor, sha: str) -> None:
    executor.query("DEFINE TABLE IF NOT EXISTS sat_bootstrap SCHEMALESS").execute()
    executor.query(
        "UPSERT sat_bootstrap:seed SET format = 'sat_graph.surql.gz', snapshot_sha256 = $sha",
        {"sha": sha},
    ).execute()


def export_snapshot(snapshot: Path = SNAPSHOT, *, database: str = "sat_graph") -> dict[str, int]:
    """Atomically export the live SurrealDB SAT corpus into a gzipped .surql snapshot."""
    with _EXPORT_LOCK:
        with connect_surreal(database) as connection:
            if not _has_revisions(connection):
                raise RuntimeError("No se puede exportar el corpus SAT: no existen revisiones publicadas.")
            counts: dict[str, int] = {}
            for table in SAT_TABLES:
                try:
                    rows = connection.query(f"SELECT VALUE count() FROM {table} GROUP ALL").execute()[0]
                    counts[table] = int(rows[0]) if rows else 0
                except NotFoundError:
                    counts[table] = 0
        raw_sql = _http_export_surql(database)
        filtered_sql = _filter_export_surql(raw_sql, set(SAT_TABLES))
        header = f"{EXPECTED_ROWS_PREFIX}{json.dumps(counts, sort_keys=True)}\n"

        snapshot.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=snapshot.parent, prefix=".sat_graph.", suffix=".tmp")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            with gzip.open(tmp_path, "wt", encoding="utf-8", compresslevel=6) as out:
                out.write(header)
                out.write(filtered_sql)
            os.replace(tmp_path, snapshot)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        sha = _snapshot_sha256(snapshot)
        with connect_surreal(database) as connection:
            _record_snapshot_sha256(connection, sha)
        return counts


def bootstrap(
    connection,
    snapshot: Path = SNAPSHOT,
    *,
    max_batch_bytes: int = DEFAULT_BATCH_MAX_BYTES,
    max_batch_statements: int = DEFAULT_BATCH_MAX_STATEMENTS,
) -> str:
    snapshot_sha = _snapshot_sha256(snapshot)
    if _has_revisions(connection) and _recorded_snapshot_sha256(connection) == snapshot_sha:
        return "present"

    expected_rows = _parse_expected_rows(snapshot)
    had_revisions = _has_revisions(connection)

    # Drop existing canonical tables before replaying DDL/data batches.
    # Clearing snapshot_sha256 first ensures any interrupted run retries cleanly
    # on the next boot without wrapping the entire multi-megabyte import in one
    # giant remote transaction.
    with connection.timeout(300):
        connection.query("DEFINE TABLE IF NOT EXISTS sat_bootstrap SCHEMALESS").execute()
        connection.query("DELETE sat_bootstrap:seed").execute()
        for table in expected_rows:
            connection.query(f"REMOVE TABLE IF EXISTS {table}").execute()

    with connection.timeout(300):
        for batch in _iter_statement_batches(
            snapshot,
            max_bytes=max_batch_bytes,
            max_statements=max_batch_statements,
        ):
            connection.query(batch).execute()
        for table, expected in expected_rows.items():
            rows = connection.query(f"SELECT VALUE count() FROM {table} GROUP ALL").execute()[0]
            if (rows[0] if rows else 0) != expected:
                raise RuntimeError(f"El respaldo SAT no coincide con el conteo esperado de {table}.")
        if not _has_revisions(connection):
            raise RuntimeError("El respaldo SAT no contiene revisiones publicadas.")
        _record_snapshot_sha256(connection, snapshot_sha)
    return "updated" if had_revisions else "restored"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true", help="Export live sat_graph to sat_graph.surql.gz")
    args = parser.parse_args()
    if args.export:
        counts = export_snapshot()
        print(f"exported {SNAPSHOT} ({json.dumps(counts, sort_keys=True)})")
        return
    with connect_surreal("sat_graph") as connection:
        print(bootstrap(connection))


if __name__ == "__main__":
    main()
