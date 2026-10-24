"""Telemetría del stream medida por el cliente: solo números y el ``request_id``.

``POST /telemetry/stream`` recibe un ``StreamTelemetry``; nunca texto de consultas ni de
respuestas (el esquema prohíbe campos extra). Se agrega en memoria (últimos ``MAX_RECORDS``)
para informar p50/p95 por etapa al panel de calidad; no se persiste ni se asocia a una persona.
"""

import math
import threading
from collections import Counter, deque
from typing import Literal, Optional, get_args

from pydantic import BaseModel, ConfigDict, Field

from models.stream_events import ErrorCode, StageName

MAX_RECORDS = 2000
MAX_MS = 600_000.0
Outcome = Literal["final", "degraded", "error", "aborted", "incomplete"]
LineCount = Field(default=0, ge=0, le=100_000)


class StreamTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    outcome: Outcome
    error_code: Optional[ErrorCode] = None
    ttfb_ms: Optional[float] = Field(default=None, ge=0, le=MAX_MS)
    total_ms: Optional[float] = Field(default=None, ge=0, le=MAX_MS)
    stage_ms: dict[StageName, float] = Field(default_factory=dict)
    lines_valid: int = LineCount
    lines_invalid: int = LineCount
    lines_repaired: int = LineCount
    lines_duplicate: int = LineCount
    lines_out_of_order: int = LineCount
    lines_legacy: int = LineCount
    degraded: bool = False

    def model_post_init(self, _context) -> None:
        if any(not 0 <= value <= MAX_MS for value in self.stage_ms.values()):
            raise ValueError("stage_ms fuera de rango")


def percentile(values, q: float) -> Optional[float]:
    """Percentil por rango más cercano; ``None`` si no hay datos (n/a, nunca 0)."""
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(math.ceil(q / 100 * len(ordered)) - 1, 0)]


def latency_summary(values) -> dict:
    values = [v for v in values if v is not None]
    return {"n": len(values), "p50": percentile(values, 50), "p95": percentile(values, 95)}


class StreamMetrics:
    def __init__(self, max_records: int = MAX_RECORDS):
        self._records: deque = deque(maxlen=max_records)
        self._lock = threading.Lock()

    def record(self, item: StreamTelemetry) -> None:
        with self._lock:
            self._records.append(item)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def summary(self) -> dict:
        with self._lock:
            records = list(self._records)
        stages = {name: latency_summary(r.stage_ms.get(name) for r in records) for name in get_args(StageName)}
        return {
            "n": len(records),
            "outcomes": dict(Counter(r.outcome for r in records)),
            "error_codes": dict(Counter(r.error_code for r in records if r.error_code)),
            "ttfb_ms": latency_summary(r.ttfb_ms for r in records),
            "total_ms": latency_summary(r.total_ms for r in records),
            "stage_ms": stages,
            "lines": {
                "valid": sum(r.lines_valid for r in records),
                "invalid": sum(r.lines_invalid for r in records),
                "repaired": sum(r.lines_repaired for r in records),
                "duplicate": sum(r.lines_duplicate for r in records),
                "out_of_order": sum(r.lines_out_of_order for r in records),
                "legacy": sum(r.lines_legacy for r in records),
            },
            "degraded": sum(r.degraded for r in records),
        }


stream_metrics = StreamMetrics()
