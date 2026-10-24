"""Contrato NDJSON v1: eventos válidos, archivos exportados al día y mensajes fijos."""

import json
import sys
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from models.stream_events import (
    ERROR_MESSAGES,
    RETRYABLE_CODES,
    ErrorCode,
    parse_stream_event,
)

ROOT = Path(__file__).resolve().parents[3]


def event(**fields):
    return {"v": 1, "seq": 0, "request_id": "r1", **fields}


@pytest.mark.parametrize(
    "payload",
    [
        event(type="meta", data={"language": "spanish"}),
        event(type="stage", stage="retrieval", status="start"),
        event(type="stage", stage="generation", status="end", elapsed_ms=12.5),
        event(type="chunk", delta="Artículo único"),
        event(type="final", data={"success": True}),
        event(type="error", code="TIMEOUT", message="x", retryable=True),
        event(type="done"),
    ],
)
def test_valid_events_round_trip(payload):
    parsed = parse_stream_event(json.dumps(payload))
    assert parsed.model_dump(exclude_none=True) == payload


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "chunk", "delta": "sin versión ni seq"},
        event(type="chunk"),
        event(type="chunk", delta="x", extra="campo no permitido"),
        event(type="stage", stage="inventada", status="start"),
        event(type="error", code="OTRO", message="x", retryable=False),
        event(type="desconocido"),
        {**event(type="done"), "v": 2},
        {**event(type="done"), "seq": -1},
    ],
)
def test_invalid_events_are_rejected(payload):
    with pytest.raises(ValidationError):
        parse_stream_event(payload)


def test_every_error_code_has_fixed_message_and_retry_policy():
    assert set(get_args(ErrorCode)) == set(ERROR_MESSAGES)
    assert RETRYABLE_CODES < set(ERROR_MESSAGES)
    assert "INTERNAL_ERROR" not in RETRYABLE_CODES


def test_exported_schema_and_typescript_are_up_to_date():
    sys.path.insert(0, str(ROOT / "backend" / "scripts"))
    try:
        import export_stream_contract
    finally:
        sys.path.pop(0)
    assert export_stream_contract.main(["--check"]) == 0
