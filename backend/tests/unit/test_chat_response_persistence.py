from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import main


@pytest.mark.unit
@pytest.mark.parametrize(
    ("payload", "language", "expected"),
    [
        ({"respuesta_espanol": "Spanish response"}, "spanish", "Spanish response"),
        ({"respuesta_espanol": "Spanish fallback"}, "quechua", "Spanish fallback"),
        ({"answer": "Generic fallback"}, "spanish", "Generic fallback"),
    ],
)
def test_extract_response_text_uses_language_safe_fallbacks(payload, language, expected):
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

    monkeypatch.setattr(main, "chat_service", chat_service)
    monkeypatch.setattr(main.app.state, "llm_optimizer", optimizer, raising=False)
    monkeypatch.setattr(main.app.state, "rag_engine", SimpleNamespace(query_with_rerank=AsyncMock(return_value={"documents": []})), raising=False)
    monkeypatch.setattr(main.app.state, "context_engineer", SimpleNamespace(build_legal_prompt=MagicMock(return_value=("prompt", {}))), raising=False)
    monkeypatch.setattr(
        main.app.state,
        "legal_agent",
        SimpleNamespace(stream_general_text=stream_text, build_general_response_from_text=MagicMock(return_value={})),
        raising=False,
    )
    monkeypatch.setattr(main.app.state, "response_validator", validator, raising=False)

    response = await main.legal_query_stream(
        main.LegalQueryRequest(query="Test query", conversation_id="conversation-id")
    )
    async for _chunk in response.body_iterator:
        pass

    assistant_message = chat_service.add_message.await_args_list[1].kwargs["message_data"]
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

    monkeypatch.setattr(main, "chat_service", chat_service)
    monkeypatch.setattr(main.app.state, "llm_optimizer", optimizer, raising=False)

    response = await main.legal_query_stream(
        main.LegalQueryRequest(query="Cached query", conversation_id="conversation-id")
    )
    async for _chunk in response.body_iterator:
        pass

    assistant_message = chat_service.add_message.await_args_list[1].kwargs["message_data"]
    assert assistant_message.content == "Cached Spanish response"
