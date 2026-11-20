"""SurrealDB-backed SAT storage adapter.

Only the storage primitive changes relative to :mod:`ingestion.sat_graph.postgres`:
all legal/business logic stays in :class:`SATGraphStore`.  The executor below
accepts the exact qmark SQL emitted by the base class and translates it to
SurrealQL; anything it cannot translate raises ``NotImplementedError`` instead
of being silently ignored.
"""

from collections import OrderedDict
from contextlib import contextmanager
from datetime import date
import json
import re
from threading import RLock

from surrealdb import RecordID

from database.surreal_connection import connect_surreal, close_surreal, surreal_session
from .store import SATGraphStore, work_id


_TABLE_COLUMNS = {
    "sat_nodes": ("id", "kind", "payload"),
    "sat_edges": ("id", "source", "predicate", "target", "payload"),
    "sat_documents": ("evidence_id", "markdown", "state"),
    "sat_reviews": ("id", "manifest"),
    "sat_parses": ("id", "evidence_id", "artifact"),
    "sat_meta": ("version",),
}

_SAT_TABLES = ("sat_meta", "sat_nodes", "sat_edges", "sat_documents",
               "sat_reviews", "sat_parses", "sat_chat_revision")

_INDEXES = (
    ("sat_node_kind", "sat_nodes", "kind"),
    ("sat_node_work_id", "sat_nodes", "work_id"),
    ("sat_node_resource_id", "sat_nodes", "resource_id"),
    ("sat_node_payload_kind", "sat_nodes", "payload_kind"),
    ("sat_node_provenance_state", "sat_nodes", "provenance_state"),
    ("sat_edges_source_predicate", "sat_edges", "source, predicate"),
    ("sat_edges_target_predicate", "sat_edges", "target, predicate"),
    ("sat_document_evidence", "sat_documents", "evidence_id"),
    ("sat_parse_evidence", "sat_parses", "evidence_id"),
)

# As in the PostgreSQL adapter, runtime_sat_store() returns a fresh instance per
# request, so initialization state and caches must live at module level.
_SCHEMAS_READY: set[str] = set()
_CHAT_CACHE = OrderedDict()
_CHAT_CACHE_LOCK = RLock()
_MAX_CHAT_CACHE_ENTRIES = 32
_REVISION_RID = RecordID("sat_chat_revision", "1")

# export() is revision-bound exactly like the chat snapshots: a write bumps the
# shared revision record, so a stale export is never served after a mutation.
_EXPORT_CACHE = {}
_EXPORT_CACHE_LOCK = RLock()


def _q(conn, sql, params=None):
    """Run a raw SurrealQL query on a pooled connection and return its first result set."""
    result = conn.query(sql, params or {}).execute()
    return result[0] if result else []


def _revision_from_conn(conn):
    """Read the shared chat revision from a raw pooled connection."""
    rows = _q(conn, "SELECT revision FROM $rid LIMIT 1", {"rid": _REVISION_RID})
    return int(rows[0]["revision"]) if rows and rows[0].get("revision") is not None else 0


def _record_id(value):
    """Return the plain string behind a Surreal RecordID (if one was stored)."""
    return getattr(value, "record_id", value)


def _cache_get(key):
    with _CHAT_CACHE_LOCK:
        if key in _CHAT_CACHE:
            _CHAT_CACHE.move_to_end(key)
            return _CHAT_CACHE[key]
    return None


def _cache_put(key, value):
    with _CHAT_CACHE_LOCK:
        _CHAT_CACHE[key] = value
        _CHAT_CACHE.move_to_end(key)
        while len(_CHAT_CACHE) > _MAX_CHAT_CACHE_ENTRIES:
            _CHAT_CACHE.popitem(last=False)


class _Cursor:
    """Minimal DB-API-like cursor consumed by SATGraphStore."""

    def __init__(self, rows):
        self._rows = list(rows)
        self.rowcount = len(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _SurrealSQL:
    """Translate the qmark SQL emitted by SATGraphStore into SurrealQL."""

    def __init__(self, connection):
        self.connection = connection

    # -- low level ---------------------------------------------------------
    def _run(self, sql, params=None):
        result = self.connection.query(sql, params or {}).execute()
        return result[0] if result else []

    def _bump(self):
        self._run("UPDATE $rid SET revision = revision + 1", {"rid": _REVISION_RID})

    @staticmethod
    def _resolve_token(token, params, original):
        if token.startswith("$p"):
            return params[token[1:]]
        if len(token) >= 2 and token[0] == "'" and token[-1] == "'":
            return token[1:-1]
        if re.fullmatch(r"-?\d+", token):
            return int(token)
        if token.upper() == "NULL":
            return None
        raise NotImplementedError(f"Untranslated SAT SQL value {token!r} in: {original}")

    @staticmethod
    def _wheres(fragment):
        """Split a SELECT tail into (where, order_column, limit)."""
        order = None
        limit = None
        match = re.search(r"\bORDER\s+BY\s+([A-Za-z_]\w*)", fragment, re.I)
        if match:
            order = match.group(1)
        match = re.search(r"\bLIMIT\s+(\d+)", fragment, re.I)
        if match:
            limit = int(match.group(1))
        cut = len(fragment)
        for pattern in (r"\bORDER\s+BY\b", r"\bLIMIT\b"):
            match = re.search(pattern, fragment, re.I)
            if match:
                cut = min(cut, match.start())
        where = fragment[:cut].strip()
        if where[:5].upper() == "WHERE":
            where = where[5:].strip()
        return where, order, limit

    @staticmethod
    def _nid(fragment):
        """SAT string ids live in ``nid``; the Surreal ``id`` is a RecordID."""
        return re.sub(r"\bid\b", "nid", fragment, flags=re.I)

    @staticmethod
    def _project(rows, columns, table):
        known = _TABLE_COLUMNS.get(table, ())
        result = []
        for record in rows:
            projected = []
            for column in columns:
                if column == "*":
                    for name in known:
                        projected.append(record.get("nid") if name == "id" else record.get(name))
                elif column == "1":
                    projected.append(1)
                elif column == "id":
                    projected.append(record.get("nid", _record_id(record.get("id"))))
                else:
                    projected.append(record.get(column.split(".")[-1]))
            result.append(tuple(projected))
        return result

    # -- public executor ---------------------------------------------------
    def execute(self, sql, params=()):
        original = sql
        names: list[str] = []

        def replace_qmark(_match):
            names.append(f"p{len(names)}")
            return "$" + names[-1]

        sql = re.sub(r"\?", replace_qmark, sql)
        bound = {name: params[index] for index, name in enumerate(names)}
        upper = sql.strip().upper()

        if upper.startswith(("CREATE TABLE", "CREATE INDEX", "CREATE SCHEMA")):
            return _Cursor([])
        if re.match(r"^SELECT\b", upper) and re.search(r"\bJOIN\b", upper):
            return self._execute_join(sql, bound, original)
        if re.match(r"^SELECT\b", upper):
            return self._execute_select(sql, bound, original)
        if re.match(r"^INSERT\b", upper):
            return self._execute_insert(sql, bound, original)
        if re.match(r"^UPDATE\b", upper):
            return self._execute_update(sql, bound, original)
        if re.match(r"^DELETE\b", upper):
            return self._execute_delete(sql, bound, original)
        raise NotImplementedError(f"Untranslated SAT SQL: {original}")

    # -- statement translators --------------------------------------------
    def _execute_select(self, sql, bound, original):
        match = re.match(
            r"^\s*SELECT\s+(.+?)\s+FROM\s+([A-Za-z_]\w*)\b(.*)$", sql, re.I | re.S
        )
        if not match:
            raise NotImplementedError(f"Untranslated SAT SQL: {original}")
        columns_raw, table, tail = match.groups()
        where, order, limit = self._wheres(tail)
        query = f"SELECT * FROM {table}"
        if where:
            query += f" WHERE {self._nid(where)}"
        if order:
            query += f" ORDER BY {self._nid(order)}"
        if limit is not None:
            query += f" LIMIT {limit}"
        try:
            rows = self._run(query, bound)
        except Exception as exc:
            # Reading a not-yet-defined table is empty in PostgreSQL; mirror it.
            if "does not exist" in str(exc).lower():
                rows = []
            else:
                raise
        return _Cursor(self._project(rows, [c.strip() for c in columns_raw.split(",")], table))

    def _execute_join(self, sql, bound, original):
        # store.py emits exactly:
        # SELECT n.payload FROM sat_edges e JOIN sat_nodes n ON n.id=e.target
        #   WHERE e.source=? AND e.predicate='has_text'
        source_match = re.search(r"\be\.source\s*=\s*(\$p\d+)", sql, re.I)
        predicate_match = re.search(r"\be\.predicate\s*=\s*'([^']*)'", sql, re.I)
        if not source_match or not predicate_match:
            raise NotImplementedError(f"Untranslated SAT JOIN SQL: {original}")
        source = bound[source_match.group(1)[1:]]
        predicate = predicate_match.group(1)
        edges = self._run(
            "SELECT target FROM sat_edges WHERE source = $p0 AND predicate = $p1",
            {"p0": source, "p1": predicate},
        )
        rows = []
        for edge in edges:
            texts = self._run(
                "SELECT payload FROM sat_nodes WHERE nid = $p0 LIMIT 1",
                {"p0": edge.get("target")},
            )
            for text in texts:
                rows.append((text.get("payload"),))
        return _Cursor(rows)

    def _execute_insert(self, sql, bound, original):
        match = re.match(
            r"^\s*INSERT\s+INTO\s+([A-Za-z_]\w*)\s+VALUES\s*\((.*?)\)\s*(.*)$",
            sql, re.I | re.S,
        )
        if not match:
            raise NotImplementedError(f"Untranslated SAT SQL: {original}")
        table, values_raw, tail = match.groups()
        columns = _TABLE_COLUMNS.get(table)
        if columns is None:
            raise NotImplementedError(f"Unknown SAT table in SQL: {original}")
        tokens = [token.strip() for token in values_raw.split(",")]
        if len(tokens) != len(columns):
            raise NotImplementedError(f"Untranslated SAT SQL (value count): {original}")
        values = [self._resolve_token(token, bound, original) for token in tokens]
        record = dict(zip(columns, values))

        conflict = re.search(r"ON\s+CONFLICT\s*\((\w+)\)", tail, re.I)
        conflict_column = conflict.group(1) if conflict else ("version" if table == "sat_meta" else "id")
        key = record.get(conflict_column, values[0])
        rid = RecordID(table, key)

        if table == "sat_meta":
            if self._run(f"SELECT 1 FROM {table} WHERE version = $p0 LIMIT 1", {"p0": key}):
                return _Cursor([])
            self._create(rid, record)
            return _Cursor([])

        record["nid"] = key
        # The RecordID is the authoritative primary key. Migrated rows on
        # sat_documents/sat_reviews/sat_parses carry no `nid` field, so a
        # nid-only check misses them and CREATE then raises AlreadyExistsError;
        # PostgreSQL treats this as INSERT ... ON CONFLICT DO NOTHING.
        exists = self.connection.select(rid).execute() is not None
        if exists:
            if "DO UPDATE" in tail.upper():
                if (
                    table == "sat_nodes"
                    and "payload=excluded.payload" in tail.replace(" ", "")
                    and record.get("kind") == "Resource"
                ):
                    current = self._run(
                        "SELECT kind FROM sat_nodes WHERE nid = $p0 LIMIT 1", {"p0": key}
                    )
                    if current and current[0].get("kind") == "Resource":
                        self._run(
                            "UPDATE sat_nodes SET payload = $p0 WHERE nid = $p1",
                            {"p0": record["payload"], "p1": key},
                        )
                        self._bump()
                    return _Cursor([])
                raise NotImplementedError(f"Untranslated SAT upsert: {original}")
            # DO NOTHING (and the unguarded insert guarded by the caller).
            return _Cursor([])
        self._create(rid, record)
        if table in ("sat_nodes", "sat_edges"):
            self._bump()
        return _Cursor([])

    def _create(self, rid, record):
        # ``id`` is reserved by SurrealDB; the string id is kept in ``nid``.
        stored = {key: value for key, value in record.items() if key != "id"}
        if getattr(rid, "table_name", None) == "sat_nodes":
            # Mirror the migration's derived/indexable payload fields so that
            # rows written at runtime are visible to the indexed fast paths.
            try:
                body = json.loads(stored.get("payload", "{}"))
            except (TypeError, ValueError):
                body = {}
            if isinstance(body, dict):
                derived = {
                    "work_id": body.get("work_id"),
                    "resource_id": body.get("resource_id")
                    or (body.get("id") if stored.get("kind") == "Resource" else None),
                    "payload_kind": body.get("kind"),
                    "provenance_state": body.get("provenance_state"),
                }
                stored.update({k: v for k, v in derived.items() if v is not None})
        params = {"rid": rid}
        assignments = []
        for index, (key, value) in enumerate(stored.items()):
            name = f"v{index}"
            assignments.append(f"{key} = ${name}")
            params[name] = value
        self._run(f"CREATE $rid SET {', '.join(assignments)}", params)

    def _execute_update(self, sql, bound, original):
        match = re.match(
            r"^\s*UPDATE\s+([A-Za-z_]\w*)\s+SET\s+(.*?)\s+WHERE\s+(.*)$", sql, re.I | re.S
        )
        if not match:
            raise NotImplementedError(f"Untranslated SAT SQL: {original}")
        table, assignments_raw, where = match.groups()
        assignments = []
        for part in assignments_raw.split(","):
            assignment = re.match(r"\s*([A-Za-z_]\w*)\s*=\s*(.+?)\s*$", part, re.S)
            if not assignment:
                raise NotImplementedError(f"Untranslated SAT SQL: {original}")
            assignments.append(f"{assignment.group(1)} = {assignment.group(2)}")
        self._run(
            f"UPDATE {table} SET {', '.join(assignments)} WHERE {self._nid(where)}", bound
        )
        if table in ("sat_nodes", "sat_edges"):
            self._bump()
        return _Cursor([])

    def _execute_delete(self, sql, bound, original):
        match = re.match(
            r"^\s*DELETE\s+(?:FROM\s+)?([A-Za-z_]\w*)\s+WHERE\s+(.*)$", sql, re.I | re.S
        )
        if not match:
            raise NotImplementedError(f"Untranslated SAT SQL: {original}")
        table, where = match.groups()
        self._run(f"DELETE FROM {table} WHERE {self._nid(where)}", bound)
        if table in ("sat_nodes", "sat_edges"):
            self._bump()
        return _Cursor([])


class SurrealSATGraphStore(SATGraphStore):
    """SATGraphStore whose storage primitive is SurrealDB instead of PostgreSQL."""

    def __init__(self, connect=None, *, candidates=False):
        # None => borrow a long-lived connection from the shared pool. A custom
        # connect factory is still honoured for tests and isolated databases.
        self.connect = connect
        self.schema = "sat_candidates" if candidates else "sat_graph"
        self.candidates = candidates

    @contextmanager
    def _connection(self):
        if self.connect is None:
            with surreal_session(self.schema) as conn:
                yield conn
        else:
            conn = self.connect(self.schema)
            try:
                yield conn
            finally:
                close_surreal(conn)

    @contextmanager
    def _transaction(self):
        with self._connection() as conn, conn.begin_transaction() as transaction:
            yield _SurrealSQL(transaction)

    @contextmanager
    def _reader(self):
        with self._connection() as conn:
            yield _SurrealSQL(conn)

    # -- schema / readiness ------------------------------------------------
    def _initialize_schema(self):
        with self._transaction() as db:
            for table in _SAT_TABLES:
                db.connection.query(f"DEFINE TABLE IF NOT EXISTS {table} SCHEMALESS", {}).execute()
            for name, table, columns in _INDEXES:
                db.connection.query(
                    f"DEFINE INDEX IF NOT EXISTS {name} ON {table} COLUMNS {columns}", {}
                ).execute()
            revision = db.connection.query(
                "SELECT revision FROM $rid LIMIT 1", {"rid": _REVISION_RID}
            ).execute()
            rows = revision[0] if revision else []
            if not rows:
                db.connection.query(
                    "CREATE $rid SET revision = 0", {"rid": _REVISION_RID}
                ).execute()
            elif rows[0].get("revision") is None:
                db.connection.query(
                    "UPDATE $rid SET revision = 0", {"rid": _REVISION_RID}
                ).execute()
        self._initialize(seed_catalog=False)

    def ensure_schema(self):
        if self.schema not in _SCHEMAS_READY:
            self._initialize_schema()
            _SCHEMAS_READY.add(self.schema)
        return self.schema

    def require_ready(self):
        with self._reader() as db:
            if not db.execute(
                "SELECT 1 FROM sat_nodes WHERE kind='DocumentaryRevision' LIMIT 1"
            ).fetchone():
                raise ValueError("El corpus SAT compartido no está cargado en SurrealDB")

    def is_ready(self) -> bool:
        try:
            self.require_ready()
        except Exception:
            return False
        return True

    def candidate_store_available(self):
        try:
            with self._reader() as db:
                db.execute("SELECT 1 FROM sat_parses LIMIT 1").fetchall()
            return True
        except Exception:
            return False

    # -- cycle detection ---------------------------------------------------
    @staticmethod
    def _reject_cycles(db, predicate):
        rows = db.execute(
            "SELECT source,target FROM sat_edges WHERE predicate=?", (predicate,)
        ).fetchall()
        adjacency: dict[str, set] = {}
        for source, target in rows:
            adjacency.setdefault(source, set()).add(target)
        state: dict[str, int] = {}

        def has_cycle(start):
            stack = [(start, iter(adjacency.get(start, ())))]
            state[start] = 1
            while stack:
                node, children = stack[-1]
                child = next(children, None)
                if child is None:
                    state[node] = 2
                    stack.pop()
                elif state.get(child) == 1:
                    return True
                elif state.get(child, 0) == 0:
                    state[child] = 1
                    stack.append((child, iter(adjacency.get(child, ()))))
            return False

        for node in list(adjacency):
            if state.get(node, 0) == 0 and has_cycle(node):
                raise ValueError("Ciclo en estructura SAT")

    # -- direct, revision-bound export -------------------------------------
    def export(self):
        """Build the exact base-project export shape using projected queries.

        The generic qmark executor materialises whole rows and then projects in
        Python; this path projects on the server and avoids the full-table scan
        overhead of the base implementation.
        """
        self.ensure_schema()
        with self._connection() as conn:
            revision = _revision_from_conn(conn)
            key = (self.schema, revision)
            with _EXPORT_CACHE_LOCK:
                cached = _EXPORT_CACHE.get(key)
            if cached is not None:
                return cached
            node_rows = _q(
                conn, "SELECT nid AS id, kind, payload FROM sat_nodes ORDER BY nid"
            )
            edge_rows = _q(
                conn,
                "SELECT nid AS id, source, predicate, target, payload FROM sat_edges ORDER BY nid",
            )
            document_rows = _q(
                conn, "SELECT evidence_id, state FROM sat_documents ORDER BY evidence_id"
            )

        nodes = [
            {"id": row["id"], "type": row["kind"], **json.loads(row["payload"])}
            for row in node_rows
        ]
        edges = [
            {
                "id": row["id"],
                "source": row["source"],
                "type": row["predicate"],
                "target": row["target"],
                "evidence": json.loads(row["payload"]),
            }
            for row in edge_rows
        ]
        documents = [
            {"evidence_id": row["evidence_id"], "state": row["state"]}
            for row in document_rows
        ]
        nodes.sort(key=lambda node: node["id"])
        edges.sort(key=lambda edge: edge["id"])
        documents.sort(key=lambda doc: doc["evidence_id"])
        result = {
            "engine": "sat",
            "schema_version": 1,
            "nodes": nodes,
            "edges": edges,
            "documents": documents,
            "resource_count": sum(n["type"] == "Resource" for n in nodes),
            "reviewed_version_count": sum(
                n["type"] == "CTV" and n.get("provenance_state") == "reviewed" for n in nodes
            ),
            "attested_snapshot_count": sum(
                n["type"] == "CTV" and n.get("provenance_state") == "user_attested_snapshot"
                for n in nodes
            ),
        }
        with _EXPORT_CACHE_LOCK:
            _EXPORT_CACHE[key] = result
            if len(_EXPORT_CACHE) > _MAX_CHAT_CACHE_ENTRIES:
                _EXPORT_CACHE.clear()
                _EXPORT_CACHE[key] = result
        return result

    def resolve(
        self, resource_id: str, component: str, as_of: str, scope="PE", language="es"
    ) -> dict:
        """Selección exacta, no semántica. Abstenerse fuera de cobertura o idioma."""
        when = date.fromisoformat(as_of).isoformat()
        if when != as_of:
            raise ValueError("Fecha requerida en formato YYYY-MM-DD")
        wid = work_id(resource_id, component)
        with self._reader() as db:
            version_rows = _q(
                db.connection,
                "SELECT nid AS id, payload FROM sat_nodes WHERE kind='CTV' AND work_id=$wid",
                {"wid": wid},
            )
            versions = [(row["id"], json.loads(row["payload"])) for row in version_rows]
            active = [
                (identity, v)
                for identity, v in versions
                if v["work_id"] == wid
                and not v.get("editorial_superseded_by")
                and v["scope"] == scope
                and ((v.get("provenance_state") == "user_attested_snapshot" and v.get("snapshot_as_of") == when)
                     or (v.get("provenance_state") == "reviewed" and v["valid_from"] <= when
                         and (v["valid_to"] is None or when < v["valid_to"])))
            ]
            if len(active) != 1:
                return {
                    "state": "abstain",
                    "reason": "missing_or_ambiguous_version",
                    "work_id": wid,
                }
            identity, version = active[0]
            if when > version["checked_through"]:
                return {
                    "state": "abstain",
                    "reason": "outside_reviewed_coverage",
                    "work_id": wid,
                }
            texts = [
                json.loads(payload)
                for (payload,) in db.execute(
                    "SELECT n.payload FROM sat_edges e JOIN sat_nodes n ON n.id=e.target WHERE e.source=? AND e.predicate='has_text'",
                    (identity,),
                )
            ]
            texts = [text for text in texts if text["language"] == language]
            if len(texts) != 1:
                return {
                    "state": "abstain",
                    "reason": "missing_or_ambiguous_language",
                    "work_id": wid,
                }
            return {
                "state": "resolved",
                "version_id": identity,
                "version": version,
                "text": texts[0],
                "as_of": when,
            }

    # -- revision-bound chat snapshots -------------------------------------
    @staticmethod
    def _revision(db):
        return _revision_from_conn(db.connection)

    @staticmethod
    def _graph_rows(db):
        nodes = [
            (identity, kind, json.loads(payload))
            for identity, kind, payload in db.execute(
                "SELECT id,kind,payload FROM sat_nodes ORDER BY id"
            ).fetchall()
        ]
        edges = [
            (identity, source, predicate, target, json.loads(payload))
            for identity, source, predicate, target, payload in db.execute(
                "SELECT * FROM sat_edges ORDER BY id"
            ).fetchall()
        ]
        return nodes, edges

    @staticmethod
    def _edge_dicts(edges):
        return [
            {"id": i, "source": s, "type": p, "target": t, "evidence": evidence}
            for i, s, p, t, evidence in edges
        ]

    def chat_snapshot(self, resource_id=None):
        self.ensure_schema()
        with self._connection() as conn:
            revision = _revision_from_conn(conn)
            key = (self.schema, "chat", (resource_id,), revision)
            cached = _cache_get(key)
            if cached is not None:
                return cached
            if resource_id:
                work_ids = [
                    row["id"]
                    for row in _q(
                        conn,
                        "SELECT nid AS id FROM sat_nodes WHERE kind='Work' AND resource_id=$rid",
                        {"rid": resource_id},
                    )
                ]
                version_ids = (
                    [
                        row["id"]
                        for row in _q(
                            conn,
                            "SELECT nid AS id FROM sat_nodes WHERE kind='CTV' AND work_id IN $wids",
                            {"wids": work_ids},
                        )
                    ]
                    if work_ids
                    else []
                )
                text_ids = (
                    [
                        row["target"]
                        for row in _q(
                            conn,
                            "SELECT target FROM sat_edges WHERE predicate='has_text' AND source IN $vids",
                            {"vids": version_ids},
                        )
                    ]
                    if version_ids
                    else []
                )
                selected = list(set(work_ids) | set(version_ids) | set(text_ids) | {resource_id})
                node_rows = _q(
                    conn,
                    "SELECT nid AS id, kind, payload FROM sat_nodes WHERE nid IN $sel ORDER BY nid",
                    {"sel": selected},
                )
                edge_rows = _q(
                    conn,
                    "SELECT nid AS id, source, predicate, target, payload FROM sat_edges "
                    "WHERE predicate IN ['has_text','contains_version'] AND source IN $sel "
                    "AND target IN $sel ORDER BY nid",
                    {"sel": selected},
                )
            else:
                node_rows = _q(
                    conn,
                    "SELECT nid AS id, kind, payload FROM sat_nodes "
                    "WHERE kind IN ['Resource','Work','CTV','CLV'] ORDER BY nid",
                )
                edge_rows = _q(
                    conn,
                    "SELECT nid AS id, source, predicate, target, payload FROM sat_edges "
                    "WHERE predicate IN ['has_text','contains_version'] ORDER BY nid",
                )

        nodes = [
            {"id": row["id"], "type": row["kind"], **json.loads(row["payload"])}
            for row in node_rows
        ]
        edges = [
            {
                "id": row["id"],
                "source": row["source"],
                "type": row["predicate"],
                "target": row["target"],
                "evidence": json.loads(row["payload"]),
            }
            for row in edge_rows
        ]
        nodes.sort(key=lambda node: node["id"])
        edges.sort(key=lambda edge: edge["id"])
        snapshot = {
            "engine": "sat",
            "schema_version": 1,
            "nodes": nodes,
            "edges": edges,
            "documents": [],
        }
        _cache_put(key, snapshot)
        return snapshot

    def chat_heading_snapshot(self):
        self.ensure_schema()
        with self._connection() as conn:
            revision = _revision_from_conn(conn)
            key = (self.schema, "heading", (), revision)
            cached = _cache_get(key)
            if cached is not None:
                return cached

            article_rows = _q(
                conn,
                "SELECT nid AS id, payload FROM sat_nodes WHERE kind='Work' AND payload_kind='article'",
            )
            article_works = {row["id"]: json.loads(row["payload"]) for row in article_rows}
            work_ids = list(article_works)
            version_rows = (
                _q(
                    conn,
                    "SELECT nid AS id, payload FROM sat_nodes WHERE kind='CTV' AND work_id IN $wids",
                    {"wids": work_ids},
                )
                if work_ids
                else []
            )
            versions = {row["id"]: json.loads(row["payload"]) for row in version_rows}
            version_ids = list(versions)

            edge_rows = (
                _q(
                    conn,
                    "SELECT nid AS id, source, target, payload FROM sat_edges "
                    "WHERE predicate='has_text' AND source IN $vids",
                    {"vids": version_ids},
                )
                if version_ids
                else []
            )
            text_ids = list({row["target"] for row in edge_rows})
            text_rows = (
                _q(
                    conn,
                    "SELECT nid AS id, payload FROM sat_nodes WHERE kind='CLV' AND nid IN $tids",
                    {"tids": text_ids},
                )
                if text_ids
                else []
            )
            texts = {row["id"]: json.loads(row["payload"]) for row in text_rows}

            # Postgres emits ORDER BY w.id, c.id, t.id. Reproduce that order so
            # the snapshot is byte-equivalent, not just set-equivalent.
            rows: list[tuple] = []
            for row in edge_rows:
                source, target = row["source"], row["target"]
                if source not in versions or target not in texts:
                    continue
                wid = versions[source].get("work_id")
                if wid not in article_works:
                    continue
                truncated = dict(texts[target])
                text = truncated.get("text")
                truncated["text"] = text.split("\n")[0] if isinstance(text, str) else text
                rows.append((wid, article_works[wid], source, versions[source],
                             target, truncated, row["id"], json.loads(row["payload"])))
            rows.sort(key=lambda r: (r[0], r[2], r[4]))

            by_id: dict[str, dict] = {}
            edge_dicts: list[dict] = []
            for wid, wp, cid, cp, tid, tp, eid, ep in rows:
                by_id[wid] = {"id": wid, "type": "Work", **wp}
                by_id[cid] = {"id": cid, "type": "CTV", **cp}
                by_id[tid] = {"id": tid, "type": "CLV", **tp}
                edge_dicts.append(
                    {"id": eid, "source": cid, "type": "has_text",
                     "target": tid, "evidence": ep}
                )
            snapshot = {
                "engine": "sat",
                "schema_version": 1,
                "nodes": list(by_id.values()),
                "edges": edge_dicts,
                "documents": [],
                "chat_revision": revision,
            }
            _cache_put(key, snapshot)
            return snapshot

    def chat_article_snapshot(self, resource_id, work_id):
        self.ensure_schema()
        with self._connection() as conn:
            revision = _revision_from_conn(conn)
            key = (self.schema, "article", (resource_id, work_id), revision)
            cached = _cache_get(key)
            if cached is not None:
                return cached

            work_rows = _q(
                conn,
                "SELECT nid AS id, kind, payload FROM sat_nodes WHERE nid=$wid LIMIT 1",
                {"wid": work_id},
            )
            work = (
                (work_rows[0]["kind"], json.loads(work_rows[0]["payload"]))
                if work_rows
                else None
            )
            seeds = set()
            if work and work[0] == "Work" and work[1].get("resource_id") == resource_id:
                seeds = {
                    row["id"]
                    for row in _q(
                        conn,
                        "SELECT nid AS id FROM sat_nodes WHERE kind='CTV' AND work_id=$wid",
                        {"wid": work_id},
                    )
                }

            version_edges = _q(
                conn, "SELECT source, target FROM sat_edges WHERE predicate='contains_version'"
            )
            forward, backward = {}, {}
            for row in version_edges:
                forward.setdefault(row["source"], set()).add(row["target"])
                backward.setdefault(row["target"], set()).add(row["source"])

            def closure(starts, adjacency):
                seen, stack = set(), list(starts)
                while stack:
                    node = stack.pop()
                    if node in seen:
                        continue
                    seen.add(node)
                    stack.extend(adjacency.get(node, ()))
                return seen

            related = closure(seeds, forward) | closure(seeds, backward)
            related_ids = list(related)
            related_ctvs = (
                _q(
                    conn,
                    "SELECT nid AS id, payload FROM sat_nodes WHERE kind='CTV' AND nid IN $ids",
                    {"ids": related_ids},
                )
                if related_ids
                else []
            )
            works = set()
            for row in related_ctvs:
                payload = json.loads(row["payload"])
                if payload.get("work_id"):
                    works.add(payload["work_id"])

            work_list = list(works)
            version_rows = (
                _q(
                    conn,
                    "SELECT nid AS id FROM sat_nodes WHERE kind='CTV' AND work_id IN $wids",
                    {"wids": work_list},
                )
                if work_list
                else []
            )
            versions = {row["id"] for row in version_rows}
            text_rows = (
                _q(
                    conn,
                    "SELECT target FROM sat_edges WHERE predicate='has_text' AND source IN $vids",
                    {"vids": list(versions)},
                )
                if versions
                else []
            )
            texts = {row["target"] for row in text_rows}
            selected = list(works | versions | texts | {resource_id})
            node_rows = _q(
                conn,
                "SELECT nid AS id, kind, payload FROM sat_nodes WHERE nid IN $sel ORDER BY nid",
                {"sel": selected},
            )
            edge_rows = _q(
                conn,
                "SELECT nid AS id, source, predicate, target, payload FROM sat_edges "
                "WHERE predicate IN ['has_text','contains_version'] AND source IN $sel "
                "AND target IN $sel ORDER BY nid",
                {"sel": selected},
            )

        nodes = [
            {"id": row["id"], "type": row["kind"], **json.loads(row["payload"])}
            for row in node_rows
        ]
        edges = [
            {
                "id": row["id"],
                "source": row["source"],
                "type": row["predicate"],
                "target": row["target"],
                "evidence": json.loads(row["payload"]),
            }
            for row in edge_rows
        ]
        nodes.sort(key=lambda node: node["id"])
        edges.sort(key=lambda edge: edge["id"])
        snapshot = {
            "engine": "sat",
            "schema_version": 1,
            "nodes": nodes,
            "edges": edges,
            "documents": [],
            "chat_revision": revision,
        }
        _cache_put(key, snapshot)
        return snapshot
