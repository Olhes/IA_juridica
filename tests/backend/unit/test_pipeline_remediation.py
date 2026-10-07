"""Offline regressions for lifecycle, candidate retrieval and shared delivery."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import main
from security import Principal
from services.legal_queries import answer_query
from datetime import datetime, timezone
from uuid import uuid4


@pytest.fixture
def pipeline(monkeypatch):
    state = main.app.state
    values = dict(
        corpus_state="ready",
        rag_engine=SimpleNamespace(
            documents={"fixture": {}},
            get_cache_revision=lambda: "r1",
            query_with_rerank=AsyncMock(
                return_value={
                    "documents": [{"content": "Evidence"}],
                    "sources": ["fixture"],
                    "method": "fixture",
                    "total_candidates": 1,
                }
            ),
        ),
        legal_agent=SimpleNamespace(
            respond_general=AsyncMock(return_value={"respuesta_espanol": "UNVALIDATED"})
        ),
        context_engineer=SimpleNamespace(
            build_legal_prompt=MagicMock(return_value=("prompt", {}))
        ),
        response_validator=SimpleNamespace(
            validate=AsyncMock(
                return_value=SimpleNamespace(
                    answer_data={"respuesta_espanol": "VALIDATED"},
                    sources=["fixture"],
                    is_reliable=True,
                    validation_report=SimpleNamespace(
                        model_dump=lambda: {"status": "passed"}
                    ),
                )
            )
        ),
        llm_optimizer=MagicMock(),
    )
    values["llm_optimizer"].get_cached.return_value = None
    values["llm_optimizer"].get_session_stats.return_value = {}
    for key, value in values.items():
        monkeypatch.setattr(state, key, value, raising=False)
    return state


@pytest.mark.asyncio
async def test_candidate_after_first_fifty_is_found_and_order_independent(rag):
    rag.documents = {
        str(i): {
            "chunks": [f"Materia ajena visitas {i}"],
            "metadata": {"filename": str(i)},
        }
        for i in range(80)
    }
    rag.documents["late"] = {
        "chunks": ["Tributo municipal licencia comercio"],
        "metadata": {"filename": "late.md"},
    }
    first = await rag.query_with_rerank(
        "tributo municipal licencia", top_k=1, rerank_candidates=50
    )
    rag.documents = dict(reversed(list(rag.documents.items())))
    second = await rag.query_with_rerank(
        "tributo municipal licencia", top_k=1, rerank_candidates=50
    )
    assert first == second
    assert first["sources"] == ["late.md"]
    assert all(0 < score <= 1 for score in first["rerank_scores"])


@pytest.mark.asyncio
async def test_nonmatching_corpus_is_not_presented_as_evidence(rag):
    result = await rag.query_with_rerank("tributo comercio aeronave")
    assert result["method"] == "no_match"
    assert result["documents"] == result["sources"] == result["rerank_scores"] == []


@pytest.mark.asyncio
async def test_native_graph_candidates_are_real_chunks_not_generated_answer(
    rag, monkeypatch
):
    import modules.rag.services.lightrag_engine as module

    monkeypatch.setattr(module, "LIGHTRAG_AVAILABLE", True)
    rag.documents = {}
    rag._storages_initialized = True
    rag.rag = SimpleNamespace(
        aquery_data=AsyncMock(
            return_value={
                "answer": "INVENTED",
                "data": {
                    "chunks": [
                        {
                            "chunk_id": "g1",
                            "content": "Licencia municipal",
                            "file_path": "graph.md",
                        }
                    ]
                },
            }
        )
    )
    result = await rag.query_with_rerank("licencia municipal")
    assert result["sources"] == ["graph.md"]
    assert result["documents"][0]["id"] == "g1"
    assert "INVENTED" not in result["answer"]


@pytest.mark.asyncio
async def test_loader_retries_failure_without_false_ready(monkeypatch):
    engine = SimpleNamespace(
        initialize_storages=AsyncMock(side_effect=RuntimeError("private")),
        load_processed_documents=AsyncMock(),
        documents={},
    )
    monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(main.app.state, "corpus_state", "loading", raising=False)
    await main.load_heavy_components(engine, main.PROCESSED_DIR)
    assert main.app.state.corpus_state == "failed"
    assert engine.initialize_storages.await_count == 3
    engine.load_processed_documents.assert_not_awaited()


@pytest.mark.asyncio
async def test_lifespan_loads_once_and_finalizes(monkeypatch, pipeline):
    engine = pipeline.rag_engine
    engine.initialize_storages = AsyncMock()
    engine.load_processed_documents = AsyncMock()
    engine.rag = SimpleNamespace(finalize_storages=AsyncMock())
    db, redis = SimpleNamespace(close=AsyncMock()), SimpleNamespace(
        initialize=AsyncMock(), close=AsyncMock()
    )
    monkeypatch.setattr(
        main, "chat_service", SimpleNamespace(initialize=AsyncMock(), db=db)
    )
    monkeypatch.setattr(main, "redis_adapter", redis)
    monkeypatch.setattr(
        type(main.settings), "validate_configuration", lambda self: {"valid": True}
    )
    monkeypatch.setattr(main.settings, "NEO4J_ENABLED", False)
    async with main.lifespan(main.app):
        await pipeline.corpus_task
        assert pipeline.corpus_state == "ready"
        engine.load_processed_documents.assert_awaited_once_with(
            str(main.PROCESSED_DIR)
        )
    assert pipeline.corpus_state == "stopped"
    engine.rag.finalize_storages.assert_awaited_once()
    db.close.assert_awaited_once()
    redis.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_cancels_loading_and_closes_on_error(monkeypatch, pipeline):
    started = asyncio.Event()

    async def load(*args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "load_heavy_components", load)
    db, redis = SimpleNamespace(close=AsyncMock()), SimpleNamespace(
        initialize=AsyncMock(), close=AsyncMock()
    )
    monkeypatch.setattr(
        main, "chat_service", SimpleNamespace(initialize=AsyncMock(), db=db)
    )
    monkeypatch.setattr(main, "redis_adapter", redis)
    monkeypatch.setattr(
        type(main.settings), "validate_configuration", lambda self: {"valid": True}
    )
    with pytest.raises(ValueError):
        async with main.lifespan(main.app):
            await started.wait()
            raise ValueError("caller error")
    assert pipeline.corpus_task.cancelled()
    db.close.assert_awaited_once()
    redis.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["loading", "failed", "stopped"])
async def test_readiness_and_first_query_fail_closed(pipeline, phase):
    pipeline.corpus_state = phase
    for call in (main.readiness(), answer_query(pipeline, "Consulta", "spanish")):
        with pytest.raises(HTTPException) as error:
            await call
        assert error.value.status_code == 503
    pipeline.rag_engine.query_with_rerank.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_and_stream_return_same_validated_content(pipeline):
    owner = Principal("owner", 9999999999)
    request = Request(
        {"type": "http", "method": "POST", "path": "/legal-query", "headers": []}
    )
    payload = main.LegalQueryRequest(query="Consulta")
    normal = await main.legal_query(request=request, payload=payload, principal=owner)
    stream = await main.legal_query_stream(
        request=request, payload=payload, principal=owner
    )
    events = [json.loads(chunk) async for chunk in stream.body_iterator]
    assert (
        normal["response"]
        == events[-1]["data"]["response"]
        == {"respuesta_espanol": "VALIDATED"}
    )
    assert "UNVALIDATED" not in str(events)
    assert pipeline.response_validator.validate.await_count == 2


@pytest.mark.asyncio
async def test_chat_uses_same_validator_before_assistant_persistence(pipeline):
    from modules.chat.services.chat_service import ChatService
    from models.chat_models import ChatRequest, MessageResponse

    chat = object.__new__(ChatService)
    cid = str(uuid4())
    chat.get_conversation = AsyncMock(return_value=object())
    chat.get_conversation_messages = AsyncMock(return_value=[])
    chat._build_conversation_context = AsyncMock(
        return_value=SimpleNamespace(model_dump=lambda: {})
    )
    saved = []

    async def add_message(conversation_id, user_id, message):
        saved.append(message)
        if message.role == "assistant":
            pipeline.response_validator.validate.assert_awaited_once()
            assert message.content == "VALIDATED"
        return MessageResponse(
            id=str(uuid4()),
            conversation_id=cid,
            created_at=datetime.now(timezone.utc),
            **message.model_dump(exclude={"conversation_id"}),
        )

    chat.add_message = add_message
    result = await chat.process_chat_message(
        ChatRequest(message="Consulta", conversation_id=cid), "owner"
    )
    assert result.success and result.message.content == "VALIDATED"
    assert len(saved) == 2


@pytest.mark.asyncio
async def test_chat_provider_error_never_persists_fake_assistant(pipeline):
    from modules.chat.services.chat_service import ChatService
    from models.chat_models import ChatRequest

    chat = object.__new__(ChatService)
    chat.get_conversation = AsyncMock(return_value=object())
    chat.get_conversation_messages = AsyncMock(return_value=[])
    chat._build_conversation_context = AsyncMock(
        return_value=SimpleNamespace(model_dump=lambda: {})
    )
    chat.add_message = AsyncMock(return_value=SimpleNamespace(id="u1"))
    pipeline.legal_agent.respond_general.side_effect = RuntimeError("PRIVATE")
    with pytest.raises(HTTPException) as error:
        await chat.process_chat_message(
            ChatRequest(message="Consulta", conversation_id="owned"), "owner"
        )
    assert error.value.status_code == 502
    assert chat.add_message.await_count == 1


@pytest.mark.asyncio
async def test_no_evidence_abstains_even_if_self_correction_invents(pipeline):
    pipeline.rag_engine.query_with_rerank.return_value = {
        "documents": [],
        "method": "no_match",
    }
    result = await answer_query(pipeline, "Consulta", "spanish", cache_key="private")
    assert result["metadata"]["evidence_status"] == "insufficient_evidence"
    assert "No hay evidencia" in result["response"]["respuesta_espanol"]
    assert result["validation"]["is_reliable"] is False
    pipeline.legal_agent.respond_general.assert_not_awaited()
    pipeline.llm_optimizer.cache_response.assert_not_called()


@pytest.mark.asyncio
async def test_provider_failure_is_redacted_not_success(pipeline):
    pipeline.legal_agent.respond_general.side_effect = RuntimeError("PRIVATE")
    with pytest.raises(HTTPException) as error:
        await answer_query(pipeline, "Consulta", "spanish")
    assert error.value.status_code == 502 and "PRIVATE" not in error.value.detail
    pipeline.response_validator.validate.assert_not_awaited()


@pytest.mark.asyncio
async def test_translation_provider_exception_does_not_leak_payload(capsys):
    from modules.language.services.translation_service import TranslationService
    from loguru import logger
    service = TranslationService()
    service.google_translator = SimpleNamespace(translate=AsyncMock(side_effect=RuntimeError("PRIVATE_CANARY")))
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)))
    try:
        result = await service._translate_with_google("PRIVATE_CANARY", "es", "qu")
    finally:
        logger.remove(sink)
    assert not result["success"]
    assert "PRIVATE_CANARY" not in "".join(messages)
    captured = capsys.readouterr()
    assert "PRIVATE_CANARY" not in captured.out + captured.err


@pytest.mark.parametrize("metric_name", ["BiasMetric", "HallucinationMetric"])
def test_deepeval4_native_score_direction_without_judge(metric_name):
    import deepeval.metrics as metrics

    metric = object.__new__(getattr(metrics, metric_name))
    metric.threshold, metric.error = 0.7, None
    metric.score = 0.8
    assert metric.is_successful()
    metric.score = 0.2
    assert not metric.is_successful()
