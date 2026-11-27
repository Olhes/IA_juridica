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
import time
import urllib.request

import httpx
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
DEFAULT_HTTP_IMPORT_MAX_BYTES = 512 * 1024
_EXPORT_LOCK = threading.Lock()
_SECTION_TABLE_RE = re.compile(r"^--\s+TABLE(?:\s+DATA)?:\s+(\S+)\s*$")
_INSERT_ARRAY_PREFIX_RE = re.compile(r"^INSERT\s+\[")
_OUTSIDE_DELIM_RE = re.compile(r"""['"`{}\[\]]""")
_QUOTE_DELIM_RES = {
    "'": re.compile(r"['\\]"),
    '"': re.compile(r'["\\]'),
    "`": re.compile(r"[`\\]"),
}
_FIELD_STR_RES = {
    field: re.compile(rf"\b{field}:\s*(['\"])")
    for field in ("nid", "kind", "payload", "predicate", "source", "target")
}


def _extract_surql_string(obj: str, field: str) -> str | None:
    """Extract and unescape a single- or double-quoted string field from a SurrealQL object literal."""
    match = _FIELD_STR_RES[field].search(obj)
    if not match:
        return None
    quote = match.group(1)
    pos = match.end()
    delim = _QUOTE_DELIM_RES[quote]
    while True:
        found = delim.search(obj, pos)
        if found is None:
            return None
        if found.group(0) == "\\":
            pos = found.end() + 1
        else:
            raw = obj[match.end() : found.start()]
            break
    def _unescape(m: re.Match[str]) -> str:
        esc = m.group(1)
        if esc.startswith("u") and len(esc) == 5:
            return chr(int(esc[1:], 16))
        return {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "b": "\b",
            "f": "\f",
            "\\": "\\",
            "'": "'",
            '"': '"',
            "/": "/",
        }.get(esc, esc)

    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", _unescape, raw)


def _extract_surql_payload(obj: str) -> dict:
    raw = _extract_surql_string(obj, "payload")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


def _replace_surql_payload(obj: str, payload: dict) -> str:
    """Replace the `payload: '...'` / `payload: \"...\"` string literal in a SurrealQL object."""
    match = _FIELD_STR_RES["payload"].search(obj)
    if not match:
        return obj
    quote = match.group(1)
    pos = match.end()
    delim = _QUOTE_DELIM_RES[quote]
    while True:
        found = delim.search(obj, pos)
        if found is None:
            return obj
        if found.group(0) == "\\":
            pos = found.end() + 1
        else:
            end_pos = found.end()
            break
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    escaped = encoded.replace("\\", "\\\\").replace("'", "\\'")
    return obj[: match.start()] + f"payload: '{escaped}'" + obj[end_pos:]


_ELIGIBLE_WORK_KINDS = frozenset({"article", "numeral", "inciso", "subinciso", "disposition"})
_CHAT_EDGE_PREDICATES = frozenset(
    {"has_text", "contains_version", "amended_by", "documentary_has_part", "derived_from_documentary"}
)


def _extract_insert_objects(statement: str) -> list[str] | None:
    """Return bare top-level ``{...}`` object literals from an ``INSERT [ ... ];`` statement."""
    match = _INSERT_ARRAY_PREFIX_RE.match(statement)
    if not match or not statement.endswith("];"):
        return None

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
                return None
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
                return None
            if depth == 0 and obj_start is not None:
                objects.append(body[obj_start : idx + 1].strip())
                obj_start = None
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth < 0:
                return None

    if in_quote is not None or depth != 0 or not objects:
        return None
    return objects


def _pack_insert_objects(
    objects: list[str],
    max_bytes: int = DEFAULT_BATCH_MAX_BYTES,
) -> list[str]:
    """Pack bare ``{...}`` objects into bounded ``INSERT [ ... ];`` statements."""
    chunks: list[str] = []
    current: list[str] = []
    wrapper_bytes = 12  # "INSERT [ " + " ];"
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


def _split_insert_statement(
    statement: str,
    max_bytes: int = DEFAULT_BATCH_MAX_BYTES,
) -> list[str]:
    """Split oversized ``INSERT [ {...}, ... ];`` statements into bounded array chunks."""
    if len(statement.encode("utf-8")) <= max_bytes:
        return [statement]
    objects = _extract_insert_objects(statement)
    if not objects:
        return [statement]
    return _pack_insert_objects(objects, max_bytes=max_bytes)


def _statement_kind(statement: str) -> str:
    return "insert" if statement.startswith("INSERT ") else "ddl"


def _iter_statement_batches(
    snapshot: Path,
    *,
    max_bytes: int = DEFAULT_BATCH_MAX_BYTES,
    max_statements: int = DEFAULT_BATCH_MAX_STATEMENTS,
    separate_ddl: bool = True,
):
    """Yield bounded SurrealQL batches, optionally keeping DDL separate from INSERT batches."""
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
                    (separate_ddl and kind != batch_kind)
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


def _http_base_url() -> str:
    return (
        surreal_url()
        .replace("ws://", "http://")
        .replace("wss://", "https://")
        .removesuffix("/rpc")
    )


def _http_auth_header(client: httpx.Client | None = None, connection=None) -> str:
    """Resolve HTTP Authorization header: prefer JWT Bearer (required by SurrealDB Cloud)."""
    conn_token = getattr(connection, "token", None)
    if isinstance(conn_token, str) and conn_token:
        return f"Bearer {conn_token}"

    user, password = surreal_credentials()
    signin_url = _http_base_url() + "/signin"
    try:
        if client is not None:
            resp = client.post(
                signin_url,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json={"user": user, "pass": password},
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("token") if isinstance(data, dict) else None
                if isinstance(token, str) and token:
                    return f"Bearer {token}"
        else:
            with httpx.Client(timeout=30.0) as tmp_client:
                return _http_auth_header(tmp_client, connection=None)
    except Exception:
        pass

    auth = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {auth}"


def _http_export_surql(database: str = "sat_graph") -> str:
    http_url = _http_base_url() + "/export"
    request = urllib.request.Request(
        http_url,
        headers={
            "Accept": "application/octet-stream",
            "Authorization": _http_auth_header(),
            "surreal-ns": settings.SURREAL_NAMESPACE,
            "surreal-db": database,
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8")


def _http_import_surql(
    snapshot: Path,
    *,
    database: str = "sat_graph",
    max_part_bytes: int = DEFAULT_HTTP_IMPORT_MAX_BYTES,
    progress: bool = False,
    connection=None,
) -> None:
    """Import a gzipped .surql export via bounded HTTP POST /import parts (< Cloudflare 100 MB cap)."""
    http_url = _http_base_url() + "/import"
    timeout = httpx.Timeout(connect=30.0, read=180.0, write=120.0, pool=30.0)
    prefix = b"OPTION IMPORT;\n"
    part_budget = max(1024, max_part_bytes - len(prefix) - 1)

    with httpx.Client(timeout=timeout) as client:
        headers = {
            "Accept": "application/json",
            "Authorization": _http_auth_header(client, connection=connection),
            "Content-Type": "text/plain; charset=utf-8",
            "surreal-ns": settings.SURREAL_NAMESPACE,
            "surreal-db": database,
        }
        for idx, batch in enumerate(
            _iter_statement_batches(
                snapshot,
                max_bytes=part_budget,
                max_statements=10_000,
                separate_ddl=False,
            ),
            start=1,
        ):
            body = prefix + batch.encode("utf-8") + b"\n"
            t0 = time.perf_counter()
            if progress:
                print(
                    f"[sat-bootstrap] HTTP /import part {idx} ({len(body) / (1024 * 1024):.2f} MB)...",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )
            response = client.post(http_url, headers=headers, content=body)
            elapsed = time.perf_counter() - t0
            if progress:
                print(
                    f" {response.status_code} ({elapsed:.1f}s)",
                    file=sys.stderr,
                    flush=True,
                )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP /import falló en parte {idx} ({response.status_code}): {response.text[:300]}"
                )
            try:
                payload = response.json()
            except ValueError:
                continue
            if isinstance(payload, list):
                for entry in payload:
                    if isinstance(entry, dict) and entry.get("status") == "ERR":
                        detail = entry.get("result") or entry.get("detail") or str(entry)
                        raise RuntimeError(
                            f"HTTP /import devolvió error SurrealQL en parte {idx}: {detail}"
                        )


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
    use_http_import: bool = False,
    http_part_bytes: int = DEFAULT_HTTP_IMPORT_MAX_BYTES,
    database: str = "sat_graph",
    progress: bool = False,
) -> str:
    snapshot_sha = _snapshot_sha256(snapshot)
    if _has_revisions(connection) and _recorded_snapshot_sha256(connection) == snapshot_sha:
        return "present"

    expected_rows = _parse_expected_rows(snapshot)
    had_revisions = _has_revisions(connection)

    # Drop existing canonical tables before replaying DDL/data.
    # Clearing snapshot_sha256 first ensures any interrupted run retries cleanly
    # on the next boot without wrapping the entire multi-megabyte import in one
    # giant remote transaction.
    if progress:
        print("[sat-bootstrap] clearing existing SAT tables...", file=sys.stderr, flush=True)
    with connection.timeout(300):
        connection.query("DEFINE TABLE IF NOT EXISTS sat_bootstrap SCHEMALESS").execute()
        connection.query("DELETE sat_bootstrap:seed").execute()
        for table in expected_rows:
            connection.query(f"REMOVE TABLE IF EXISTS {table}").execute()

    if use_http_import:
        if progress:
            print(
                f"[sat-bootstrap] importing {snapshot.name} via HTTP /import...",
                file=sys.stderr,
                flush=True,
            )
        _http_import_surql(
            snapshot,
            database=database,
            max_part_bytes=http_part_bytes,
            progress=progress,
            connection=connection,
        )
    else:
        with connection.timeout(300):
            for idx, batch in enumerate(
                _iter_statement_batches(
                    snapshot,
                    max_bytes=max_batch_bytes,
                    max_statements=max_batch_statements,
                ),
                start=1,
            ):
                connection.query(batch).execute()
                if progress and idx % 25 == 0:
                    print(
                        f"[sat-bootstrap] applied {idx} WebSocket batches...",
                        file=sys.stderr,
                        flush=True,
                    )

    if progress:
        print("[sat-bootstrap] verifying row counts...", file=sys.stderr, flush=True)
    with connection.timeout(300):
        for table, expected in expected_rows.items():
            rows = connection.query(f"SELECT VALUE count() FROM {table} GROUP ALL").execute()[0]
            if (rows[0] if rows else 0) != expected:
                raise RuntimeError(f"El respaldo SAT no coincide con el conteo esperado de {table}.")
        if not _has_revisions(connection):
            raise RuntimeError("El respaldo SAT no contiene revisiones publicadas.")
        _record_snapshot_sha256(connection, snapshot_sha)
    return "updated" if had_revisions else "restored"


def compact_snapshot(snapshot: Path = SNAPSHOT) -> dict[str, int]:
    """Compact a SAT snapshot to active chat-runtime data, dropping superseded versions and documentary audit bloat."""
    nodes_meta: dict[str, tuple[str, dict]] = {}
    edges_meta: list[tuple[str, str, str]] = []
    cur_table: str | None = None

    with gzip.open(snapshot, "rt", encoding="utf-8") as stream:
        for line in stream:
            match = _SECTION_TABLE_RE.match(line.strip())
            if match:
                cur_table = match.group(1)
                continue
            stripped = line.strip()
            if not stripped.startswith("INSERT "):
                continue
            if cur_table == "sat_nodes":
                for obj in _extract_insert_objects(stripped) or ():
                    nid = _extract_surql_string(obj, "nid")
                    kind = _extract_surql_string(obj, "kind")
                    if nid and kind:
                        nodes_meta[nid] = (kind, _extract_surql_payload(obj))
            elif cur_table == "sat_edges":
                for obj in _extract_insert_objects(stripped) or ():
                    pred = _extract_surql_string(obj, "predicate")
                    src = _extract_surql_string(obj, "source")
                    tgt = _extract_surql_string(obj, "target")
                    if pred and src and tgt:
                        edges_meta.append((pred, src, tgt))

    active_ctvs = {
        nid
        for nid, (k, p) in nodes_meta.items()
        if k == "CTV" and not p.get("editorial_superseded_by")
    }
    active_revs = {
        nid
        for nid, (k, p) in nodes_meta.items()
        if k == "DocumentaryRevision" and not p.get("editorial_superseded_by")
    }
    referenced_clvs = {
        tgt for pred, src, tgt in edges_meta if pred == "has_text" and src in active_ctvs
    }
    active_works = {nodes_meta[cid][1].get("work_id") for cid in active_ctvs}

    # Container CLVs (libro/titulo/capitulo/document) are never returned as chunks;
    # SATRetriever._ancestor_headings() only reads their first 3 non-empty lines (<=200 chars).
    clv_is_container: dict[str, bool] = {}
    for pred, src, tgt in edges_meta:
        if pred != "has_text" or src not in active_ctvs:
            continue
        ctv_payload = nodes_meta[src][1]
        if ctv_payload.get("provenance_state") == "reviewed":
            clv_is_container[tgt] = False
            continue
        wid = ctv_payload.get("work_id")
        work_kind = nodes_meta[wid][1].get("kind") if wid in nodes_meta else None
        is_container = work_kind not in _ELIGIBLE_WORK_KINDS
        clv_is_container[tgt] = clv_is_container.get(tgt, True) and is_container

    kept_nodes: set[str] = set()
    for nid, (k, p) in nodes_meta.items():
        if (
            k == "Resource"
            or (k == "Work" and nid in active_works)
            or (k == "CTV" and nid in active_ctvs)
            or (k == "CLV" and nid in referenced_clvs)
            or (k == "DocumentaryRevision" and nid in active_revs)
            or (k == "DocumentaryComponent" and p.get("revision_id") in active_revs)
        ):
            kept_nodes.add(nid)

    counts = {tbl: 0 for tbl in SAT_TABLES}
    out_lines: list[str] = []
    cur_table = None

    with gzip.open(snapshot, "rt", encoding="utf-8") as stream:
        for line in stream:
            stripped = line.strip()
            if stripped.startswith(EXPECTED_ROWS_PREFIX):
                continue
            match = _SECTION_TABLE_RE.match(stripped)
            if match:
                cur_table = match.group(1)
                out_lines.append(line)
                continue
            if not stripped.startswith("INSERT "):
                out_lines.append(line)
                continue

            objs = _extract_insert_objects(stripped) or []
            if cur_table == "sat_nodes":
                kept: list[str] = []
                for obj in objs:
                    nid = _extract_surql_string(obj, "nid")
                    if nid not in kept_nodes:
                        continue
                    kind, payload = nodes_meta[nid]
                    if kind == "CLV" and clv_is_container.get(nid):
                        text = payload.get("text") or ""
                        snippet = "\n".join(text.splitlines()[:3])
                        if len(snippet) > 250:
                            snippet = snippet[:250]
                        if len(snippet) < len(text):
                            obj = _replace_surql_payload(obj, {**payload, "text": snippet})
                    kept.append(obj)
            elif cur_table == "sat_edges":
                kept = [
                    _replace_surql_payload(obj, {})
                    for obj in objs
                    if (
                        _extract_surql_string(obj, "predicate") in _CHAT_EDGE_PREDICATES
                        and _extract_surql_string(obj, "source") in kept_nodes
                        and _extract_surql_string(obj, "target") in kept_nodes
                    )
                ]
            elif cur_table in {"sat_documents", "sat_parses"}:
                kept = []
            else:
                kept = objs

            if cur_table in counts:
                counts[cur_table] += len(kept)
            if kept:
                for chunk in _pack_insert_objects(kept, max_bytes=DEFAULT_BATCH_MAX_BYTES):
                    out_lines.append(chunk + "\n")

    header = f"{EXPECTED_ROWS_PREFIX}{json.dumps(counts, sort_keys=True)}\n"
    fd, tmp_name = tempfile.mkstemp(dir=snapshot.parent, prefix=".sat_graph.", suffix=".tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with gzip.open(tmp_path, "wt", encoding="utf-8", compresslevel=6, newline="\n") as out:
            out.write(header)
            out.writelines(out_lines)
        os.replace(tmp_path, snapshot)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true", help="Export live sat_graph to sat_graph.surql.gz")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Prune editorially superseded versions and dangling edges from sat_graph.surql.gz in place.",
    )
    parser.add_argument(
        "--method",
        choices=("http", "ws"),
        default="http",
        help="Import transport: native HTTP /import stream (default) or batched WebSocket RPC.",
    )
    parser.add_argument(
        "--part-mb",
        type=float,
        default=DEFAULT_HTTP_IMPORT_MAX_BYTES / (1024 * 1024),
        help="Max size in MiB per HTTP /import part (default: 0.5).",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress stderr progress messages.")
    args = parser.parse_args()
    if args.export:
        counts = export_snapshot()
        print(f"exported {SNAPSHOT} ({json.dumps(counts, sort_keys=True)})")
        return
    if args.compact:
        counts = compact_snapshot()
        print(f"compacted {SNAPSHOT} ({json.dumps(counts, sort_keys=True)})")
        return
    progress = not args.quiet
    if progress:
        print(
            f"[sat-bootstrap] connecting to {surreal_url()} (ns={settings.SURREAL_NAMESPACE})...",
            file=sys.stderr,
            flush=True,
        )
    with connect_surreal("sat_graph") as connection:
        print(
            bootstrap(
                connection,
                use_http_import=(args.method == "http"),
                http_part_bytes=max(64 * 1024, int(args.part_mb * 1024 * 1024)),
                progress=progress,
            )
        )


if __name__ == "__main__":
    main()
