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
from database.errors import DatabaseUnavailableError
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
    monkeypatch.setattr(settings, "TRANSLATION_ENABLED", True)
    monkeypatch.setattr(service, "translation_cache", {})
    monkeypatch.setattr(service, "google_translate_available", True)
    monkeypatch.setattr(service, "_is_translation_supported", lambda *_: True)

    async def echo(text, *_):
        return {"success": True, "translated_text": text, "method": "google_translate"}

    monkeypatch.setattr(service, "_translate_with_google", AsyncMock(side_effect=echo))
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize("output,success", [("", False), ("Texto legal", False), ("Legal text", True)])
async def test_translation_provider_rejects_unchanged_output_without_caching(
    translator, monkeypatch, output, success
):
    monkeypatch.setattr(
        translator, "_translate_with_google",
        TranslationService._translate_with_google.__get__(translator),
    )
    provider = SimpleNamespace(translate=AsyncMock(return_value=SimpleNamespace(text=output)))
    monkeypatch.setattr(translator, "google_translator", provider)
    result = await translator.translate("Texto legal", "es", "qu")
    assert result["success"] is success
    assert bool(translator.translation_cache) is success
    if success:
        assert result["translated_text"] == output
        assert "confidence" not in result
    else:
        assert result["original_text"] == "Texto legal"
        assert result["complete"] is False


@pytest.mark.asyncio
async def test_translation_preserves_reference_only_segments_without_provider(translator):
    result = await translator.translate("[4]\n\n123.", "es", "qu")
    assert result["success"] and result["translated_text"] == "[4]\n\n123."
    translator._translate_with_google.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_disabled_translation_never_calls_provider_or_serves_cached_output(translator, monkeypatch):
    text = "Artículo 12. Texto legal."
    assert (await translator.translate(text, "es", "qu"))["success"]
    assert translator.translation_cache
    translator._translate_with_google.reset_mock()
    monkeypatch.setattr(settings, "TRANSLATION_ENABLED", False)

    result = await translator.translate(text, "es", "qu")
    assert not result["success"] and not result["complete"]
    assert result["original_text"] == text and result["method"] == "none"
    translator._translate_with_google.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_language_facade_does_not_rewrite_provider_output(translator):
    from language import LanguageHandler, TranslationService as LegacyTranslationService

    assert LegacyTranslationService is TranslationService
    handler = LanguageHandler()
    result = await handler.process_response(
        "quiere una pensión de alimentos", target_language="qu", context={"legal_topic": "pensión"}
    )
    assert result["translated"] and not result["context_applied"]
    assert result["response"] == "quiere una pensión de alimentos"


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
    message = record.getMessage()
    assert "SECRET" not in message and "192.0.2.10" not in message
    assert "GET /auth/google/callback HTTP/1.1" in message


def test_access_log_sanitizes_injection_uuids_tokens_and_length():
    def _filter_path(raw_path: str) -> str:
        record = logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            "",
            0,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1", "GET", raw_path, "1.1", 404),
            None,
        )
        assert SafeAccessLog().filter(record)
        return record.getMessage()

    # Preserves plain routes like /favicon.ico for observability
    assert "GET /favicon.ico HTTP/1.1" in _filter_path("/favicon.ico")

    # Neutralizes CRLF / control-character log injection (CWE-117)
    injected = _filter_path("/ok\r\nINFO: forged\x00line?token=abc#frag")
    assert "\r" not in injected and "\n" not in injected and "\x00" not in injected
    assert "token" not in injected and "abc" not in injected and "frag" not in injected

    # Redacts UUID resource identifiers and local-session tokens in paths
    conv_msg = _filter_path(
        "/chat/conversations/c9879836-f083-4d3b-b760-ea898bae18c4?limit=50"
    )
    assert "c9879836-f083-4d3b-b760-ea898bae18c4" not in conv_msg
    assert "limit=50" not in conv_msg
    assert "GET /chat/conversations/{id} HTTP/1.1" in conv_msg

    session_msg = _filter_path("/local-session/super-secret-token-value")
    assert "super-secret-token-value" not in session_msg
    assert "GET /local-session/{redacted} HTTP/1.1" in session_msg

    # Local-session bypass variants (double slash, uppercase, root_path prefix, trailing segments)
    for bypass in (
        "//local-session/SECRET_TOK",
        "/local-session//SECRET_TOK",
        "/LOCAL-SESSION/SECRET_TOK",
        "/api/local-session/SECRET_TOK",
        "/local-session/SECRET_A/SECRET_B",
    ):
        assert "SECRET" not in _filter_path(bypass)

    # Fragment-before-query ordering and proxy-form absolute URI with credentials
    frag_first = _filter_path("/auth/google/callback#frag?code=SECRET")
    assert "frag" not in frag_first and "SECRET" not in frag_first
    assert "GET /auth/google/callback HTTP/1.1" in frag_first

    proxy_uri = _filter_path("http://user:SECRET@example.com/path")
    assert "SECRET" not in proxy_uri and "GET [route] HTTP/1.1" in proxy_uri

    # Unicode line/control separators on path
    uni_msg = _filter_path("/a\u2028b\u2029c\x85d\x9b31mred")
    for ch in ("\u2028", "\u2029", "\x85", "\x9b"):
        assert ch not in uni_msg

    # Bounds pathological long scanner paths
    long_msg = _filter_path("/" + "a" * 300)
    assert len(long_msg) < 200
    assert "127.0.0.1" not in long_msg


def test_access_log_sanitizes_method_version_and_rejects_bad_status():
    forged = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1234", "GET\r\nINFO: forged", "/ok", "1.1\u2028forged", 200),
        None,
    )
    assert SafeAccessLog().filter(forged)
    msg = forged.getMessage()
    assert "\r" not in msg and "\n" not in msg and "\u2028" not in msg
    assert "forged" not in msg
    assert '[client] - "[method] /ok HTTP/[version]" 200' == msg

    long_method = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1234", "A" * 300, "/ok", "1.1", 200),
        None,
    )
    assert SafeAccessLog().filter(long_method)
    assert len(long_method.getMessage()) < 100

    bad_status = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", 123, None, None, "200\r\nFAKE"),
        None,
    )
    assert not SafeAccessLog().filter(bad_status)

    bool_status = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", "/ok", "1.1", True),
        None,
    )
    assert not SafeAccessLog().filter(bool_status)


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
    # El fallo ocurre tras abrir el stream: sale como evento `error`, sin eco.
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [e["type"] for e in events] == ["meta", "error", "done"]
    assert events[1]["code"] == "INTERNAL_ERROR"
    assert marker not in response.text + caplog.text + captured.out + captured.err
    assert response.headers["X-Request-ID"] != marker
    assert {e["request_id"] for e in events} == {response.headers["X-Request-ID"]}


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
