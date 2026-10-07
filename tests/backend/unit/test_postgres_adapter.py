"""Contrato SQL del adaptador real con cursor simulado, sin servidor PostgreSQL."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from database.postgres_adapter_final import PostgreSQLAdapter, DatabaseUnavailableError
from models.chat_models import ConversationUpdate

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


def adapter(row=None, rows=None):
    db = PostgreSQLAdapter()
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = row
    cursor.fetchall.return_value = rows or []
    db.conn = connection
    return db, connection, cursor


@pytest.mark.asyncio
async def test_conversation_read_scopes_owner_and_normalizes_nullable_fields():
    db, _, cursor = adapter(("c1", "owner", "Prueba", "spanish", NOW, None, None, True))
    result = await db.get_conversation("c1", "owner")
    assert result["metadata"] == {}
    assert result["updated_at"] == NOW.isoformat()
    sql, params = cursor.execute.call_args.args
    assert "user_id = %s" in sql
    assert params == ("c1", "owner")
    cursor.fetchone.return_value = None
    assert await db.get_conversation("foreign", "owner") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "foreign", "failure"])
async def test_message_insert_scopes_owner_serializes_dates_and_rolls_back(outcome):
    db, connection, cursor = adapter(("m1", "c1", "Prueba", "user", None, NOW))
    if outcome == "foreign":
        cursor.fetchone.return_value = None
    elif outcome == "failure":
        cursor.execute.side_effect = RuntimeError("synthetic database failure")
    if outcome == "failure":
        with pytest.raises(RuntimeError, match="synthetic"):
            await db.create_message("c1", "owner", "Prueba", "user")
    else:
        result = await db.create_message(
            "c1", "owner", "Prueba", "user", {"dates": [NOW], "nested": {"value": 1}}
        )
        sql, params = cursor.execute.call_args.args
        assert "c.user_id = %s" in sql
        assert params[-2:] == ("c1", "owner")
        assert json.loads(params[2]) == {
            "dates": [NOW.isoformat()],
            "nested": {"value": 1},
        }
        if outcome == "success":
            assert result["created_at"] == NOW.isoformat()
            assert result["metadata"] == {}
            connection.commit.assert_called_once()
        else:
            assert result is None
    if outcome != "success":
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()


@pytest.mark.asyncio
async def test_message_and_conversation_listing_use_owner_and_pagination():
    db, _, cursor = adapter(rows=[("m1", "c1", "Prueba", "assistant", None, NOW)])
    messages = await db.get_conversation_messages("c1", "owner")
    assert messages[0]["metadata"] == {}
    assert cursor.execute.call_args.args[1] == ("c1", "owner")
    assert "c.user_id = %s" in cursor.execute.call_args.args[0]
    cursor.fetchall.return_value = [("c1", "Prueba", "quechua", NOW, None, None)]
    conversations = await db.list_conversations("owner", limit=7, offset=2)
    assert cursor.execute.call_args.args[1] == ("owner", 7, 2)
    assert conversations[0]["message_count"] == 0
    assert conversations[0]["updated_at"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("found", [False, True])
async def test_conversation_update_and_delete_preserve_owner_and_return_result(found):
    db, connection, cursor = adapter(("c1",) if found else None)
    assert await db.update_conversation("c1", "owner", {}) is False
    cursor.execute.assert_not_called()
    payload = ConversationUpdate(
        title="Nuevo", metadata={"date": [NOW]}, is_active=False
    )
    assert await db.update_conversation("c1", "owner", payload) is found
    sql, params = cursor.execute.call_args.args
    assert "WHERE id = %s AND user_id = %s" in sql
    assert params[-2:] == ["c1", "owner"]
    assert json.loads(params[1]) == {"date": [NOW.isoformat()]}
    assert params[2] is False
    assert await db.delete_conversation("c1", "owner") is found
    assert cursor.execute.call_args.args[1] == ("c1", "owner")
    assert connection.commit.call_count == 2


@pytest.mark.asyncio
async def test_conversation_update_rolls_back_database_error():
    db, connection, cursor = adapter()
    cursor.execute.side_effect = RuntimeError("synthetic")
    with pytest.raises(RuntimeError, match="synthetic"):
        await db.update_conversation("c1", "owner", {"title": "Nuevo"})
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


@pytest.mark.asyncio
async def test_disconnected_adapter_never_returns_fabricated_conversations():
    db = PostgreSQLAdapter()
    db.conn = None
    assert await db.get_conversation("c1", "owner") is None
    assert await db.get_conversation_messages("c1", "owner") == []
    assert await db.list_conversations("owner") == []
    assert await db.update_conversation("c1", "owner", {}) is False
    assert await db.delete_conversation("c1", "owner") is False
    with pytest.raises(DatabaseUnavailableError):
        await db.create_conversation("owner")
