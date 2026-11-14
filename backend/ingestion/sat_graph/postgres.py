"""Transactional SAT storage in a dedicated schema of the app's PostgreSQL."""
from contextlib import contextmanager

from psycopg import Error as PostgresError

from database.postgres_connection import connect_postgres
from .store import SATGraphStore

_LOCK = 6591427708185  # Reserved database-wide lock for SAT editorial writes.

# Esquemas ya inicializados en este proceso. `runtime_sat_store()` devuelve una
# instancia nueva por request, así que el estado no puede vivir en el objeto.
_SCHEMAS_READY: set[str] = set()


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
