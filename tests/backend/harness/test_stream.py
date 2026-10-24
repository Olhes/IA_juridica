"""Calidad del stream: fixtures rotos, validez del contrato y latencia p50/p95 por etapa."""

import json

import pytest

from evaluation.harness import runner, stream_eval, stream_fixtures
from services.stream_telemetry import StreamMetrics, StreamTelemetry, latency_summary, percentile

pytestmark = pytest.mark.harness


def test_broken_stream_fixtures_match_their_generator_byte_for_byte(tmp_path):
    """Se regeneran con ``python -m evaluation.harness.stream_fixtures``; no se editan a mano."""
    written = stream_fixtures.write(tmp_path)
    assert written == sorted(stream_fixtures.build())
    for name in written + ["manifest.json"]:
        assert (tmp_path / name).read_bytes() == (stream_fixtures.FIXTURES_DIR / name).read_bytes(), name
    assert {p.name for p in stream_fixtures.FIXTURES_DIR.iterdir()} == set(written) | {"manifest.json", ".gitattributes"}


def test_fixtures_cover_the_failure_modes_the_client_must_survive():
    manifest = json.loads((stream_fixtures.FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) >= 15
    for needed in ("bom_crlf", "invalid_line", "repairable_prefix", "concatenated_objects", "truncated_final", "missing_final",
                   "duplicate_events", "out_of_order", "error_event", "unsupported_version", "legacy_no_seq", "empty"):
        assert f"{needed}.ndjson" in manifest
    assert (stream_fixtures.FIXTURES_DIR / "bom_crlf.ndjson").read_bytes().startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in (stream_fixtures.FIXTURES_DIR / "bom_crlf.ndjson").read_bytes()


def test_the_reference_valid_stream_satisfies_the_contract_and_broken_ones_do_not():
    valid = [ln for ln in (stream_fixtures.FIXTURES_DIR / "valid.ndjson").read_text(encoding="utf-8").splitlines()]
    assert stream_eval.check_contract(valid) == []
    for name in ("missing_final", "truncated_final", "duplicate_events", "unsupported_version", "empty", "only_stages"):
        lines = (stream_fixtures.FIXTURES_DIR / f"{name}.ndjson").read_text(encoding="utf-8").splitlines()
        assert stream_eval.check_contract(lines), name


def test_contract_checker_names_each_kind_of_problem():
    events = stream_fixtures.valid_events()
    dumps = stream_fixtures.dumps
    problems = stream_eval.check_contract([dumps(e) for e in events[:8]])
    assert "0 eventos terminales (se espera 1)" in problems and "falta `done`" in problems
    assert any("chunk" in p for p in stream_eval.check_contract([dumps(e) for e in events[:7] + [events[7] | {"delta": "x"}] + events[8:]]))
    assert any("después de `done`" in p for p in stream_eval.check_contract([dumps(e) for e in events] + [dumps(events[0])]))


def test_percentiles_use_nearest_rank_and_are_na_without_data():
    values = list(range(1, 101))
    assert percentile(values, 50) == 50 and percentile(values, 95) == 95 and percentile([7], 95) == 7
    assert percentile([], 50) is None
    assert latency_summary([None, 10.0, 20.0]) == {"n": 2, "p50": 10.0, "p95": 20.0}
    assert latency_summary([]) == {"n": 0, "p50": None, "p95": None}


async def test_streams_over_the_real_generator_are_valid_and_report_latency_per_stage(cases):
    delays = {"retrieval": 0.02, "generation": 0.04, "validation": 0.01}
    records = [
        await stream_eval.run_stream(c.id, run_pipeline=stream_eval.stub_pipeline(c, delays_s=delays), request_id="a" * 32)
        for c in list(cases.values())[:6]
    ]
    summary = stream_eval.summarise_streams(records)
    assert summary["n_streams"] == 6 and summary["valid_stream_rate"] == 1.0 and summary["final_rate"] == 1.0
    assert summary["error_rate"] == 0.0 and summary["invalid_streams"] == []
    assert summary["stage_ms"]["generation"]["p50"] == pytest.approx(40.0) and summary["stage_ms"]["generation"]["n"] == 6
    assert summary["stage_ms"]["translate_in"] == {"n": 0, "p50": None, "p95": None}
    assert summary["ttfb_ms"]["p95"] < summary["terminal_ms"]["p50"]
    assert summary["terminal_ms"]["p50"] >= 70  # suma de las esperas simuladas


async def test_pipeline_failures_still_produce_valid_error_streams(cases):
    from services.legal_queries import PipelineError

    async def fail(_on_stage):
        raise PipelineError(503, "Legal retrieval unavailable", "RETRIEVAL_UNAVAILABLE")

    async def hang(_on_stage):
        import asyncio

        await asyncio.sleep(30)

    case = next(iter(cases.values()))
    failed = await stream_eval.run_stream(case.id, run_pipeline=fail)
    timed_out = await stream_eval.run_stream(case.id, run_pipeline=hang, timeout_s=0.05)
    summary = stream_eval.summarise_streams([failed, timed_out])
    assert summary["valid_stream_rate"] == 1.0 and summary["error_rate"] == 1.0 and summary["final_rate"] == 0.0
    assert summary["error_codes"] == {"RETRIEVAL_UNAVAILABLE": 1, "TIMEOUT": 1}


def test_summary_is_na_for_an_empty_run():
    summary = stream_eval.summarise_streams([])
    assert summary["valid_stream_rate"] is None and summary["ttfb_ms"]["p95"] is None


async def test_stream_suite_writes_a_report_with_reproducibility_metadata(tmp_path):
    path, report = await runner.run_stream_suite(results_dir=tmp_path, limit=5)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["meta"]["answer_source"] == "stub_pipeline" and saved["source"] == "offline"
    assert saved["n_streams"] == 5 and saved["valid_stream_rate"] == 1.0 and report["invalid_streams"] == []
    assert set(saved["stage_ms"]) == {"translate_in", "retrieval", "generation", "validation", "translate_out"}


def test_client_telemetry_schema_is_numbers_only():
    item = StreamTelemetry.model_validate({"request_id": "a" * 32, "outcome": "final", "ttfb_ms": 12.5, "total_ms": 900, "stage_ms": {"retrieval": 100.0}})
    assert item.degraded is False and item.lines_invalid == 0
    for bad in (
        {"request_id": "a" * 32, "outcome": "final", "query": "texto privado"},
        {"request_id": "no-hex", "outcome": "final"},
        {"request_id": "a" * 32, "outcome": "desconocido"},
        {"request_id": "a" * 32, "outcome": "final", "ttfb_ms": -1},
        {"request_id": "a" * 32, "outcome": "final", "stage_ms": {"inventada": 1.0}},
        {"request_id": "a" * 32, "outcome": "final", "stage_ms": {"retrieval": 10**9}},
        {"request_id": "a" * 32, "outcome": "final", "lines_invalid": 10**7},
    ):
        with pytest.raises(ValueError):
            StreamTelemetry.model_validate(bad)


def test_stream_metrics_aggregate_percentiles_outcomes_and_lines_and_stay_bounded():
    metrics = StreamMetrics(max_records=3)
    for index, total in enumerate((100, 200, 300, 400)):
        metrics.record(StreamTelemetry(request_id=f"{index:032x}", outcome="final" if index < 3 else "error",
                                       error_code=None if index < 3 else "TIMEOUT", ttfb_ms=10 + index, total_ms=total,
                                       stage_ms={"retrieval": 50.0 * (index + 1)}, lines_invalid=index))
    summary = metrics.summary()
    assert summary["n"] == 3 and summary["total_ms"] == {"n": 3, "p50": 300, "p95": 400}
    assert summary["outcomes"] == {"final": 2, "error": 1} and summary["error_codes"] == {"TIMEOUT": 1}
    assert summary["stage_ms"]["retrieval"]["p95"] == 200.0 and summary["stage_ms"]["generation"]["n"] == 0
    assert summary["lines"]["invalid"] == 1 + 2 + 3
    metrics.clear()
    assert metrics.summary()["n"] == 0 and metrics.summary()["total_ms"]["p50"] is None
