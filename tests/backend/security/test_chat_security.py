from contextlib import contextmanager
import logging
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import bcrypt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import main
from config.settings import settings
from models.chat_models import (
    CachedConversation,
    ConversationResponse,
    ConversationUpdate,
)
from modules.auth.services.security import AuthService
from modules.chat.services.chat_service import ChatService
from security import Principal, issue_session, set_session_cookie, verify_session


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    main.limiter.reset()
    yield
    main.limiter.reset()


@contextmanager
def _offline_client(client_addr=None):
    kwargs = {"client": client_addr} if client_addr is not None else {}
    client = TestClient(main.app, **kwargs)  # No lifespan: no Redis/Postgres/LLM startup.
    try:
        yield client
    finally:
        client.close()


def test_bcrypt_login_verification_accepts_an_existing_hash_and_fails_closed():
    password = "clave sintética"
    stored = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=4, prefix=b"2a")).decode("ascii")
    assert AuthService.verify_password(password, stored)
    assert not AuthService.verify_password("otra clave", stored)
    assert not AuthService.verify_password("é" * 37, stored)
    assert not AuthService.verify_password(password, "no-es-bcrypt")


def test_signed_sessions_are_distinct_expire_and_reject_tampering():
    token_a, principal_a = issue_session(now=1_000)
    token_b, principal_b = issue_session(now=1_000)

    assert principal_a.id != principal_b.id
    assert verify_session(token_a, now=1_001) == principal_a
    assert verify_session(token_a + "tampered", now=1_001) is None
    assert verify_session(token_a, now=principal_a.expires_at) is None


def test_session_cookie_is_http_only_and_secure_in_production(monkeypatch):
    token, principal = issue_session(now=1_000)
    response = main.Response()
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    set_session_cookie(response, token, principal)

    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "Max-Age=" in cookie
    assert "SameSite=lax" in cookie


def test_production_configuration_rejects_insecure_defaults(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ANONYMOUS_SESSION_SECRET", "short")
    monkeypatch.setattr(settings, "RATE_LIMIT_STORAGE_URI", "memory://")
    result = settings.validate_configuration()
    assert not result["valid"]
    assert any("ANONYMOUS_SESSION_SECRET" in issue for issue in result["issues"])
    assert any("RATE_LIMIT_STORAGE_URI" in issue for issue in result["issues"])


@pytest.mark.asyncio
async def test_cache_hit_and_database_fallback_both_enforce_owner():
    service = ChatService()
    owner = str(uuid.uuid4())
    attacker = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    cached = CachedConversation(
        id=conversation_id,
        user_id=owner,
        title="Private",
        language="spanish",
        messages=[],
        metadata={},
        created_at=main.datetime.now(),
        updated_at=main.datetime.now(),
    )
    service.redis = SimpleNamespace(
        get_cache=AsyncMock(return_value=cached.to_redis_format())
    )
    service.db = SimpleNamespace(get_conversation=AsyncMock(return_value=None))

    assert await service.get_conversation(conversation_id, attacker) is None
    service.redis.get_cache.assert_awaited_once_with(
        f"conversation:{attacker}:{conversation_id}"
    )
    service.db.get_conversation.assert_awaited_once_with(conversation_id, attacker)

    service.redis.get_cache = AsyncMock(return_value=None)
    service.db.get_conversation.reset_mock()
    assert await service.get_conversation(conversation_id, attacker) is None
    service.db.get_conversation.assert_awaited_once_with(conversation_id, attacker)


@pytest.mark.asyncio
async def test_update_delete_stats_and_messages_forward_owner():
    service = ChatService()
    owner = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    service.redis = SimpleNamespace(
        delete_cache=AsyncMock(return_value=True),
        get_cache=AsyncMock(return_value=None),
    )
    service.db = SimpleNamespace(
        update_conversation=AsyncMock(return_value=False),
        delete_conversation=AsyncMock(return_value=False),
        get_conversation_messages=AsyncMock(return_value=[]),
    )

    assert (
        await service.update_conversation(
            conversation_id, owner, ConversationUpdate(title="New")
        )
        is None
    )
    assert not await service.delete_conversation(conversation_id, owner)
    assert await service.get_conversation_messages(conversation_id, owner) == []
    service.db.update_conversation.assert_awaited_once_with(
        conversation_id, owner, ConversationUpdate(title="New")
    )
    service.db.delete_conversation.assert_awaited_once_with(conversation_id, owner)
    service.db.get_conversation_messages.assert_awaited_once_with(
        conversation_id, owner
    )

    conversation = ConversationResponse(
        id=conversation_id,
        user_id=owner,
        title="Owned",
        language="spanish",
        created_at=main.datetime.now(),
        updated_at=main.datetime.now(),
        is_active=True,
    )
    service.get_conversation = AsyncMock(return_value=conversation)
    service.get_conversation_messages = AsyncMock(return_value=[])
    stats = await service.get_conversation_stats(conversation_id, owner)
    assert stats["conversation_id"] == conversation_id
    service.get_conversation.assert_awaited_once_with(conversation_id, owner)
    service.get_conversation_messages.assert_awaited_once_with(conversation_id, owner)


def test_client_cannot_submit_user_id():
    with _offline_client() as client:
        client.post("/session/bootstrap")

        response = client.post(
            "/chat/conversations",
            json={"title": "Spoof", "language": "spanish", "user_id": str(uuid.uuid4())},
        )
        assert response.status_code == 422


def test_expensive_endpoint_returns_real_429(monkeypatch):
    with _offline_client(("203.0.113.10", 50000)) as client:
        first_principal = client.post("/session/bootstrap").json()["principal_id"]
        optimizer = MagicMock()
        optimizer.get_cached.return_value = {"response": {"respuesta_espanol": "cached"}}
        monkeypatch.setattr(main.app.state, "llm_optimizer", optimizer, raising=False)
        monkeypatch.setattr(
            main.app.state,
            "rag_engine",
            SimpleNamespace(get_cache_revision=lambda: "fixture-revision"),
            raising=False,
        )

        statuses = [
            client.post(
                "/legal-query", json={"query": "rate", "language": "spanish"}
            ).status_code
            for _ in range(10)
        ]
        assert statuses[:10] == [200] * 10
        client.cookies.clear()
        assert client.post("/session/bootstrap").json()["principal_id"] != first_principal
        assert client.post("/legal-query", json={"query": "rate"}).status_code == 429


def test_bootstrap_is_rate_limited_by_ip():
    with _offline_client(("203.0.113.11", 50000)) as client:
        statuses = [client.post("/session/bootstrap").status_code for _ in range(21)]
        assert statuses[:20] == [200] * 20
        assert statuses[20] == 429


@pytest.mark.asyncio
async def test_conversation_creation_returns_redacted_503(monkeypatch):
    from database.errors import DatabaseUnavailableError
    from database.surreal_adapter import SurrealAdapter

    adapter = SurrealAdapter()
    monkeypatch.setattr(adapter, "initialize", AsyncMock())
    with pytest.raises(DatabaseUnavailableError):
        await adapter.create_conversation(str(uuid.uuid4()))
    with _offline_client(("203.0.113.12", 50000)) as client:
        client.post("/session/bootstrap")
        monkeypatch.setattr(
            main.chat_service,
            "create_conversation",
            AsyncMock(side_effect=DatabaseUnavailableError()),
        )
        response = client.post("/chat/conversations", json={"language": "spanish"})
        assert response.status_code == 503
        assert response.json() == {"detail": "Chat persistence unavailable"}


@pytest.mark.asyncio
async def test_backend_health_is_degraded_without_surrealdb(monkeypatch):
    monkeypatch.setattr(
        main.chat_service,
        "db",
        SimpleNamespace(health_check=AsyncMock(return_value={"status": "unhealthy"})),
    )
    result = await main.health_check()
    assert (result["components"]["surrealdb"], result["status"]) == (
        "unhealthy",
        "degraded",
    )


def test_stream_rejects_foreign_conversation_before_persistence(monkeypatch):
    with _offline_client() as client:
        client.post("/session/bootstrap")
        service = MagicMock()
        service.get_conversation = AsyncMock(return_value=None)
        service.add_message = AsyncMock()
        monkeypatch.setattr(main, "chat_service", service)
        monkeypatch.setattr(main.app.state, "llm_optimizer", MagicMock(), raising=False)

        response = client.post(
            "/legal-query-stream",
            json={"query": "private", "conversation_id": str(uuid.uuid4())},
        )
        assert response.status_code == 404
        service.add_message.assert_not_awaited()


def test_public_errors_and_logs_are_redacted(monkeypatch, caplog):
    with _offline_client() as client:
        client.post("/session/bootstrap")
        optimizer = MagicMock()
        optimizer.get_cached.side_effect = RuntimeError("sensitive prompt value")
        monkeypatch.setattr(main.app.state, "llm_optimizer", optimizer, raising=False)
        monkeypatch.setattr(
            main.app.state,
            "rag_engine",
            SimpleNamespace(get_cache_revision=lambda: "fixture-revision"),
            raising=False,
        )

        with caplog.at_level(logging.ERROR, logger="ia_juridica.api"):
            response = client.post("/legal-query", json={"query": "secret prompt"})
        assert response.status_code == 500
        assert "sensitive" not in response.text
        assert "secret prompt" not in response.text
        assert "sensitive prompt value" not in caplog.text
        assert "secret prompt" not in caplog.text
        assert "RuntimeError" in caplog.text


def test_lightrag_provider_logs_are_disabled():
    import modules.rag.services.lightrag_engine  # noqa: F401

    assert logging.getLogger("lightrag").disabled
