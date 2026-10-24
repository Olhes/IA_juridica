"""POST /telemetry/stream (solo números), su resumen administrativo y el stream HTTP real bajo StreamGuard."""

import json

import pytest

from evaluation.harness.stream_eval import check_contract
from services.stream_telemetry import stream_metrics

ADMIN = {"X-API-Key": "offline-admin-key"}
REQUEST_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def clean_metrics():
    stream_metrics.clear()
    yield
    stream_metrics.clear()


def body(**overrides):
    return json.dumps({"request_id": REQUEST_ID, "outcome": "final", "ttfb_ms": 12.5, "total_ms": 900.0,
                       "stage_ms": {"retrieval": 100.0, "generation": 500.0}, "lines_valid": 10, **overrides})


def test_valid_telemetry_is_accepted_without_a_session_and_with_plain_text_bodies(api):
    client, _, _ = api
    response = client.post("/telemetry/stream", content=body(), headers={"Content-Type": "text/plain;charset=UTF-8"})
    assert response.status_code == 204 and response.content == b""
    assert client.post("/telemetry/stream", content=body(request_id="f" * 32), headers={"Content-Type": "application/json"}).status_code == 204
    assert stream_metrics.summary()["n"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        body(query="texto privado del usuario"),
        body(response="texto de la respuesta"),
        body(request_id="no-es-un-id"),
        body(outcome="inventado"),
        body(ttfb_ms=-5),
        "{ no es json",
        "[]",
        "",
    ],
)
def test_telemetry_with_text_or_invalid_numbers_is_rejected_and_never_stored(api, payload):
    client, _, _ = api
    response = client.post("/telemetry/stream", content=payload, headers={"Content-Type": "text/plain"})
    assert response.status_code == 422
    assert "texto privado" not in response.text and stream_metrics.summary()["n"] == 0


def test_oversized_telemetry_is_rejected_with_413(api):
    client, _, _ = api
    assert client.post("/telemetry/stream", content=body(stage_ms={}) + " " * 5000).status_code == 413
    assert stream_metrics.summary()["n"] == 0


def test_summary_requires_the_admin_key_and_reports_p50_p95_per_stage(api):
    client, _, _ = api
    for index, total in enumerate((100.0, 200.0, 300.0)):
        client.post("/telemetry/stream", content=body(request_id=f"{index:032x}", total_ms=total, stage_ms={"retrieval": total / 2}))
    assert client.get("/telemetry/stream/summary").status_code == 403
    response = client.get("/telemetry/stream/summary", headers=ADMIN)
    summary = response.json()["summary"]
    assert response.status_code == 200 and summary["n"] == 3
    assert summary["total_ms"] == {"n": 3, "p50": 200.0, "p95": 300.0}
    assert summary["stage_ms"]["retrieval"]["p95"] == 150.0 and summary["stage_ms"]["validation"]["p50"] is None
    assert "texto" not in json.dumps(summary)


def test_the_http_stream_is_contract_valid_and_shares_the_request_id_header(api):
    client, _, optimizer = api
    optimizer.get_cached.return_value = {"response": {"respuesta_espanol": "Artículo local"}, "sources": ["licencia.md"], "validation": {"is_reliable": True}}
    client.post("/session/bootstrap")
    response = client.post("/legal-query-stream", json={"query": "licencia", "language": "spanish"})
    lines = [line for line in response.text.split("\n") if line]
    assert check_contract(lines) == []
    assert {json.loads(line)["request_id"] for line in lines} == {response.headers["X-Request-ID"]}
    assert response.text.endswith("\n") and "\r" not in response.text
