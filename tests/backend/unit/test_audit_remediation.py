"""Offline regression evidence for A08/A12/A13/A17 (no providers or databases)."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import main
from config.settings import settings
from context.conversation_prompt import bounded_history, with_conversation
from database.postgres_adapter_final import DatabaseUnavailableError
from models.chat_models import ChatRequest, ConversationCreate
from modules.language.services.translation_service import TranslationService
from optimization.query_cache import answer_cache_key
from security import Principal, limiter
from utils.console import SafeAccessLog


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    c = TestClient(main.app)
    c.post("/session/bootstrap")
    yield c
    c.close()


@pytest.fixture
def translator(monkeypatch):
    service = TranslationService()
    monkeypatch.setattr(service, "translation_cache", {})
    monkeypatch.setattr(service, "google_translate_available", True)
    monkeypatch.setattr(service, "_is_translation_supported", lambda *_: True)

    async def echo(text, *_):
        return {"success": True, "translated_text": text, "method": "google_translate"}

    monkeypatch.setattr(service, "_translate_with_google", AsyncMock(side_effect=echo))
    return service


@pytest.mark.asyncio
async def test_long_translation_preserves_tail_structure_and_references(translator):
    original = (
        "Texto legal largo. " * 550 + "\n\n1. Artículo 42 de Ley 1234 [2]\n"
        "2. Advertencia final https://example.invalid/norma\n\nMARCADOR_FINAL"
    )
    result = await translator.translate(original, "es", "qu")
    assert result["success"] and result["complete"]
    assert result["translated_text"] == original
    assert result["segments_translated"] >= 3
    assert all(
        len(call.args[0]) <= 4000
        for call in translator._translate_with_google.await_args_list
    )
    assert result["review_required"]


@pytest.mark.asyncio
@pytest.mark.parametrize("output", ["", "corto", "Respuesta sin cita ZXQREF99QXZ"])
async def test_translation_rejects_empty_truncated_or_missing_citation(
    translator, output
):
    translator._translate_with_google.return_value = {
        "success": True,
        "translated_text": output,
        "method": "google_translate",
    }
    translator._translate_with_google.side_effect = None
    original = "Texto " * 500 + " [4]"
    result = await translator.translate(original, "es", "qu")
    assert not result["success"]
    assert result["original_text"] == original and result["warning"]
    assert not translator.translation_cache


@pytest.mark.asyncio
async def test_translation_failure_does_not_cache_partial_success(translator):
    count = 0

    async def fail_second(text, *_):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("PRIVATE_TRANSLATION_MARKER")
        return {"success": True, "translated_text": text, "method": "google_translate"}

    translator._translate_with_google.side_effect = fail_second
    result = await translator.translate("Texto completo. " * 700, "es", "qu")
    assert not result["success"] and result["segments_translated"] == 1
    assert "PRIVATE_TRANSLATION_MARKER" not in json.dumps(result)
    assert not translator.translation_cache


@pytest.mark.asyncio
async def test_missing_provider_is_not_successful_dictionary_translation(
    translator, monkeypatch
):
    monkeypatch.setattr(translator, "google_translate_available", False)
    result = await translator.translate(
        "Todos los pasos deben conservarse.", "es", "qu"
    )
    assert result["success"] is False
    assert result["original_text"]


@pytest.mark.parametrize(
    "factory, kwargs",
    [
        (main.LegalQueryRequest, {"query": " \n\t "}),
        (main.LegalQueryRequest, {"query": "valid", "language": "invented"}),
        (ChatRequest, {"message": "  "}),
        (ChatRequest, {"message": "valid", "language": "en"}),
        (ConversationCreate, {"language": "en"}),
        (ConversationCreate, {"initial_message": "  "}),
    ],
)
def test_input_contract_rejects_blank_or_unknown_language(factory, kwargs):
    with pytest.raises(ValidationError):
        factory(**kwargs)


@pytest.mark.parametrize("route", ["/legal-query", "/legal-query-stream"])
def test_foreign_conversation_is_404_before_generation(client, monkeypatch, route):
    chat = SimpleNamespace(
        get_conversation=AsyncMock(return_value=None), add_message=AsyncMock()
    )
    rag = SimpleNamespace(query_with_rerank=AsyncMock())
    monkeypatch.setattr(main, "chat_service", chat)
    monkeypatch.setattr(main.app.state, "rag_engine", rag, raising=False)
    response = client.post(
        route, json={"query": "Consulta", "conversation_id": "foreign"}
    )
    assert response.status_code == 404
    chat.add_message.assert_not_awaited()
    rag.query_with_rerank.assert_not_awaited()


@pytest.mark.parametrize("route", ["/legal-query", "/legal-query-stream"])
def test_storage_failure_is_redacted_503(client, monkeypatch, route):
    monkeypatch.setattr(
        main.chat_service,
        "get_conversation",
        AsyncMock(side_effect=DatabaseUnavailableError("PRIVATE_DSN")),
    )
    response = client.post(
        route, json={"query": "Consulta", "conversation_id": "owned"}
    )
    assert response.status_code == 503
    assert "PRIVATE_DSN" not in response.text


@pytest.mark.parametrize("route", ["/legal-query", "/legal-query-stream"])
def test_invalid_query_http_422(client, route):
    assert client.post(route, json={"query": "   "}).status_code == 422
    assert (
        client.post(route, json={"query": "Hola", "language": "en"}).status_code == 422
    )


def test_context_and_history_budgets_are_explicit():
    messages = [SimpleNamespace(role="user", content="x" * 2000) for _ in range(30)]
    history = bounded_history(messages)
    assert sum(len(m["content"]) for m in history) <= 6000
    assert len(history) <= 12
    with pytest.raises(ValueError):
        with_conversation("prompt", context={"text": "x" * 10001})


@pytest.mark.parametrize(
    "changed",
    [
        "owner_id",
        "context",
        "history",
        "conversation_id",
        "corpus_revision",
        "language",
        "mode",
    ],
)
def test_cache_is_private_contextual_and_revision_aware(changed):
    kwargs = dict(
        query="¿Y ahora?",
        language="spanish",
        owner_id="owner",
        context={},
        history=[],
        conversation_id="id",
        corpus_revision="r1",
        mode="query",
    )
    old = answer_cache_key(**kwargs)
    values = {
        "owner_id": "other",
        "context": {"city": "Cusco"},
        "history": [{"role": "user", "content": "Mi empleador"}],
        "conversation_id": "id2",
        "corpus_revision": "r2",
        "language": "quechua",
        "mode": "stream",
    }
    kwargs[changed] = values[changed]
    assert answer_cache_key(**kwargs) != old


def test_corpus_edit_changes_revision(rag, monkeypatch):
    monkeypatch.setattr(settings, "LOAD_LOCAL_KG", True)
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False)
    old = rag.get_cache_revision()
    rag.documents["new"]["content"] += " Modificación vigente."
    assert rag.get_cache_revision() != old
    monkeypatch.setattr(settings, "NEO4J_ENABLED", True)
    assert rag.get_cache_revision() is None


@pytest.mark.asyncio
async def test_second_turn_context_reaches_prompt_and_owner_check(monkeypatch):
    chat = SimpleNamespace(
        get_conversation=AsyncMock(return_value=object()),
        get_conversation_messages=AsyncMock(
            return_value=[
                SimpleNamespace(role="user", content="Mi caso es laboral en Cusco.")
            ]
        ),
    )
    monkeypatch.setattr(main, "chat_service", chat)
    monkeypatch.setattr(
        main.app.state,
        "rag_engine",
        SimpleNamespace(get_cache_revision=lambda: "r1"),
        raising=False,
    )
    payload = main.LegalQueryRequest(
        query="¿Y qué hago después?", conversation_id="owned"
    )
    key, history = await main._prepare_query_context(payload, "owner", "query")
    prompt = main.ContextEngineer().build_legal_prompt(
        payload.query, [], history=history
    )[0]
    assert "Mi caso es laboral en Cusco." in prompt
    assert key and "NO instrucciones" in prompt
    chat.get_conversation_messages.assert_awaited_once_with("owned", "owner", limit=12)


def test_access_log_does_not_keep_oauth_code_or_ip():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("192.0.2.10", "GET", "/auth/google/callback?code=SECRET", "1.1", 500),
        None,
    )
    assert SafeAccessLog().filter(record)
    assert (
        "SECRET" not in record.getMessage() and "192.0.2.10" not in record.getMessage()
    )


def test_stream_error_and_logs_do_not_echo_query_or_request_id(
    client, monkeypatch, caplog, capsys
):
    marker = "PRIVATE_MARKER_123"
    monkeypatch.setattr(
        main.app.state,
        "rag_engine",
        SimpleNamespace(get_cache_revision=lambda: "r1"),
        raising=False,
    )
    optimizer = MagicMock()
    optimizer.get_cached.side_effect = RuntimeError(marker)
    monkeypatch.setattr(main.app.state, "llm_optimizer", optimizer, raising=False)
    with caplog.at_level(logging.INFO, logger="ia_juridica.api"):
        response = client.post(
            "/legal-query-stream",
            json={"query": marker},
            headers={"X-Request-ID": marker},
        )
    captured = capsys.readouterr()
    assert response.status_code == 500
    assert marker not in response.text + caplog.text + captured.out + captured.err
    assert response.headers["X-Request-ID"] != marker


def test_oauth_failure_is_redacted(client, monkeypatch, caplog, capsys):
    from modules.auth.routes import auth_routes

    marker = "PRIVATE_OAUTH_MARKER"
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "fixture")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "fixture")
    http = MagicMock()
    http.__aenter__ = AsyncMock(side_effect=RuntimeError(marker))
    monkeypatch.setattr(auth_routes.httpx, "AsyncClient", lambda: http)
    with caplog.at_level(logging.ERROR, logger="ia_juridica.auth"):
        response = client.get("/auth/google/callback", params={"code": marker})
    captured = capsys.readouterr()
    assert response.status_code == 500
    assert marker not in response.text + caplog.text + captured.out + captured.err
    assert "RuntimeError" in caplog.text
