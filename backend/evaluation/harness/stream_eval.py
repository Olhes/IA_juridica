"""Calidad del stream NDJSON: validez del contrato y latencia por etapa (p50/p95).

``run_stream`` ejecuta el generador real (``stream_legal_query`` + ``StreamGuard``) para una
consulta, anota cuándo llega cada línea y valida lo entregado contra el esquema. Con un
``pipeline`` simulado (sin esperas) mide el costo propio del stream; con el pipeline real
(``--run-model-evals``) mide la latencia de punta a punta por etapa.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from models.stream_events import parse_stream_event
from services.legal_stream import stream_legal_query
from services.stream_guard import guard_stream
from services.stream_telemetry import latency_summary

STAGES = ("translate_in", "retrieval", "generation", "validation", "translate_out")


@dataclass
class StreamRecord:
    case_id: str
    lines: list = field(default_factory=list)
    arrivals_ms: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    @property
    def events(self) -> list:
        return [json.loads(line) for line in self.lines]


def _text_of(final_data: dict) -> str:
    from services.legal_queries import response_text

    return response_text(final_data.get("response"), "spanish")


def check_contract(lines) -> list:
    """Problemas de un stream ya entregado: esquema, orden, terminal único, done, chunk == final."""
    problems, seen_terminal, done, chunk, expected_seq, request_id = [], 0, False, None, 0, None
    for index, line in enumerate(lines):
        try:
            event = parse_stream_event(line)
        except ValueError:
            problems.append(f"línea {index}: no cumple el esquema")
            continue
        if done:
            problems.append("hay eventos después de `done`")
        if event.seq != expected_seq:
            problems.append(f"`seq` {event.seq} en lugar de {expected_seq}")
        expected_seq = event.seq + 1
        request_id = request_id or event.request_id
        if event.request_id != request_id:
            problems.append("cambió el `request_id`")
        if index == 0 and event.type != "meta":
            problems.append("el primer evento no es `meta`")
        if event.type == "chunk":
            chunk = event.delta
        elif event.type in {"final", "error"}:
            seen_terminal += 1
            if event.type == "final" and chunk is not None and chunk != _text_of(event.data):
                problems.append("`chunk` y `final` no coinciden")
        elif event.type == "done":
            done = True
    if seen_terminal != 1:
        problems.append(f"{seen_terminal} eventos terminales (se espera 1)")
    if not done:
        problems.append("falta `done`")
    return problems


async def run_stream(case_id, *, run_pipeline, language="spanish", request_id="0" * 32, timeout_s=120.0,
                     idle_timeout_s=135.0, clock=time.perf_counter) -> StreamRecord:
    async def persist(_result):
        return None

    source = stream_legal_query(run_pipeline=run_pipeline, extract_text=_text_of_result, persist=persist,
                                request_id=request_id, language=language, timeout_s=timeout_s)
    delivered = guard_stream(source, extract_text=_text_of, request_id=request_id, idle_timeout_s=idle_timeout_s)
    record = StreamRecord(case_id)
    started = clock()
    async for line in delivered:
        record.lines.append(line)
        record.arrivals_ms.append((clock() - started) * 1000)
    record.problems = check_contract(record.lines)
    return record


def _text_of_result(result: dict) -> str:
    from services.legal_queries import response_text

    return response_text(result.get("response"), "spanish")


def describe(record: StreamRecord) -> dict:
    """Números de un stream: tiempos de llegada, terminal y duración por etapa."""
    events = record.events
    terminal = next((e for e in events if e["type"] in {"final", "error"}), None)
    terminal_ms = next((t for e, t in zip(events, record.arrivals_ms) if e["type"] in {"final", "error"}), None)
    first_stage = next((t for e, t in zip(events, record.arrivals_ms) if e["type"] == "stage"), None)
    chunk_ms = next((t for e, t in zip(events, record.arrivals_ms) if e["type"] == "chunk"), None)
    stage_ms: dict = {}
    for event in events:
        if event["type"] == "stage" and event["status"] == "end" and "elapsed_ms" in event:
            stage_ms[event["stage"]] = stage_ms.get(event["stage"], 0.0) + event["elapsed_ms"]
    return {
        "case_id": record.case_id,
        "valid": not record.problems,
        "problems": record.problems,
        "terminal": terminal["type"] if terminal else None,
        "error_code": terminal.get("code") if terminal else None,
        "ttfb_ms": record.arrivals_ms[0] if record.arrivals_ms else None,
        "first_stage_ms": first_stage,
        "text_ms": chunk_ms,
        "terminal_ms": terminal_ms,
        "stage_ms": stage_ms,
        "events": len(events),
    }


def summarise_streams(records) -> dict:
    """Tasas de validez y latencia p50/p95 (``n/a`` = ``None`` si no hay datos)."""
    rows = [describe(r) for r in records]
    n = len(rows)
    rate = lambda hit: (sum(1 for row in rows if hit(row)) / n) if n else None  # noqa: E731
    return {
        "n_streams": n,
        "valid_stream_rate": rate(lambda r: r["valid"]),
        "final_rate": rate(lambda r: r["terminal"] == "final"),
        "error_rate": rate(lambda r: r["terminal"] == "error"),
        "error_codes": _count(r["error_code"] for r in rows if r["error_code"]),
        "ttfb_ms": latency_summary(r["ttfb_ms"] for r in rows),
        "first_stage_ms": latency_summary(r["first_stage_ms"] for r in rows),
        "text_ms": latency_summary(r["text_ms"] for r in rows),
        "terminal_ms": latency_summary(r["terminal_ms"] for r in rows),
        "stage_ms": {stage: latency_summary(r["stage_ms"].get(stage) for r in rows) for stage in STAGES},
        "invalid_streams": [{"case_id": r["case_id"], "problems": r["problems"]} for r in rows if not r["valid"]],
    }


def _count(items) -> dict:
    counts: dict = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts


def stub_pipeline(case, *, delays_s: Optional[dict] = None):
    """Pipeline simulado (sin modelos) que emite las etapas reales con esperas opcionales."""
    delays_s = delays_s or {}

    async def run(on_stage):
        for stage in ("retrieval", "generation", "validation"):
            await on_stage({"stage": stage, "status": "start"})
            await asyncio.sleep(delays_s.get(stage, 0))
            await on_stage({"stage": stage, "status": "end", "elapsed_ms": delays_s.get(stage, 0) * 1000})
        text = " ".join(f.text for f in case.required_facts) or "No hay evidencia suficiente en el corpus."
        return {"success": True, "response": {"respuesta_espanol": text}, "sources": [], "validation": {},
                "metadata": {"evidence_status": "retrieved", "timings": {"total_ms": 0.0, "stages": {}, "cache_hit": False}}}

    return run
