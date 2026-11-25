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
