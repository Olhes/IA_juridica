"""Unit tests for native async SurrealAdapter query, index, cascade, and loop contracts."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from surrealdb import RecordID

from database import surreal_adapter as module
from database.errors import DatabaseUnavailableError
from database.surreal_adapter import AUTH_DB, CONVERSATIONS_DB, SurrealAdapter


class FakeAsyncConnection:
    def __init__(self, handler=None):
        self.queries = []
        self.closed = False
        self.handler = handler or (lambda sql, params: [[]])

    async def query(self, sql, params=None):
        self.queries.append((sql, dict(params or {})))
        return self.handler(sql, params or {})

    async def version(self):
        return "surrealdb-4.0.1"

    async def close(self):
        self.closed = True


def _connected_adapter(auth_handler=None, conv_handler=None):
    adapter = SurrealAdapter()
    adapter.conn = FakeAsyncConnection(auth_handler)
    adapter.conv_conn = FakeAsyncConnection(conv_handler)
    adapter._loop = asyncio.get_running_loop()
    adapter._indexes_ready = True
    return adapter


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_creates_indexes_once_and_rebinds_across_loops(monkeypatch):
    opened = []

    async def fake_open(database):
        conn = FakeAsyncConnection()
        opened.append((database, conn))
        return conn

    monkeypatch.setattr(module, "_open_connection", fake_open)

    adapter = SurrealAdapter()
    await adapter.initialize()
    await adapter.initialize()  # Idempotent on same loop.

    assert [db for db, _ in opened] == [AUTH_DB, CONVERSATIONS_DB]
    assert adapter.is_connected()
    auth_sql = opened[0][1].queries[0][0]
    conv_sql = opened[1][1].queries[0][0]
    assert "idx_users_email" in auth_sql and "idx_user_roles_user" in auth_sql
    assert "idx_conversations_user_updated" in conv_sql
    assert "idx_messages_conversation_created" in conv_sql

    # Simulating a different event loop closes stale clients and rebinds cleanly.
    adapter._loop = object()
    await adapter.initialize()
    assert len(opened) == 4
    assert opened[0][1].closed and opened[1][1].closed
    await adapter.close()
    assert not adapter.is_connected()
    assert opened[2][1].closed and opened[3][1].closed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_conversations_paginates_and_groups_counts_in_surrealql():
    def handle_conv(sql, params):
        if "FROM conversations" in sql:
            assert "LIMIT $limit" in sql
            assert params == {"p0": "u-1", "limit": 10}
            return [[
                {
                    "id": RecordID("conversations", "c-1"),
                    "user_id": "u-1",
                    "title": "Alimentos",
                    "language": "spanish",
                    "created_at": "2026-11-24T10:00:00+00:00",
                    "updated_at": "2026-11-24T11:00:00+00:00",
                    "metadata": {},
                    "is_active": True,
                }
            ]]
        if "GROUP BY conversation_id" in sql:
            assert "INSIDE $ids" in sql
            assert params == {"ids": ["c-1"]}
            return [[{"conversation_id": "c-1", "total": 4}]]
        raise AssertionError(f"Unexpected SQL: {sql}")

    adapter = _connected_adapter(conv_handler=handle_conv)
    conversations = await adapter.get_user_conversations("u-1", limit=10)

    assert len(conversations) == 1
    assert conversations[0]["id"] == "c-1"
    assert conversations[0]["message_count"] == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_message_updates_conversation_timestamp_in_transaction():
    def handle_conv(sql, params):
        if sql.startswith("SELECT * FROM conversations"):
            return [[{"id": RecordID("conversations", "c-1"), "user_id": "u-1"}]]
        if sql.startswith("BEGIN TRANSACTION;"):
            assert "CREATE $rid SET" in sql
            assert "UPDATE $conv_rid SET updated_at = $ts" in sql
            assert params["cid"] == "c-1"
            assert params["conv_rid"] == RecordID("conversations", "c-1")
            return [[]]
        raise AssertionError(f"Unexpected SQL: {sql}")

    adapter = _connected_adapter(conv_handler=handle_conv)
    msg = await adapter.create_message("c-1", "u-1", "Respuesta", "assistant", {"k": 1})

    assert msg is not None
    assert msg["conversation_id"] == "c-1"
    assert msg["metadata"] == {"k": 1}
    assert len(adapter.conv_conn.queries) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_conversation_cascades_messages_atomically():
    def handle_conv(sql, params):
        if sql.startswith("SELECT * FROM conversations"):
            return [[{"id": RecordID("conversations", "c-1"), "user_id": "u-1"}]]
        if sql.startswith("BEGIN TRANSACTION;"):
            assert "DELETE messages WHERE conversation_id = $cid;" in sql
            assert "DELETE $rid;" in sql
            assert params == {"rid": RecordID("conversations", "c-1"), "cid": "c-1"}
            return [[]]
        raise AssertionError(f"Unexpected SQL: {sql}")

    adapter = _connected_adapter(conv_handler=handle_conv)
    assert await adapter.delete_conversation("c-1", "u-1") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_conversation_enforces_owner_in_single_query():
    def handle_conv(sql, params):
        assert "UPDATE $rid SET" in sql
        assert "WHERE user_id = $owner RETURN AFTER" in sql
        if params["owner"] == "u-1":
            return [[{"id": RecordID("conversations", "c-1"), "title": "Nuevo"}]]
        return [[]]

    adapter = _connected_adapter(conv_handler=handle_conv)
    assert await adapter.update_conversation("c-1", "u-1", {"title": "Nuevo"}) is True
    assert await adapter.update_conversation("c-1", "intruder", {"title": "Hack"}) is False
    assert len(adapter.conv_conn.queries) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_conversations_filters_messages_in_surrealql():
    def handle_conv(sql, params):
        if "FROM conversations" in sql:
            return [[
                {
                    "id": RecordID("conversations", "c-title"),
                    "user_id": "u-1",
                    "title": "Consulta REDAM",
                    "language": "spanish",
                    "created_at": "2026-11-24T10:00:00+00:00",
                    "updated_at": "2026-11-24T12:00:00+00:00",
                },
                {
                    "id": RecordID("conversations", "c-body"),
                    "user_id": "u-1",
                    "title": "Otra consulta",
                    "language": "spanish",
                    "created_at": "2026-11-24T09:00:00+00:00",
                    "updated_at": "2026-11-24T11:00:00+00:00",
                },
            ]]
        if "FROM messages" in sql:
            assert "INSIDE $ids" in sql
            assert "string::lowercase(content) CONTAINS $needle" in sql
            assert params == {"ids": ["c-body"], "needle": "redam"}
            return [[{"conversation_id": "c-body"}]]
        raise AssertionError(f"Unexpected SQL: {sql}")

    adapter = _connected_adapter(conv_handler=handle_conv)
    found = await adapter.search_conversations("u-1", "REDAM", limit=5)

    assert [row["id"] for row in found] == ["c-title", "c-body"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_roles_and_permissions_filter_with_inside_instead_of_full_table_scans():
    def handle_auth(sql, params):
        if "FROM user_roles" in sql:
            return [[{"user_id": "u-1", "role_id": "r-admin", "assigned_at": "2026-11-24T00:00:00Z"}]]
        if "FROM roles WHERE id INSIDE $rids" in sql:
            assert params == {"rids": [RecordID("roles", "r-admin")]}
            return [[{"id": RecordID("roles", "r-admin"), "name": "admin", "description": "Admin"}]]
        if "FROM role_permissions WHERE role_id INSIDE $rids" in sql:
            assert params == {"rids": ["r-admin"]}
            return [[{"permission_id": "p-review"}]]
        if "FROM permissions WHERE id INSIDE $pids" in sql:
            assert params == {"pids": [RecordID("permissions", "p-review")]}
            return [[{"name": "quality:admin"}]]
        raise AssertionError(f"Unexpected full-table scan or query: {sql}")

    adapter = _connected_adapter(auth_handler=handle_auth)
    roles = await adapter.get_user_roles("u-1")
    perms = await adapter.get_user_permissions("u-1")

    assert roles[0]["name"] == "admin"
    assert perms == ["quality:admin"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unavailable_database_raises_domain_error(monkeypatch):
    adapter = SurrealAdapter()
    monkeypatch.setattr(adapter, "initialize", AsyncMock())
    with pytest.raises(DatabaseUnavailableError):
        await adapter.get_user_conversations("u-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_check_reports_unhealthy_when_version_raises_or_loop_mismatch():
    adapter = _connected_adapter()

    async def broken_version():
        raise ConnectionError("socket closed")

    adapter.conn.version = broken_version
    assert (await adapter.health_check())["status"] == "unhealthy"

    # Wrong event loop also reports unhealthy instead of probing a stale socket.
    adapter2 = _connected_adapter()
    adapter2._loop = object()
    assert (await adapter2.health_check())["status"] == "unhealthy"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_conversations_returns_newest_body_match_ahead_of_older_title_match():
    def handle_conv(sql, params):
        if "FROM conversations" in sql:
            return [[
                {
                    "id": RecordID("conversations", "c-newest-body"),
                    "user_id": "u-1",
                    "title": "Consulta general",
                    "language": "spanish",
                    "created_at": "2026-11-24T12:00:00+00:00",
                    "updated_at": "2026-11-24T13:00:00+00:00",
                },
                {
                    "id": RecordID("conversations", "c-older-title"),
                    "user_id": "u-1",
                    "title": "Consulta REDAM",
                    "language": "spanish",
                    "created_at": "2026-11-24T10:00:00+00:00",
                    "updated_at": "2026-11-24T11:00:00+00:00",
                },
                {
                    "id": RecordID("conversations", "c-oldest-ignored"),
                    "user_id": "u-1",
                    "title": "Sin coincidencia",
                    "language": "spanish",
                    "created_at": "2026-11-24T08:00:00+00:00",
                    "updated_at": "2026-11-24T09:00:00+00:00",
                },
            ]]
        if "FROM messages" in sql:
            assert params == {"ids": ["c-newest-body"], "needle": "redam"}
            return [[{"conversation_id": "c-newest-body"}]]
        raise AssertionError(f"Unexpected SQL: {sql}")

    adapter = _connected_adapter(conv_handler=handle_conv)
    found = await adapter.search_conversations("u-1", "redam", limit=1)
    assert [row["id"] for row in found] == ["c-newest-body"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_by_id_returns_none_for_empty_id():
    adapter = _connected_adapter()
    assert await adapter.get_user_by_id(None) is None
    assert await adapter.get_user_by_id("") is None
    assert adapter.conn.queries == []
