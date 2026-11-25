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
_EXPORT_LOCK = threading.Lock()
_SECTION_TABLE_RE = re.compile(r"^--\s+TABLE(?:\s+DATA)?:\s+(\S+)\s*$")


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


def bootstrap(connection, snapshot: Path = SNAPSHOT) -> str:
    snapshot_sha = _snapshot_sha256(snapshot)
    if _has_revisions(connection) and _recorded_snapshot_sha256(connection) == snapshot_sha:
        return "present"

    expected_rows = _parse_expected_rows(snapshot)
    had_revisions = _has_revisions(connection)

    # Drop existing canonical tables before starting the import transaction:
    # SurrealDB forbids DEFINE INDEX in the same transaction that deleted rows
    # from that table. Clearing snapshot_sha256 first ensures any interrupted
    # update retries cleanly on the next boot.
    with connection.timeout(300):
        connection.query("DEFINE TABLE IF NOT EXISTS sat_bootstrap SCHEMALESS").execute()
        connection.query("DELETE sat_bootstrap:seed").execute()
        for table in expected_rows:
            connection.query(f"REMOVE TABLE IF EXISTS {table}").execute()

    with connection.timeout(300), connection.begin_transaction() as transaction:
        _record_snapshot_sha256(transaction, snapshot_sha)

        # The native export emits one DEFINE or INSERT per line. Replay each
        # statement in the same transaction to limit the size of each RPC.
        with gzip.open(snapshot, "rt", encoding="utf-8") as statements:
            for line in statements:
                statement = line.strip()
                if statement and not statement.startswith("--") and statement != "OPTION IMPORT;":
                    transaction.query(statement).execute()
        for table, expected in expected_rows.items():
            rows = transaction.query(f"SELECT VALUE count() FROM {table} GROUP ALL").execute()[0]
            if (rows[0] if rows else 0) != expected:
                raise RuntimeError(f"El respaldo SAT no coincide con el conteo esperado de {table}.")
        if not _has_revisions(transaction):
            raise RuntimeError("El respaldo SAT no contiene revisiones publicadas.")
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
