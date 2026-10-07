"""Regresiones para timestamps independientes de la zona horaria del host."""

import ast
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, call

import pytest

from modules.validation.services.schemas import ValidationReport
from utils.file_utils import FileUtils

redis_module = importlib.import_module("database.redis_adapter")
FIXED_TIME = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("offset_hours", [-5, 0, 5.5])
async def test_rate_limit_scores_use_real_epoch_in_any_host_timezone(
    monkeypatch, offset_hours
):
    local_zone = timezone(timedelta(hours=offset_hours))

    class LocalNaiveDatetime(datetime):
        def timestamp(self):
            # Simula la interpretación local de un datetime sin zona, incluso en Windows.
            return datetime.timestamp(self.replace(tzinfo=local_zone))

    naive_utc = LocalNaiveDatetime(2026, 10, 6, 12, 0)
    clock = SimpleNamespace(
        now=Mock(return_value=FIXED_TIME), utcnow=Mock(return_value=naive_utc)
    )
    monkeypatch.setattr(redis_module, "datetime", clock)
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=[0, 2, 1, True])
    adapter = redis_module.RedisAdapter()
    adapter.client = SimpleNamespace(pipeline=Mock(return_value=pipe))

    result = await adapter.check_rate_limit("user", limit=3, window_seconds=60)

    epoch = FIXED_TIME.timestamp()
    pipe.zremrangebyscore.assert_called_once_with("rate_limit:user", 0, epoch - 60)
    pipe.zadd.assert_called_once_with("rate_limit:user", {str(epoch): epoch})
    pipe.expire.assert_called_once_with("rate_limit:user", 60)
    assert result == {
        "allowed": True,
        "current": 2,
        "limit": 3,
        "remaining": 0,
        "reset_time": epoch + 60,
    }
    clock.now.assert_called_once_with(timezone.utc)
    clock.utcnow.assert_not_called()


@pytest.mark.parametrize("failure_stage", [None, "ping", "info"])
async def test_redis_health_reports_explicit_utc_in_success_and_failure(
    monkeypatch, failure_stage
):
    end_time = FIXED_TIME + timedelta(milliseconds=2)
    clock = SimpleNamespace(
        now=Mock(side_effect=[FIXED_TIME, end_time, end_time]),
        utcnow=Mock(return_value=FIXED_TIME.replace(tzinfo=None)),
    )
    monkeypatch.setattr(redis_module, "datetime", clock)
    adapter = redis_module.RedisAdapter()
    adapter.client = SimpleNamespace(
        ping=AsyncMock(), info=AsyncMock(return_value={"redis_version": "7"})
    )
    if failure_stage:
        getattr(adapter.client, failure_stage).side_effect = RuntimeError("unavailable")

    result = await adapter.health_check()

    assert result["status"] == ("unhealthy" if failure_stage else "healthy")
    assert datetime.fromisoformat(result["timestamp"]) == end_time
    assert datetime.fromisoformat(result["timestamp"]).tzinfo == timezone.utc
    if not failure_stage:
        assert result["response_time_ms"] == pytest.approx(2)
    assert all(args == call(timezone.utc) for args in clock.now.call_args_list)
    clock.utcnow.assert_not_called()


def test_validation_report_default_is_fresh_utc_for_each_instance(monkeypatch):
    schemas = importlib.import_module("modules.validation.services.schemas")
    later = FIXED_TIME + timedelta(seconds=1)
    clock = SimpleNamespace(now=Mock(side_effect=[FIXED_TIME, later]))
    monkeypatch.setattr(schemas, "datetime", clock)
    fields = dict(
        status="passed",
        confidence="high",
        confidence_score=0.9,
        hallucination_risk=0.1,
        is_grounded=True,
    )

    first = ValidationReport(**fields)
    second = ValidationReport(**fields)

    assert first.validated_at == FIXED_TIME
    assert second.validated_at == later
    assert first.validated_at.tzinfo == timezone.utc
    serialized = json.loads(first.model_dump_json())["validated_at"]
    assert datetime.fromisoformat(serialized) == FIXED_TIME
    assert clock.now.call_args_list == [call(timezone.utc), call(timezone.utc)]


def test_file_modification_time_is_serialized_as_utc(tmp_path):
    file_path = tmp_path / "document.txt"
    file_path.write_text("document", encoding="utf-8")
    timestamp = 1571595618.0
    os.utime(file_path, (timestamp, timestamp))

    result = FileUtils().validate_file(str(file_path))

    assert result["is_valid"] is True
    assert (
        result["file_info"]["modified"]
        == datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    )


def test_backend_does_not_use_naive_utc_factories_or_timestamp_conversions():
    backend = Path(__file__).resolve().parents[3] / "backend"
    issues = []
    for path in backend.rglob("*.py"):
        if any(part in {".venv", "__pycache__"} for part in path.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {
                "utcnow",
                "utcfromtimestamp",
            }:
                issues.append(f"{path.relative_to(backend)}:{node.lineno}: {node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "fromtimestamp":
                    has_zone = len(node.args) >= 2 or any(
                        kw.arg == "tz"
                        and not (
                            isinstance(kw.value, ast.Constant)
                            and kw.value.value is None
                        )
                        for kw in node.keywords
                    )
                    if not has_zone:
                        issues.append(
                            f"{path.relative_to(backend)}:{node.lineno}: fromtimestamp without timezone"
                        )
    assert issues == []
