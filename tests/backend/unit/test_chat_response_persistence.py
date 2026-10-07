from datetime import datetime, timedelta, timezone
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

import main
from security import Principal


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "created_at",
    [
        datetime(2026, 10, 6, 9, 30),  # UTC heredado sin zona horaria
        datetime(2026, 10, 6, 9, 30, tzinfo=timezone.utc),
        datetime(2026, 10, 6, 4, 30, tzinfo=timezone(timedelta(hours=-5))),
        datetime(2026, 10, 6, 15, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    ],
)
async def test_conversation_stats_uses_aware_utc_and_accepts_legacy_dates(monkeypatch, created_at):
    service_module = importlib.import_module("modules.chat.services.chat_service")
    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    clock = SimpleNamespace(now=MagicMock(return_value=now), utcnow=MagicMock(return_value=now.replace(tzinfo=None)))
    monkeypatch.setattr(service_module, "datetime", clock)
    service = object.__new__(service_module.ChatService)
    conversation = SimpleNamespace(created_at=created_at, updated_at=created_at)
    service.get_conversation = AsyncMock(return_value=conversation)
    service.get_conversation_messages = AsyncMock(return_value=[
        SimpleNamespace(role="user", tokens_used=3, language="spanish"),
        SimpleNamespace(role="assistant", tokens_used=5, language="spanish"),
    ])

    stats = await service.get_conversation_stats("conversation-id", "owner-id")

    assert stats["duration_hours"] == pytest.approx(2.5)
    assert stats["message_count"] == 2
    assert stats["user_messages"] == stats["assistant_messages"] == 1
    assert stats["total_tokens"] == 8
    assert stats["last_activity"] == created_at
    assert conversation.created_at == created_at  # No mutar datos persistidos.
    clock.now.assert_called_once_with(timezone.utc)
    clock.utcnow.assert_not_called()
    service.get_conversation.assert_awaited_once_with("conversation-id", "owner-id")
    service.get_conversation_messages.assert_awaited_once_with("conversation-id", "owner-id")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_stats_missing_conversation_does_not_read_messages():
    service_module = importlib.import_module("modules.chat.services.chat_service")
    service = object.__new__(service_module.ChatService)
    service.get_conversation = AsyncMock(return_value=None)
    service.get_conversation_messages = AsyncMock()

    assert await service.get_conversation_stats("missing", "owner-id") == {}
    service.get_conversation_messages.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_message_writes_aware_utc_activity_to_legacy_cache(monkeypatch):
    service_module = importlib.import_module("modules.chat.services.chat_service")
    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    clock = SimpleNamespace(now=MagicMock(return_value=now), utcnow=MagicMock(return_value=now.replace(tzinfo=None)))
    monkeypatch.setattr(service_module, "datetime", clock)
    original_created_at = datetime(2026, 10, 6, 9, 30)
    cached = service_module.CachedConversation(
        id="conversation-id", user_id="owner-id", title="Conversation", language="spanish",
        messages=[], metadata={}, created_at=original_created_at, updated_at=original_created_at,
    )
    message_data = service_module.MessageCreate(role="user", content="Hello")
    db_message = {
        "id": "message-id", "conversation_id": "conversation-id", "role": "user", "content": "Hello",
        "language": "spanish", "metadata": {}, "message_type": "text", "tokens_used": 0,
        "model_used": None, "created_at": now,
    }
    service = object.__new__(service_module.ChatService)
    service.db = SimpleNamespace(create_message=AsyncMock(return_value=db_message))
    service.redis = SimpleNamespace(get_cache=AsyncMock(return_value=cached.to_redis_format()), set_cache=AsyncMock())
    service.cache_ttl = {"conversation": 3600}

    message = await service.add_message("conversation-id", "owner-id", message_data)

    assert message.id == "message-id"
    cache_key, stored, ttl = service.redis.set_cache.await_args.args
    assert (cache_key, ttl) == ("conversation:owner-id:conversation-id", 3600)
    restored = service_module.CachedConversation.from_redis_format(stored)
    assert restored.updated_at == now
    assert restored.updated_at.utcoffset() == timedelta(0)
    assert restored.created_at == original_created_at
    assert len(restored.messages) == 1
    clock.now.assert_called_once_with(timezone.utc)
    clock.utcnow.assert_not_called()


def make_request() -> Request:
    return Request(
        {"type": "http", "method": "POST", "path": "/legal-query-stream", "headers": []}
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("payload", "language", "expected"),
    [
        ({"respuesta_espanol": "Spanish response"}, "spanish", "Spanish response"),
        ({"respuesta_espanol": "Spanish fallback"}, "quechua", "Spanish fallback"),
        ({"answer": "Generic fallback"}, "spanish", "Generic fallback"),
    ],
)
def test_extract_response_text_uses_language_safe_fallbacks(
    payload, language, expected
):
    assert main._extract_response_text(payload, language) == expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_persists_validated_spanish_response(monkeypatch):
    optimizer = MagicMock()
    optimizer.get_cached.return_value = None
    optimizer.get_session_stats.return_value = {}

    async def stream_text(*_args, **_kwargs):
        yield "Generated response"

    validator = MagicMock()
    validator.validate = AsyncMock(
        return_value=SimpleNamespace(
            answer_data={"respuesta_espanol": "Validated Spanish response"},
            validation_report=SimpleNamespace(model_dump=lambda: {"status": "passed"}),
            sources=["source"],
            is_reliable=False,
        )
    )
    chat_service = MagicMock()
    chat_service.add_message = AsyncMock()
    chat_service.get_conversation = AsyncMock(return_value=object())
    chat_service.get_conversation_messages = AsyncMock(return_value=[])

    monkeypatch.setattr(main, "chat_service", chat_service)
    monkeypatch.setattr(main.app.state, "llm_optimizer", optimizer, raising=False)
    monkeypatch.setattr(
        main.app.state,
        "rag_engine",
        SimpleNamespace(query_with_rerank=AsyncMock(return_value={"documents": [{"content": "source evidence"}]})),
        raising=False,
    )
    monkeypatch.setattr(
        main.app.state,
        "context_engineer",
        SimpleNamespace(build_legal_prompt=MagicMock(return_value=("prompt", {}))),
        raising=False,
    )
    monkeypatch.setattr(
        main.app.state,
        "legal_agent",
        SimpleNamespace(
            respond_general=AsyncMock(return_value={"respuesta_espanol": "Generated response"}),
            stream_general_text=stream_text,
            build_general_response_from_text=MagicMock(return_value={}),
        ),
        raising=False,
    )
    monkeypatch.setattr(main.app.state, "response_validator", validator, raising=False)

    response = await main.legal_query_stream(
        request=make_request(),
        payload=main.LegalQueryRequest(
            query="Test query", conversation_id="conversation-id"
        ),
        principal=Principal("c5d4a819-f0b1-4775-a374-f280bfc2085c", 9999999999),
    )
    async for _chunk in response.body_iterator:
        pass

    assistant_message = chat_service.add_message.await_args_list[1].kwargs[
        "message_data"
    ]
    assert assistant_message.content == "Validated Spanish response"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cached_stream_persists_response_with_same_extractor(monkeypatch):
    optimizer = MagicMock()
    optimizer.get_cached.return_value = {
        "response": {"respuesta_espanol": "Cached Spanish response"},
        "sources": ["cached-source"],
        "validation": {"status": "passed"},
    }
    chat_service = MagicMock()
    chat_service.add_message = AsyncMock()
    chat_service.get_conversation = AsyncMock(return_value=object())
    chat_service.get_conversation_messages = AsyncMock(return_value=[])

    monkeypatch.setattr(main, "chat_service", chat_service)
    monkeypatch.setattr(main.app.state, "llm_optimizer", optimizer, raising=False)

    monkeypatch.setattr(
        main.app.state,
        "rag_engine",
        SimpleNamespace(get_cache_revision=lambda: "fixture-revision"),
        raising=False,
    )
    response = await main.legal_query_stream(
        request=make_request(),
        payload=main.LegalQueryRequest(
            query="Cached query", conversation_id="conversation-id"
        ),
        principal=Principal("c5d4a819-f0b1-4775-a374-f280bfc2085c", 9999999999),
    )
    async for _chunk in response.body_iterator:
        pass

    assistant_message = chat_service.add_message.await_args_list[1].kwargs[
        "message_data"
    ]
    assert assistant_message.content == "Cached Spanish response"
