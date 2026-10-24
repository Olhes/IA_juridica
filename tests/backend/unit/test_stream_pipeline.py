"""Tiempos por etapa y stream NDJSON v1 (offline, sin proveedores)."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.legal_queries import PipelineError, answer_query
from services.legal_stream import stream_legal_query
from services.pipeline_telemetry import PipelineTimer


def make_state(*, documents=True, retrieval=None, generation=None):
    docs = [{"content": "Evidencia"}] if documents else []
    optimizer = MagicMock()
    optimizer.get_cached.return_value = None
    optimizer.get_session_stats.return_value = {}
    return SimpleNamespace(
        corpus_state="ready",
        rag_engine=SimpleNamespace(
            documents={"f": {}},
            query_with_rerank=retrieval
            or AsyncMock(return_value={"documents": docs, "method": "fixture"}),
        ),
        context_engineer=SimpleNamespace(
            build_legal_prompt=MagicMock(return_value=("p", {}))
        ),
        legal_agent=SimpleNamespace(
            respond_general=generation
            or AsyncMock(return_value={"respuesta_espanol": "borrador"})
        ),
        response_validator=SimpleNamespace(
            validate=AsyncMock(
                return_value=SimpleNamespace(
                    answer_data={"respuesta_espanol": "validada"},
                    sources=["f"],
                    is_reliable=True,
                    validation_report=SimpleNamespace(
                        model_dump=lambda: {"status": "passed"}
                    ),
                )
            )
        ),
        llm_optimizer=optimizer,
    )


async def test_timer_records_stage_and_notifies_start_and_end():
    seen = []
    ticks = iter([0.0, 0.0, 0.25, 0.25, 0.5])
    timer = PipelineTimer(seen.append, clock=lambda: next(ticks))
    async with timer.stage("retrieval"):
        pass
    assert [(e["stage"], e["status"]) for e in seen] == [
        ("retrieval", "start"),
        ("retrieval", "end"),
    ]
    assert timer.stages == {"retrieval": 250.0}
    assert timer.snapshot()["cache_hit"] is False
    with pytest.raises(ValueError):
        async with timer.stage("inventada"):
            pass


async def test_answer_query_reports_every_stage_in_order_and_timings():
    seen = []
    result = await answer_query(
        make_state(), "Consulta", "spanish", on_stage=seen.append
    )
    assert [(e["stage"], e["status"]) for e in seen] == [
        ("retrieval", "start"),
        ("retrieval", "end"),
        ("generation", "start"),
        ("generation", "end"),
        ("validation", "start"),
        ("validation", "end"),
    ]
    timings = result["metadata"]["timings"]
    assert set(timings["stages"]) == {"retrieval", "generation", "validation"}
    assert timings["cache_hit"] is False and timings["total_ms"] >= 0


async def test_cache_hit_has_timings_and_timings_are_not_cached():
    state = make_state()
    await answer_query(state, "Consulta", "spanish", cache_key="k")
    cached = state.llm_optimizer.cache_response.call_args.args[1]
    assert "timings" not in cached["metadata"]
    state.llm_optimizer.get_cached.return_value = cached
    hit = await answer_query(state, "Consulta", "spanish", cache_key="k")
    assert hit["cached"] is True and hit["metadata"]["timings"]["cache_hit"] is True


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (
            make_state(retrieval=AsyncMock(side_effect=RuntimeError("PRIVADO"))),
            "RETRIEVAL_UNAVAILABLE",
        ),
        (
            make_state(generation=AsyncMock(side_effect=RuntimeError("PRIVADO"))),
            "GENERATION_UNAVAILABLE",
        ),
    ],
)
async def test_pipeline_errors_carry_stable_code(state, code):
    with pytest.raises(PipelineError) as error:
        await answer_query(state, "Consulta", "spanish")
    assert error.value.code == code and "PRIVADO" not in error.value.detail


async def collect(**overrides):
    async def persist(_result):
        return None

    options = dict(
        run_pipeline=lambda on_stage: answer_query(
            make_state(), "Consulta", "spanish", on_stage=on_stage
        ),
        extract_text=lambda result: result["response"]["respuesta_espanol"],
        persist=persist,
        request_id="req",
        language="spanish",
        timeout_s=5,
    )
    options.update(overrides)
    return [json.loads(line) async for line in stream_legal_query(**options)]


async def test_stream_emits_stages_before_validated_text_then_done():
    events = await collect()
    types = [e["type"] for e in events]
    assert types[0] == "meta" and types[-3:] == ["chunk", "final", "done"]
    assert types[1:-3] and set(types[1:-3]) == {"stage"}
    assert [e["seq"] for e in events] == list(range(len(events)))
    assert {e["request_id"] for e in events} == {"req"}
    assert "borrador" not in json.dumps(events)
    assert events[-3]["delta"] == "validada"
    assert events[-2]["data"]["metadata"]["timings"]["stages"]["validation"] >= 0


async def test_stream_failures_become_a_single_error_event_with_code():
    async def failing(_on_stage):
        raise PipelineError(503, "Legal retrieval unavailable", "RETRIEVAL_UNAVAILABLE")

    events = await collect(run_pipeline=failing)
    assert [e["type"] for e in events] == ["meta", "error", "done"]
    assert events[1]["code"] == "RETRIEVAL_UNAVAILABLE"
    assert events[1]["retryable"] is True

    async def crashing(_on_stage):
        raise RuntimeError("PRIVADO")

    events = await collect(run_pipeline=crashing)
    assert events[1]["code"] == "INTERNAL_ERROR" and events[1]["retryable"] is False
    assert "PRIVADO" not in json.dumps(events)


async def test_stream_times_out_and_cancels_the_pipeline():
    cancelled = asyncio.Event()

    async def slow(_on_stage):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    events = await collect(run_pipeline=slow, timeout_s=0.05)
    assert [e["type"] for e in events] == ["meta", "error", "done"]
    assert events[1]["code"] == "TIMEOUT" and events[1]["retryable"] is True
    assert cancelled.is_set()


async def test_persistence_failure_is_an_error_not_a_final():
    async def persist(_result):
        raise RuntimeError("DB")

    events = await collect(persist=persist)
    assert "final" not in [e["type"] for e in events]
    assert events[-2]["type"] == "error"


async def test_answer_includes_verified_citations_and_evidence_excerpts():
    document = {
        "content": "Prelación de obligados (Art. 475 CC). " + "texto " * 80,
        "metadata": {"title": "Guía de pensión"},
        "relevance_score": 0.8,
    }
    state = make_state(retrieval=AsyncMock(return_value={"documents": [document], "method": "fixture"}))
    state.response_validator.validate.return_value.answer_data = {
        "respuesta_espanol": "Rige el artículo 475 del Código Civil y la Ley 99999."
    }
    metadata = (await answer_query(state, "Consulta", "spanish"))["metadata"]
    statuses = {c["key"]: c["status"] for c in metadata["citations"]}
    assert statuses == {"cc:art:475": "verified", "ley:99999": "unverified"}
    assert metadata["citations"][0]["source"] == "Guía de pensión"
    (evidence,) = metadata["evidence"]
    assert evidence["source"] == "Guía de pensión" and evidence["relevance"] == 0.8
    assert len(evidence["excerpt"]) <= 240 and "Art. 475" in evidence["excerpt"]


async def test_answer_without_documents_has_no_citations_or_evidence():
    state = make_state(documents=False)
    metadata = (await answer_query(state, "Consulta", "spanish"))["metadata"]
    assert metadata["evidence_status"] == "insufficient_evidence"
    assert metadata["citations"] == [] and metadata["evidence"] == []


async def test_evidence_reports_retrieval_origin_and_cited_jurisprudence():
    graph = {"content": "Resolvió la Casación 2154-2018, Arequipa.", "metadata": {"title": "Grafo", "retrieval_origin": "lightrag"}, "relevance_score": 0.7}
    lexical = {"content": "Texto sin jurisprudencia.", "metadata": {"title": "Léxico"}, "relevance_score": 0.4}
    state = make_state(retrieval=AsyncMock(return_value={"documents": [graph, lexical], "method": "cohere_rerank"}))
    metadata = (await answer_query(state, "Consulta", "spanish"))["metadata"]
    first, second = metadata["evidence"]
    assert (first["origin"], first["jurisprudence"]) == ("lightrag", ["casacion:2154-2018"])
    assert (second["origin"], second["jurisprudence"]) == ("lexical", [])
    assert metadata["retrieval_method"] == "cohere_rerank"
