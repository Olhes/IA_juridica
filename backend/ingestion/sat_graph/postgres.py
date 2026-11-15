"""Transactional SAT storage in a dedicated schema of the app's PostgreSQL."""
from contextlib import contextmanager
import json
from collections import OrderedDict
from threading import RLock

from psycopg import Error as PostgresError

from database.postgres_connection import connect_postgres
from .store import SATGraphStore

_LOCK = 6591427708185  # Reserved database-wide lock for SAT editorial writes.

# Esquemas ya inicializados en este proceso. `runtime_sat_store()` devuelve una
# instancia nueva por request, así que el estado no puede vivir en el objeto.
_SCHEMAS_READY: set[str] = set()
_CHAT_CACHE = OrderedDict()
_CHAT_CACHE_LOCK = RLock()
_MAX_CHAT_CACHE_ENTRIES = 32


def _cache_put(key, revision, snapshot):
    previous = _CHAT_CACHE.get(key)
    if previous is None or revision >= previous[0]:
        _CHAT_CACHE[key] = (revision, snapshot)
        _CHAT_CACHE.move_to_end(key)
        while len(_CHAT_CACHE) > _MAX_CHAT_CACHE_ENTRIES:
            _CHAT_CACHE.popitem(last=False)


class _PostgresSQL:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        # Only internal SQL uses qmark parameters; user values never enter SQL text.
        return self.connection.execute(query.replace("?", "%s"), params)


class PostgresSATGraphStore(SATGraphStore):
    def __init__(self, connect=connect_postgres, *, candidates=False):
        self.connect = connect
        self.schema = "sat_candidates" if candidates else "sat_graph"
        self.candidates = candidates

    @contextmanager
    def _transaction(self):
        with self.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK,))
            db.execute(f"SET LOCAL search_path TO {self.schema}, pg_catalog")
            yield _PostgresSQL(db)

    @contextmanager
    def _reader(self):
        with self.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            db.execute(f"SET LOCAL search_path TO {self.schema}, pg_catalog")
            yield _PostgresSQL(db)

    def _initialize_schema(self):
        with self._transaction() as db:
            db.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
        self._initialize(seed_catalog=False)
        with self._transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sat_chat_revision (id INTEGER PRIMARY KEY, revision BIGINT NOT NULL)')
            db.execute('INSERT INTO sat_chat_revision VALUES (1, 0) ON CONFLICT (id) DO NOTHING')
            db.execute("CREATE INDEX IF NOT EXISTS sat_work_resource_idx ON sat_nodes ((payload::jsonb ->> 'resource_id')) WHERE kind = 'Work'")
            db.execute("CREATE INDEX IF NOT EXISTS sat_ctv_work_idx ON sat_nodes ((payload::jsonb ->> 'work_id')) WHERE kind = 'CTV'")
            db.execute('''CREATE OR REPLACE FUNCTION sat_bump_chat_revision() RETURNS trigger AS $$
                BEGIN UPDATE sat_chat_revision SET revision = revision + 1 WHERE id = 1; RETURN NULL; END;
                $$ LANGUAGE plpgsql SET search_path FROM CURRENT''')
            for table in ('sat_nodes', 'sat_edges'):
                db.execute(f'DROP TRIGGER IF EXISTS sat_chat_revision_trigger ON {table}')
                db.execute(f'''CREATE TRIGGER sat_chat_revision_trigger AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE
                    ON {table} FOR EACH STATEMENT EXECUTE FUNCTION sat_bump_chat_revision()''')

    def ensure_schema(self):
        """Crea el esquema en el primer uso; idempotente y sin sembrar catálogo.

        Sin esto una base nueva no puede recibir el primer documento: las tablas
        solo las creaba el importador de un snapshot previo. La transacción toma
        el lock de escritura, así que dos llamadas concurrentes se serializan.
        """
        if self.schema not in _SCHEMAS_READY:
            self._initialize_schema()
            _SCHEMAS_READY.add(self.schema)
        return self.schema

    def export(self):
        # El panel de revisión debe poder listar aunque el corpus esté vacío.
        self.ensure_schema()
        return super().export()

    def chat_snapshot(self, resource_id=None):
        """Read only graph types used by chat, with transactionally invalidated cache."""
        self.ensure_schema()
        with self._reader() as db:
            info = db.connection.info
            relation = db.execute("SELECT 'sat_chat_revision'::regclass::oid").fetchone()[0]
            key = (info.host, info.port, info.dbname, info.user, self.schema, relation, resource_id)
            revision = db.execute('SELECT revision FROM sat_chat_revision WHERE id = 1').fetchone()[0]
            with _CHAT_CACHE_LOCK:
                cached = _CHAT_CACHE.get(key)
                if cached is not None and cached[0] == revision:
                    _CHAT_CACHE.move_to_end(key)
                    return cached[1]
            if resource_id:
                sql = """WITH works AS (SELECT id FROM sat_nodes WHERE kind='Work' AND payload::jsonb->>'resource_id' = ?),
                    versions AS (SELECT id FROM sat_nodes WHERE kind='CTV' AND payload::jsonb->>'work_id' IN (SELECT id FROM works)),
                    texts AS (SELECT target AS id FROM sat_edges WHERE predicate='has_text' AND source IN (SELECT id FROM versions)),
                    selected AS (SELECT id FROM works UNION SELECT id FROM versions UNION SELECT id FROM texts UNION SELECT ? AS id)
                    SELECT id,kind,payload FROM sat_nodes WHERE id IN (SELECT id FROM selected) ORDER BY id"""
                rows = db.execute(sql, (resource_id, resource_id)).fetchall()
                selected = [row[0] for row in rows]
                edge_rows = db.connection.execute("SELECT id,source,predicate,target,payload FROM sat_edges WHERE predicate IN ('has_text','contains_version') AND source = ANY(%s) AND target = ANY(%s) ORDER BY id", (selected, selected))
            else:
                rows = db.execute("SELECT id,kind,payload FROM sat_nodes WHERE kind IN ('Resource','Work','CTV','CLV') ORDER BY id")
                edge_rows = db.execute("SELECT id,source,predicate,target,payload FROM sat_edges WHERE predicate IN ('has_text','contains_version') ORDER BY id")
            nodes = [{'id': i, 'type': kind, **json.loads(payload)} for i, kind, payload in rows]
            edges = [{'id': i, 'source': s, 'type': p, 'target': t, 'evidence': json.loads(payload)} for i, s, p, t, payload in edge_rows]
            snapshot = {'engine': 'sat', 'schema_version': 1, 'nodes': nodes, 'edges': edges, 'documents': []}
            with _CHAT_CACHE_LOCK:
                # A slower reader must not replace a newer cached revision.
                _cache_put(key, revision, snapshot)
            return snapshot

    def chat_heading_snapshot(self):
        """Lightweight, revision-bound graph for resolving article headings.

        The CLVs here contain only their first line. This snapshot is used only
        to identify a heading; the full graph is loaded before returning evidence.
        """
        self.ensure_schema()
        with self._reader() as db:
            info = db.connection.info
            relation = db.execute("SELECT 'sat_chat_revision'::regclass::oid").fetchone()[0]
            key = (info.host, info.port, info.dbname, info.user, self.schema, relation, 'headings')
            revision = db.execute('SELECT revision FROM sat_chat_revision WHERE id = 1').fetchone()[0]
            with _CHAT_CACHE_LOCK:
                cached = _CHAT_CACHE.get(key)
                if cached is not None and cached[0] == revision:
                    _CHAT_CACHE.move_to_end(key)
                    return cached[1]
            rows = db.execute("""SELECT w.id,w.payload,c.id,c.payload,t.id,
                t.payload::jsonb - 'text' || jsonb_build_object('text', split_part(t.payload::jsonb->>'text', E'\\n', 1)),
                e.id,e.payload
                FROM sat_nodes w JOIN sat_nodes c ON c.kind='CTV' AND c.payload::jsonb->>'work_id'=w.id
                JOIN sat_edges e ON e.source=c.id AND e.predicate='has_text'
                JOIN sat_nodes t ON t.id=e.target AND t.kind='CLV'
                WHERE w.kind='Work' AND w.payload::jsonb->>'kind'='article'
                ORDER BY w.id,c.id,t.id""").fetchall()
            nodes, edges = {}, []
            for wid, wp, cid, cp, tid, tp, eid, ep in rows:
                nodes[wid] = {'id': wid, 'type': 'Work', **json.loads(wp)}
                nodes[cid] = {'id': cid, 'type': 'CTV', **json.loads(cp)}
                nodes[tid] = {'id': tid, 'type': 'CLV', **tp}
                edges.append({'id': eid, 'source': cid, 'type': 'has_text',
                              'target': tid, 'evidence': json.loads(ep)})
            snapshot = {'engine': 'sat', 'schema_version': 1,
                        'nodes': list(nodes.values()), 'edges': edges, 'documents': [],
                        'chat_revision': revision}
            with _CHAT_CACHE_LOCK:
                _cache_put(key, revision, snapshot)
            return snapshot

    def chat_article_snapshot(self, resource_id, work_id):
        """Load an article, its versioned ancestry and descendants only."""
        self.ensure_schema()
        with self._reader() as db:
            info = db.connection.info
            relation = db.execute("SELECT 'sat_chat_revision'::regclass::oid").fetchone()[0]
            key = (info.host, info.port, info.dbname, info.user, self.schema,
                   relation, 'article', resource_id, work_id)
            revision = db.execute('SELECT revision FROM sat_chat_revision WHERE id = 1').fetchone()[0]
            with _CHAT_CACHE_LOCK:
                cached = _CHAT_CACHE.get(key)
                if cached is not None and cached[0] == revision:
                    _CHAT_CACHE.move_to_end(key)
                    return cached[1]
            rows = db.connection.execute("""WITH RECURSIVE
                seed AS (SELECT c.id FROM sat_nodes c JOIN sat_nodes w ON w.id = c.payload::jsonb->>'work_id'
                         WHERE c.kind='CTV' AND w.id=%s AND w.kind='Work'
                           AND w.payload::jsonb->>'resource_id'=%s),
                descendants(id) AS (SELECT id FROM seed UNION SELECT e.target FROM sat_edges e
                         JOIN descendants d ON e.source=d.id WHERE e.predicate='contains_version'),
                ancestors(id) AS (SELECT id FROM seed UNION SELECT e.source FROM sat_edges e
                         JOIN ancestors a ON e.target=a.id WHERE e.predicate='contains_version'),
                works AS (SELECT DISTINCT payload::jsonb->>'work_id' AS id FROM sat_nodes
                          WHERE kind='CTV' AND id IN (SELECT id FROM descendants UNION SELECT id FROM ancestors)),
                versions AS (SELECT id FROM sat_nodes WHERE kind='CTV' AND payload::jsonb->>'work_id' IN (SELECT id FROM works)),
                texts AS (SELECT target AS id FROM sat_edges WHERE predicate='has_text' AND source IN (SELECT id FROM versions)),
                selected AS (SELECT id FROM works UNION SELECT id FROM versions UNION SELECT id FROM texts UNION SELECT %s::text)
                SELECT id,kind,payload FROM sat_nodes WHERE id IN (SELECT id FROM selected) ORDER BY id""",
                (work_id, resource_id, resource_id)).fetchall()
            ids = [row[0] for row in rows]
            edge_rows = db.connection.execute("""SELECT id,source,predicate,target,payload FROM sat_edges
                WHERE predicate IN ('has_text','contains_version') AND source=ANY(%s) AND target=ANY(%s) ORDER BY id""",
                (ids, ids)).fetchall()
            snapshot = {'engine': 'sat', 'schema_version': 1,
                        'nodes': [{'id': i, 'type': kind, **json.loads(payload)} for i, kind, payload in rows],
                        'edges': [{'id': i, 'source': s, 'type': p, 'target': t, 'evidence': json.loads(payload)}
                                  for i, s, p, t, payload in edge_rows], 'documents': [],
                        'chat_revision': revision}
            with _CHAT_CACHE_LOCK:
                _cache_put(key, revision, snapshot)
            return snapshot

    def stage(self, *args, **kwargs):
        self.ensure_schema()
        return super().stage(*args, **kwargs)

    def review(self, *args, **kwargs):
        self.ensure_schema()
        return super().review(*args, **kwargs)

    def require_ready(self):
        with self._reader() as db:
            if not db.execute("SELECT 1 FROM sat_nodes WHERE kind='DocumentaryRevision' LIMIT 1").fetchone():
                raise ValueError("El corpus SAT compartido no está cargado en PostgreSQL")

    def is_ready(self) -> bool:
        """¿Hay al menos una revisión publicada?

        A diferencia de ``require_ready``, no interrumpe el arranque: un esquema
        todavía inexistente o un corpus vacío son estados transitivos mientras
        alguien publica el primer documento. Un error de conexión tampoco se
        distingue aquí: la sonda de salud ya lo reporta por separado.
        """
        try:
            self.require_ready()
        except (ValueError, PostgresError):
            return False
        return True

    def candidate_store_available(self):
        with self._reader() as db:
            return db.execute("SELECT to_regclass('sat_parses')").fetchone()[0] is not None
