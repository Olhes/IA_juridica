import gzip
import json
from contextlib import nullcontext

import pytest

from scripts import bootstrap_sat_corpus as mod
from services import sat_corpus_routes as routes


SAMPLE_EXPORT = """-- ------------------------------
-- OPTION
-- ------------------------------

OPTION IMPORT;

-- ------------------------------
-- TABLE: sat_nodes
-- ------------------------------

DEFINE TABLE sat_nodes TYPE ANY SCHEMALESS PERMISSIONS NONE;

-- ------------------------------
-- TABLE DATA: sat_nodes
-- ------------------------------

INSERT [ { id: sat_nodes:`1`, kind: 'DocumentaryRevision' } ];

-- ------------------------------
-- TABLE: sat_bootstrap
-- ------------------------------

DEFINE TABLE sat_bootstrap TYPE ANY SCHEMALESS PERMISSIONS NONE;

-- ------------------------------
-- TABLE DATA: sat_bootstrap
-- ------------------------------

INSERT [ { id: sat_bootstrap:seed, format: 'sat_graph.surql.gz' } ];

-- ------------------------------
-- TABLE: zz_probe
-- ------------------------------

DEFINE TABLE zz_probe TYPE ANY SCHEMALESS PERMISSIONS NONE;

-- ------------------------------
-- TABLE: sat_meta
-- ------------------------------

DEFINE TABLE sat_meta TYPE ANY SCHEMALESS PERMISSIONS NONE;
"""


def test_filter_export_surql_keeps_only_canonical_tables():
    filtered = mod._filter_export_surql(SAMPLE_EXPORT, set(mod.SAT_TABLES))
    assert "OPTION IMPORT;" in filtered
    assert "DEFINE TABLE sat_nodes" in filtered
    assert "INSERT [ { id: sat_nodes:`1`" in filtered
    assert "DEFINE TABLE sat_meta" in filtered
    assert "sat_bootstrap" not in filtered
    assert "zz_probe" not in filtered


def test_parse_expected_rows_reads_embedded_header_and_falls_back(tmp_path):
    custom = {tbl: idx + 1 for idx, tbl in enumerate(mod.SAT_TABLES)}
    with_header = tmp_path / "with_header.surql.gz"
    with gzip.open(with_header, "wt", encoding="utf-8") as out:
        out.write(f"{mod.EXPECTED_ROWS_PREFIX}{json.dumps(custom)}\nOPTION IMPORT;\n")
    assert mod._parse_expected_rows(with_header) == custom

    legacy = tmp_path / "legacy.surql.gz"
    with gzip.open(legacy, "wt", encoding="utf-8") as out:
        out.write("-- OPTION\nOPTION IMPORT;\n")
    assert mod._parse_expected_rows(legacy) == mod.EXPECTED_ROWS


def test_export_snapshot_writes_atomic_gzip_and_rejects_empty_db(tmp_path, monkeypatch):
    class FakeQuery:
        def __init__(self, result):
            self._result = result

        def execute(self):
            return [self._result]

    class FakeConn:
        def __init__(self, has_rev=True):
            self.has_rev = has_rev

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, sql, params=None):
            if sql == mod.REVISION_QUERY:
                return FakeQuery(["rev:1"] if self.has_rev else [])
            if "sat_bootstrap" in sql:
                return FakeQuery([])
            for idx, tbl in enumerate(mod.SAT_TABLES):
                if f"FROM {tbl}" in sql:
                    return FakeQuery([idx + 10])
            raise AssertionError(f"Unexpected query: {sql}")

    target = tmp_path / "sat_graph.surql.gz"
    monkeypatch.setattr(mod, "connect_surreal", lambda db="sat_graph": FakeConn(has_rev=False))
    with pytest.raises(RuntimeError, match="no existen revisiones"):
        mod.export_snapshot(target)
    assert not target.exists()

    monkeypatch.setattr(mod, "connect_surreal", lambda db="sat_graph": FakeConn(has_rev=True))
    monkeypatch.setattr(mod, "_http_export_surql", lambda db="sat_graph": SAMPLE_EXPORT)
    counts = mod.export_snapshot(target)
    assert counts == {tbl: idx + 10 for idx, tbl in enumerate(mod.SAT_TABLES)}
    assert target.is_file()
    assert mod._parse_expected_rows(target) == counts
    with gzip.open(target, "rt", encoding="utf-8") as stream:
        body = stream.read()
    assert "sat_bootstrap" not in body
    assert "zz_probe" not in body
    assert "DEFINE TABLE sat_nodes" in body


def test_maybe_export_snapshot_skips_non_surreal_and_runs_for_surreal(monkeypatch):
    called = []
    monkeypatch.setattr(routes, "export_snapshot", lambda: called.append(True) or {"sat_nodes": 1})
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("SAT_AUTO_EXPORT_SNAPSHOT", raising=False)

    # Non-Surreal store is skipped
    routes._maybe_export_snapshot(object())
    assert called == []

    # Candidate Surreal store is skipped
    cand_store = routes.SurrealSATGraphStore.__new__(routes.SurrealSATGraphStore)
    cand_store.candidates = True
    routes._maybe_export_snapshot(cand_store)
    assert called == []

    # Live Surreal SAT store triggers export
    live_store = routes.SurrealSATGraphStore.__new__(routes.SurrealSATGraphStore)
    live_store.candidates = False
    routes._maybe_export_snapshot(live_store)
    assert called == [True]


def test_bootstrap_overwrites_when_snapshot_hash_changes_and_skips_when_identical(tmp_path):
    counts = {tbl: 1 if tbl == "sat_nodes" else 0 for tbl in mod.SAT_TABLES}
    snap = tmp_path / "sat_graph.surql.gz"
    with gzip.open(snap, "wt", encoding="utf-8") as out:
        out.write(f"{mod.EXPECTED_ROWS_PREFIX}{json.dumps(counts)}\n")
        out.write("DEFINE TABLE sat_nodes TYPE ANY SCHEMALESS PERMISSIONS NONE;\n")
        out.write("INSERT [ { id: sat_nodes:`1`, kind: 'DocumentaryRevision' } ];\n")

    class FakeQuery:
        def __init__(self, result):
            self._result = result

        def execute(self):
            return [self._result]

    class FakeConn:
        def __init__(self, stored_sha=None, has_rev=True):
            self.stored_sha = stored_sha
            self.has_rev = has_rev
            self.executed = []

        def timeout(self, _seconds):
            return nullcontext()

        def begin_transaction(self):
            return nullcontext(self)

        def query(self, sql, params=None):
            self.executed.append(sql)
            if sql == mod.REVISION_QUERY:
                return FakeQuery(["rev:1"] if self.has_rev else [])
            if "SELECT VALUE snapshot_sha256 FROM sat_bootstrap:seed" in sql:
                return FakeQuery([self.stored_sha] if self.stored_sha else [])
            if "DELETE sat_bootstrap:seed" in sql:
                self.stored_sha = None
                return FakeQuery([])
            if "UPSERT sat_bootstrap:seed" in sql:
                self.stored_sha = params["sha"]
                return FakeQuery([])
            if sql.startswith("REMOVE TABLE IF EXISTS ") or sql.startswith("DEFINE TABLE ") or sql.startswith("INSERT "):
                if sql.startswith("INSERT "):
                    self.has_rev = True
                return FakeQuery([])
            for tbl, val in counts.items():
                if f"FROM {tbl}" in sql:
                    return FakeQuery([val])
            raise AssertionError(f"Unexpected SQL: {sql}")

    sha = mod._snapshot_sha256(snap)

    # 1. Existing DB with identical hash -> skips overwrite ("present")
    same_conn = FakeConn(stored_sha=sha, has_rev=True)
    assert mod.bootstrap(same_conn, snap) == "present"
    assert not any(s.startswith("REMOVE TABLE") for s in same_conn.executed)

    # 2. Existing DB with stale/different hash -> overwrites ("updated")
    stale_conn = FakeConn(stored_sha="old-hash", has_rev=True)
    assert mod.bootstrap(stale_conn, snap) == "updated"
    assert sum(s.startswith("REMOVE TABLE IF EXISTS ") for s in stale_conn.executed) == len(mod.SAT_TABLES)
    assert stale_conn.stored_sha == sha

    # 3. Empty DB -> restores ("restored")
    empty_conn = FakeConn(stored_sha=None, has_rev=False)
    assert mod.bootstrap(empty_conn, snap) == "restored"
    assert empty_conn.stored_sha == sha


def test_split_insert_statement_splits_oversized_array_respecting_quotes():
    obj_a = "{ id: sat_nodes:`a`, text: 'hola, } [mundo]' }"
    obj_b = "{ id: sat_nodes:`b`, text: \"comilla \\\"interna\\\" }\" }"
    obj_c = "{ id: sat_nodes:`c`, text: 'tercero' }"
    stmt = f"INSERT [ {obj_a}, {obj_b}, {obj_c} ];"

    parts = mod._split_insert_statement(stmt, max_bytes=len(obj_a) + 30)
    assert len(parts) == 3
    for part in parts:
        assert part.startswith("INSERT [ ") and part.endswith(" ];")
    assert obj_a in parts[0] and obj_b in parts[1] and obj_c in parts[2]


def test_iter_statement_batches_groups_small_statements_and_separates_ddl(tmp_path):
    snap = tmp_path / "batched.surql.gz"
    with gzip.open(snap, "wt", encoding="utf-8") as out:
        out.write("OPTION IMPORT;\n")
        out.write("DEFINE TABLE sat_nodes SCHEMALESS;\n")
        out.write("DEFINE INDEX idx_a ON sat_nodes COLUMNS nid;\n")
        out.write("INSERT [ { id: sat_nodes:`1` } ];\n")
        out.write("INSERT [ { id: sat_nodes:`2` } ];\n")

    batches = list(mod._iter_statement_batches(snap, max_bytes=1024, max_statements=10))
    assert len(batches) == 2
    assert batches[0].startswith("DEFINE TABLE") and "DEFINE INDEX" in batches[0]
    assert batches[1].startswith("INSERT [") and "sat_nodes:`2`" in batches[1]


def test_bootstrap_records_sha_only_after_row_counts_pass(tmp_path):
    counts = {tbl: 1 if tbl == "sat_nodes" else 0 for tbl in mod.SAT_TABLES}
    snap = tmp_path / "fail_count.surql.gz"
    with gzip.open(snap, "wt", encoding="utf-8") as out:
        out.write(f"{mod.EXPECTED_ROWS_PREFIX}{json.dumps(counts)}\n")
        out.write("DEFINE TABLE sat_nodes SCHEMALESS;\n")
        out.write("INSERT [ { id: sat_nodes:`1`, kind: 'DocumentaryRevision' } ];\n")

    class FakeQuery:
        def __init__(self, result):
            self._result = result

        def execute(self):
            return [self._result]

    class FailingCountConn:
        def __init__(self):
            self.stored_sha = "stale-sha"
            self.upserted = False

        def timeout(self, _seconds):
            return nullcontext()

        def query(self, sql, params=None):
            if sql == mod.REVISION_QUERY:
                return FakeQuery([])
            if "SELECT VALUE snapshot_sha256" in sql:
                return FakeQuery([self.stored_sha] if self.stored_sha else [])
            if "DELETE sat_bootstrap:seed" in sql:
                self.stored_sha = None
                return FakeQuery([])
            if "UPSERT sat_bootstrap:seed" in sql:
                self.upserted = True
                return FakeQuery([])
            if sql.startswith("REMOVE TABLE") or sql.startswith("DEFINE TABLE") or sql.startswith("INSERT "):
                return FakeQuery([])
            if "SELECT VALUE count() FROM sat_nodes" in sql:
                return FakeQuery([0])
            return FakeQuery([0])

    conn = FailingCountConn()
    with pytest.raises(RuntimeError, match="conteo esperado de sat_nodes"):
        mod.bootstrap(conn, snap)
    assert conn.stored_sha is None
    assert conn.upserted is False


def test_http_import_surql_chunks_payload_and_checks_errors(tmp_path, monkeypatch):
    snap = tmp_path / "sample.surql.gz"
    raw = (
        "OPTION IMPORT;\n"
        "DEFINE TABLE sat_nodes SCHEMALESS;\n"
        "INSERT [ { id: sat_nodes:`1`, text: '" + ("a" * 800) + "' } ];\n"
        "INSERT [ { id: sat_nodes:`2`, text: '" + ("b" * 800) + "' } ];\n"
    )
    with gzip.open(snap, "wt", encoding="utf-8", newline="\n") as out:
        out.write(raw)

    captured = []

    class FakeResponse:
        def __init__(self, status_code=200, body=None, text="ok"):
            self.status_code = status_code
            self._body = body
            self.text = text

        def json(self):
            return self._body

    def make_client(resp):
        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, url, *, headers, content=None, json=None):
                if url.endswith("/signin"):
                    return FakeResponse(200, {"token": "jwt-from-signin"})
                body_str = content.decode("utf-8") if isinstance(content, (bytes, bytearray)) else b"".join(content).decode("utf-8")
                captured.append({"url": url, "headers": headers, "body": body_str})
                return resp

        return FakeClient

    monkeypatch.setattr(mod, "surreal_url", lambda: "wss://demo.surreal.cloud/rpc")
    monkeypatch.setattr(mod, "surreal_credentials", lambda: ("ia_admin", "secret"))
    monkeypatch.setattr(mod.httpx, "Client", make_client(FakeResponse(200, [{"status": "OK"}])))

    class ConnWithToken:
        token = "jwt-from-ws"

    mod._http_import_surql(snap, database="sat_graph", max_part_bytes=1200, connection=ConnWithToken())
    assert len(captured) == 2
    for part in captured:
        assert part["url"] == "https://demo.surreal.cloud/import"
        assert part["headers"]["surreal-db"] == "sat_graph"
        assert part["headers"]["Authorization"] == "Bearer jwt-from-ws"
        assert part["body"].startswith("OPTION IMPORT;\n")
    assert "DEFINE TABLE sat_nodes" in captured[0]["body"]
    assert "sat_nodes:`1`" in captured[0]["body"]
    assert "sat_nodes:`2`" in captured[1]["body"]

    captured.clear()
    mod._http_import_surql(snap, database="sat_graph", max_part_bytes=1200)
    assert captured[0]["headers"]["Authorization"] == "Bearer jwt-from-signin"

    monkeypatch.setattr(
        mod.httpx,
        "Client",
        make_client(FakeResponse(200, [{"status": "ERR", "result": "parse failure"}])),
    )
    with pytest.raises(RuntimeError, match="parse failure"):
        mod._http_import_surql(snap, database="sat_graph")

    monkeypatch.setattr(mod.httpx, "Client", make_client(FakeResponse(413, None, text="Payload Too Large")))
    with pytest.raises(RuntimeError, match="413"):
        mod._http_import_surql(snap, database="sat_graph")


def test_bootstrap_http_import_mode_skips_ws_batches_and_records_sha(tmp_path, monkeypatch):
    counts = {tbl: 1 if tbl == "sat_nodes" else 0 for tbl in mod.SAT_TABLES}
    snap = tmp_path / "http_mode.surql.gz"
    with gzip.open(snap, "wt", encoding="utf-8") as out:
        out.write(f"{mod.EXPECTED_ROWS_PREFIX}{json.dumps(counts)}\n")
        out.write("OPTION IMPORT;\n")

    imported = []

    class FakeQuery:
        def __init__(self, result):
            self._result = result

        def execute(self):
            return [self._result]

    class FakeConn:
        def __init__(self):
            self.stored_sha = None
            self.has_rev = False

        def timeout(self, _seconds):
            return nullcontext()

        def query(self, sql, params=None):
            if sql == mod.REVISION_QUERY:
                return FakeQuery(["rev:1"] if self.has_rev else [])
            if "SELECT VALUE snapshot_sha256" in sql:
                return FakeQuery([self.stored_sha] if self.stored_sha else [])
            if "DELETE sat_bootstrap:seed" in sql:
                self.stored_sha = None
                return FakeQuery([])
            if "UPSERT sat_bootstrap:seed" in sql:
                self.stored_sha = params["sha"]
                return FakeQuery([])
            if sql.startswith("REMOVE TABLE") or sql.startswith("DEFINE TABLE"):
                return FakeQuery([])
            if "INSERT " in sql:
                raise AssertionError("HTTP import mode must not run WebSocket INSERT batches")
            for tbl, val in counts.items():
                if f"FROM {tbl}" in sql:
                    return FakeQuery([val])
            raise AssertionError(f"Unexpected SQL: {sql}")

    conn = FakeConn()

    def fake_http_import(
        path,
        *,
        database="sat_graph",
        max_part_bytes=mod.DEFAULT_HTTP_IMPORT_MAX_BYTES,
        progress=False,
        connection=None,
    ):
        imported.append((path, database))
        conn.has_rev = True

    monkeypatch.setattr(mod, "_http_import_surql", fake_http_import)
    assert mod.bootstrap(conn, snap, use_http_import=True) == "restored"
    assert imported == [(snap, "sat_graph")]
    assert conn.stored_sha == mod._snapshot_sha256(snap)


def test_compact_snapshot_prunes_superseded_and_audit_data_and_trims_containers(tmp_path):
    snap = tmp_path / "sat_graph.surql.gz"
    long_container = "TÍTULO I ALIMENTOS\n" + ("texto duplicado " * 100)
    raw_lines = [
        "-- EXPECTED_ROWS: " + json.dumps({t: 0 for t in mod.SAT_TABLES}) + "\n",
        "OPTION IMPORT;\n",
        "-- TABLE: sat_documents\n",
        "DEFINE TABLE sat_documents SCHEMALESS;\n",
        "-- TABLE DATA: sat_documents\n",
        "INSERT [ { id: sat_documents:`1`, markdown: 'huge doc' } ];\n",
        "-- TABLE: sat_nodes\n",
        "DEFINE TABLE sat_nodes SCHEMALESS;\n",
        "-- TABLE DATA: sat_nodes\n",
        "INSERT [ "
        "{ id: sat_nodes:`1`, nid: 'pe:ley:1', kind: 'Resource', payload: '{\"title\":\"Ley 1\"}' }, "
        "{ id: sat_nodes:`2`, nid: 'work:active', kind: 'Work', payload: '{\"resource_id\":\"pe:ley:1\",\"kind\":\"article\"}' }, "
        "{ id: sat_nodes:`3`, nid: 'work:orphan', kind: 'Work', payload: '{\"resource_id\":\"pe:ley:1\",\"kind\":\"article\"}' }, "
        "{ id: sat_nodes:`4`, nid: 'work:tit1', kind: 'Work', payload: '{\"resource_id\":\"pe:ley:1\",\"kind\":\"titulo\"}' }, "
        "{ id: sat_nodes:`5`, nid: 'ctv:old', kind: 'CTV', payload: '{\"work_id\":\"work:orphan\",\"editorial_superseded_by\":\"ctv:new\"}' }, "
        "{ id: sat_nodes:`6`, nid: 'ctv:new', kind: 'CTV', payload: '{\"work_id\":\"work:active\",\"provenance_state\":\"user_attested_snapshot\"}' }, "
        "{ id: sat_nodes:`7`, nid: 'ctv:tit1', kind: 'CTV', payload: '{\"work_id\":\"work:tit1\",\"provenance_state\":\"user_attested_snapshot\"}' }, "
        "{ id: sat_nodes:`8`, nid: 'clv:old', kind: 'CLV', payload: '{\"text\":\"old\"}' }, "
        "{ id: sat_nodes:`9`, nid: 'clv:new', kind: 'CLV', payload: '{\"text\":\"articulo completo vigente\"}' }, "
        "{ id: sat_nodes:`10`, nid: 'clv:tit1', kind: 'CLV', payload: " + repr(json.dumps({"text": long_container})) + " }, "
        "{ id: sat_nodes:`11`, nid: 'rev:old', kind: 'DocumentaryRevision', payload: '{\"editorial_superseded_by\":\"rev:new\",\"markdown\":\"old md\"}' }, "
        "{ id: sat_nodes:`12`, nid: 'rev:new', kind: 'DocumentaryRevision', payload: '{\"review_hash\":\"h1\",\"markdown\":\"active full markdown\"}' }, "
        "{ id: sat_nodes:`13`, nid: 'dc:new', kind: 'DocumentaryComponent', payload: '{\"revision_id\":\"rev:new\"}' }, "
        "{ id: sat_nodes:`15`, nid: 'dc:old', kind: 'DocumentaryComponent', payload: '{\"revision_id\":\"rev:old\"}' }, "
        "{ id: sat_nodes:`14`, nid: 'er:new', kind: 'EditorialReview', payload: '{\"revision_id\":\"rev:new\"}' } "
        "];\n",
        "-- TABLE: sat_edges\n",
        "DEFINE TABLE sat_edges SCHEMALESS;\n",
        "-- TABLE DATA: sat_edges\n",
        "INSERT [ "
        "{ id: sat_edges:`1`, predicate: 'has_text', source: 'ctv:old', target: 'clv:old', payload: '{\"audit\":1}' }, "
        "{ id: sat_edges:`2`, predicate: 'has_text', source: 'ctv:new', target: 'clv:new', payload: '{\"audit\":1}' }, "
        "{ id: sat_edges:`3`, predicate: 'has_text', source: 'ctv:tit1', target: 'clv:tit1', payload: '{\"audit\":1}' }, "
        "{ id: sat_edges:`4`, predicate: 'part_of_revision', source: 'dc:new', target: 'rev:new', payload: '{\"audit\":1}' }, "
        "{ id: sat_edges:`5`, predicate: 'derived_from_documentary', source: 'ctv:new', target: 'dc:new', payload: '{\"audit\":1}' } "
        "];\n",
    ]
    with gzip.open(snap, "wt", encoding="utf-8", newline="\n") as out:
        out.writelines(raw_lines)

    counts = mod.compact_snapshot(snap)
    assert counts["sat_documents"] == 0
    assert counts["sat_nodes"] == 9
    assert counts["sat_edges"] == 3
    assert mod._parse_expected_rows(snap) == counts

    with gzip.open(snap, "rt", encoding="utf-8") as stream:
        body = stream.read()
    for kept in ("pe:ley:1", "work:active", "work:tit1", "ctv:new", "ctv:tit1", "clv:new", "clv:tit1", "rev:new", "dc:new", "derived_from_documentary", "active full markdown", "articulo completo vigente", "TÍTULO I ALIMENTOS"):
        assert kept in body
    for dropped in ("work:orphan", "ctv:old", "clv:old", "rev:old", "dc:old", "er:new", "part_of_revision", "huge doc", '"audit":1'):
        assert dropped not in body
    assert "INSERT [ INSERT [" not in body
    emitted_objs = sum(
        len(mod._extract_insert_objects(line.strip()) or [])
        for line in body.splitlines()
        if line.startswith("INSERT ")
    )
    assert emitted_objs == sum(counts.values())
    assert len(body) < len("".join(raw_lines))





