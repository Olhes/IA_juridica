"""Disponibilidad del corpus SAT: distingue "vacío" de "listo" sin tumbar la API."""

import sys

import psycopg
import pytest

from ingestion.sat_graph.postgres import PostgresSATGraphStore


class _Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.row = row

    def execute(self, query, params=()):
        return _Cursor(self.row if "FROM sat_nodes" in query else None)

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False


def store_with(row):
    return PostgresSATGraphStore(connect=lambda: _Connection(row))


def test_empty_corpus_is_not_ready_instead_of_crashing_startup():
    assert store_with(None).is_ready() is False


def test_published_revision_reports_ready():
    assert store_with((1,)).is_ready() is True


def test_unreachable_database_is_not_ready_and_does_not_raise():
    def broken():
        raise psycopg.OperationalError("sin conexión")

    assert PostgresSATGraphStore(connect=broken).is_ready() is False


def test_require_ready_still_refuses_an_empty_corpus():
    """El editor local sí exige corpus: no debe editar sobre una base vacía."""
    with pytest.raises(ValueError):
        store_with(None).require_ready()


class _ReadyCursor:
    """Cursor de un esquema ya inicializado: `sat_meta` siempre reporta versión 1."""

    def fetchone(self):
        return (1,)

    def fetchall(self):
        return [(1,)]


class _RecordingConnection:
    """Conexión falsa que solo anota el SQL ejecutado."""

    def __init__(self, statements):
        self.statements = statements

    def execute(self, query, params=()):
        self.statements.append(query)
        return _ReadyCursor()

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False


def test_ensure_schema_creates_the_schema_once_per_process(monkeypatch):
    module = sys.modules["ingestion.sat_graph.postgres"]
    monkeypatch.setattr(module, "_SCHEMAS_READY", set())
    statements = []
    store = module.PostgresSATGraphStore(connect=lambda: _RecordingConnection(statements))

    store.ensure_schema()
    store.ensure_schema()

    created = [statement for statement in statements if "CREATE SCHEMA" in statement]
    assert len(created) == 1
    assert any("CREATE TABLE IF NOT EXISTS sat_nodes" in statement for statement in statements)
