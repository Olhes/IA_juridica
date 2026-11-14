"""Transactional SAT storage in a dedicated schema of the app's PostgreSQL."""
from contextlib import contextmanager

from database.postgres_connection import connect_postgres
from .store import SATGraphStore

_LOCK = 6591427708185  # Reserved database-wide lock for SAT editorial writes.


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

    def require_ready(self):
        with self._reader() as db:
            if not db.execute("SELECT 1 FROM sat_nodes WHERE kind='DocumentaryRevision' LIMIT 1").fetchone():
                raise ValueError("El corpus SAT compartido no está cargado en PostgreSQL")

    def candidate_store_available(self):
        with self._reader() as db:
            return db.execute("SELECT to_regclass('sat_parses')").fetchone()[0] is not None
