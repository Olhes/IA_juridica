"""StreamGuard: contrato garantizado pase lo que pase aguas arriba (esquema, terminal único, chunk == final)."""

import asyncio
import json
import random

import pytest

from evaluation.harness.stream_fixtures import FINAL_TEXT, REQUEST_ID, dumps, valid_events
from models.stream_events import parse_stream_event
from services.stream_guard import StreamGuard, guard_stream


def text_of(data):
    return data["response"]["respuesta_espanol"]


def guard():
    return StreamGuard(extract_text=text_of, request_id=REQUEST_ID)


def feed_all(lines):
    instance, out = guard(), []
    for line in lines:
        out.extend(instance.feed(line))
        if instance.finished:
            break
    out.extend(instance.close())
    return instance, [json.loads(line) for line in out]


def lines_of(events):
    return [dumps(e) for e in events]


def assert_contract(events):
    """Invariantes que el cliente puede asumir de todo stream entregado."""
    assert [e["seq"] for e in events] == list(range(len(events)))
    assert len({e["request_id"] for e in events}) == 1
    assert events[0]["type"] == "meta" and events[-1]["type"] == "done"
    assert sum(e["type"] in {"final", "error"} for e in events) == 1
    assert sum(e["type"] == "done" for e in events) == 1
    terminal = next(i for i, e in enumerate(events) if e["type"] in {"final", "error"})
    assert all(e["type"] != "chunk" for e in events[terminal + 1 :])
    for event in events:
        parse_stream_event(event)
    finals = [e for e in events if e["type"] == "final"]
    chunks = [e for e in events if e["type"] == "chunk"]
    if finals and chunks:
        assert chunks[0]["delta"] == text_of(finals[0]["data"])


def test_a_valid_stream_passes_through_unchanged():
    instance, out = feed_all(lines_of(valid_events()))
    assert instance.violations == [] and out == valid_events()
    assert_contract(out)


def test_chunk_is_held_until_its_final_and_dropped_if_the_texts_differ():
    events = valid_events()
    instance = guard()
    emitted = [instance.feed(dumps(e)) for e in events[:8]]
    assert emitted[-1] == []  # el chunk espera a su final
    mismatched = events[7] | {"delta": "Texto distinto del final validado"}
    instance, out = feed_all(lines_of(events[:7] + [mismatched] + events[8:]))
    assert instance.violations == ["chunk_final_mismatch"]
    assert [e["type"] for e in out][-2:] == ["error", "done"] and all(e["type"] != "chunk" for e in out)
    assert out[-2]["code"] == "INTERNAL_ERROR" and "Texto distinto" not in json.dumps(out)
    assert_contract(out)


@pytest.mark.parametrize(
    ("mutation", "violation"),
    [
        (lambda e: e[:1] + [dict(e[1], extra="no permitido")] + e[2:], "invalid_event"),
        (lambda e: e[:1] + [dict(e[1], request_id="f" * 32)] + e[2:], "request_id_changed"),
        (lambda e: e[1:], "meta_missing"),
        (lambda e: e[:1] + [e[0]] + e[1:], "duplicate_meta"),
        (lambda e: e[:7] + [e[7], e[7]] + e[8:], "multiple_chunks"),
        (lambda e: e[:8] + [e[9]], "done_without_terminal"),
    ],
)
def test_violations_are_reported_and_the_client_gets_a_single_error_then_done(mutation, violation):
    instance, out = feed_all(lines_of(mutation(valid_events())))
    assert violation in instance.violations
    assert out[-2]["type"] == "error" and out[-1]["type"] == "done"
    assert_contract(out)


def test_events_after_the_terminal_are_dropped_but_the_delivered_final_is_kept():
    events = valid_events()
    noisy = events[:9] + [events[2] | {"seq": 9}, events[9] | {"seq": 10}]
    instance, out = feed_all(lines_of(noisy))
    assert instance.violations == ["event_after_terminal"]
    assert [e["type"] for e in out][-2:] == ["final", "done"] and all(e["type"] != "error" for e in out)
    assert_contract(out)


def test_the_client_always_sees_meta_first_even_if_the_source_never_sent_it():
    instance, out = feed_all(lines_of(valid_events()[1:]))
    assert instance.violations == ["meta_missing"]
    assert [e["type"] for e in out] == ["meta", "error", "done"] and out[0]["data"] == {"language": "unknown"}
    assert_contract(out)


def test_garbage_lines_and_missing_terminal_are_closed_with_an_error():
    instance, out = feed_all(["{esto no es json"])
    assert instance.violations == ["invalid_event"] and [e["type"] for e in out] == ["meta", "error", "done"]
    instance, out = feed_all(lines_of(valid_events()[:4]))
    assert "stream_ended_without_terminal" in instance.violations
    assert [e["type"] for e in out] == ["meta", "stage", "stage", "stage", "error", "done"][: len(out)]
    assert_contract(out)


def test_an_upstream_error_is_passed_on_and_its_done_is_kept():
    events = [valid_events()[0], valid_events()[1], dict(valid_events()[0], seq=2, type="error", code="TIMEOUT", message="x", retryable=True), valid_events()[9] | {"seq": 3}]
    events[2].pop("data")
    instance, out = feed_all(lines_of(events))
    assert instance.violations == [] and out[-2]["code"] == "TIMEOUT"
    assert_contract(out)


def test_seq_is_renumbered_by_the_guard_not_trusted_from_upstream():
    events = valid_events()
    gap = [e | {"seq": e["seq"] * 3} for e in events]
    instance, out = feed_all(lines_of(gap))
    assert [e["seq"] for e in out] == list(range(10)) and instance.violations == []


def test_fuzz_mutated_streams_always_satisfy_the_contract():
    rnd = random.Random(2026)
    base = lines_of(valid_events())
    for _ in range(400):
        lines = list(base)
        for _ in range(rnd.randint(1, 4)):
            if not lines:
                break
            op, at = rnd.choice(["drop", "dup", "swap", "corrupt", "truncate", "foreign", "text"]), rnd.randrange(len(lines))
            if op == "drop":
                lines.pop(at)
            elif op == "dup":
                lines.insert(at, lines[at])
            elif op == "swap" and at + 1 < len(lines):
                lines[at], lines[at + 1] = lines[at + 1], lines[at]
            elif op == "corrupt":
                lines[at] = lines[at][: rnd.randrange(len(lines[at]) + 1)] + rnd.choice(["}", "{", "\x00", "ñ"])
            elif op == "truncate":
                lines = lines[:at]
            elif op == "foreign":
                lines[at] = lines[at].replace(REQUEST_ID, "f" * 32)
            else:
                lines[at] = lines[at].replace(FINAL_TEXT, "otro texto")
        instance, out = feed_all(lines)
        assert_contract(out)
        # El ruido posterior a un `final` ya entregado se descarta; cualquier otra violación cierra con `error`.
        if instance.violations and not any(e["type"] == "final" for e in out):
            assert any(e["type"] == "error" for e in out)


async def agen(lines, stall=None):
    for line in lines:
        yield line
    if stall:
        await asyncio.sleep(stall)


async def collect(source, **kwargs):
    options = dict(extract_text=text_of, request_id=REQUEST_ID, idle_timeout_s=5)
    options.update(kwargs)
    return [json.loads(line) async for line in guard_stream(source, **options)]


async def test_guard_stream_delivers_valid_streams_and_closes_short_ones():
    assert await collect(agen(lines_of(valid_events()))) == valid_events()
    out = await collect(agen(lines_of(valid_events()[:3])))
    assert [e["type"] for e in out][-2:] == ["error", "done"]
    assert_contract(out)


async def test_watchdog_emits_a_retryable_timeout_when_the_source_goes_silent():
    out = await collect(agen(lines_of(valid_events()[:2]), stall=30), idle_timeout_s=0.05)
    assert [e["type"] for e in out][-2:] == ["error", "done"]
    assert out[-2]["code"] == "TIMEOUT" and out[-2]["retryable"] is True
    assert_contract(out)


async def test_the_source_is_closed_when_the_guard_stops_early():
    closed = asyncio.Event()

    async def source():
        try:
            for line in lines_of(valid_events()):
                yield line
            yield "{no es json"
        finally:
            closed.set()

    assert (await collect(source()))[-1]["type"] == "done"
    assert closed.is_set()
