"""In-process fixture; the running application only uses PostgreSQL."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3

from ingestion.sat_graph.store import SATGraphStore


class FixtureSATStore(SATGraphStore):
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _transaction(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db

    @contextmanager
    def _reader(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.execute("BEGIN")
            with db:
                yield db
