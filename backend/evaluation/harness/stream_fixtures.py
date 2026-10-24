"""Streams NDJSON rotos de referencia (``tests/backend/fixtures/gold/ndjson_broken/``).

Los consumen pytest (``StreamGuard`` y la validación de contrato), vitest (el analizador del
cliente) y Playwright (la interfaz). El generador es la fuente de verdad: los archivos y el
``manifest.json`` se regeneran con ``python -m evaluation.harness.stream_fixtures`` y un test
comprueba que no se editaron a mano. ``expected`` describe qué debe concluir un cliente
robusto al leer **el texto completo** del archivo.
"""

import json
from pathlib import Path

from evaluation.harness.gold import GOLD_DIR

FIXTURES_DIR = GOLD_DIR / "ndjson_broken"
REQUEST_ID = "0123456789abcdef0123456789abcdef"
OTHER_REQUEST_ID = "fedcba9876543210fedcba9876543210"
FINAL_TEXT = "Respuesta final validada ñ 🦙"
CHUNK_ONLY_TEXT = "Texto recibido sin validación final"

FINAL_DATA = {
    "success": True,
    "query": "Consulta sintética",
    "language": "spanish",
    "cached": False,
    "response": {"respuesta_espanol": FINAL_TEXT, "respuesta_quechua": "Kutichiy"},
    "sources": ["fuente.md"],
    "validation": {"status": "passed", "is_reliable": True},
    "metadata": {
        "evidence_status": "retrieved",
        "timings": {"total_ms": 321.5, "stages": {"retrieval": 100.0, "generation": 150.0, "validation": 40.0}, "cache_hit": False},
    },
}


def event(seq, type_, request_id=REQUEST_ID, **fields):
    return {"v": 1, "seq": seq, "request_id": request_id, "type": type_, **fields}


def valid_events(text=FINAL_TEXT, request_id=REQUEST_ID):
    data = json.loads(json.dumps(FINAL_DATA))
    data["response"]["respuesta_espanol"] = text
    return [
        event(0, "meta", request_id, data={"language": "spanish"}),
        event(1, "stage", request_id, stage="retrieval", status="start"),
        event(2, "stage", request_id, stage="retrieval", status="end", elapsed_ms=100.0),
        event(3, "stage", request_id, stage="generation", status="start"),
        event(4, "stage", request_id, stage="generation", status="end", elapsed_ms=150.0),
        event(5, "stage", request_id, stage="validation", status="start"),
        event(6, "stage", request_id, stage="validation", status="end", elapsed_ms=40.0),
        event(7, "chunk", request_id, delta=text),
        event(8, "final", request_id, data=data),
        event(9, "done", request_id),
    ]


def dumps(item):
    return json.dumps(item, ensure_ascii=False, separators=(",", ":"))


def render(events, eol="\n"):
    return "".join(dumps(e) + eol for e in events)


def _expected(**overrides):
    base = {
        "final_text": FINAL_TEXT, "chunk_text": FINAL_TEXT, "degraded": False, "incomplete": False, "error_code": None,
        "missing_done": False, "invalid": 0, "repaired": 0, "duplicates": 0, "unsupported": 0, "legacy": 0,
        "out_of_order": 0, "valid": 10,
    }
    base.update(overrides)
    return base


def build() -> dict:
    """``{nombre: (texto, descripción, esperado)}``."""
    ok = valid_events()
    lines = [dumps(e) for e in ok]
    cases = {}
    cases["valid.ndjson"] = ("".join(line + "\n" for line in lines), "Stream correcto de referencia.", _expected())
    cases["bom_crlf.ndjson"] = ("﻿" + render(ok, "\r\n"), "BOM al inicio y saltos de línea CRLF.", _expected())
    garbage = lines[:4] + ["{esto no es json", ""] + lines[4:]
    cases["invalid_line.ndjson"] = ("\n".join(garbage) + "\n", "Una línea basura entre eventos válidos.", _expected(invalid=1))
    prefixed = lines[:1] + ["data: " + lines[1]] + lines[2:]
    cases["repairable_prefix.ndjson"] = ("\n".join(prefixed) + "\n", "Un evento con el prefijo `data: ` de SSE.", _expected(repaired=1))
    glued = lines[:2] + [lines[2] + lines[3]] + lines[4:]
    cases["concatenated_objects.ndjson"] = ("\n".join(glued) + "\n", "Dos eventos pegados en una línea (salto perdido).", _expected(repaired=1))
    truncated = lines[:8] + [lines[8][: len(lines[8]) // 2]]
    cases["truncated_final.ndjson"] = ("\n".join(truncated), "El stream se corta a mitad del `final`.",
                                       _expected(final_text=None, degraded=True, missing_done=True, invalid=1, valid=8))
    no_final = lines[:8] + [lines[9]]
    cases["missing_final.ndjson"] = ("\n".join(no_final) + "\n", "Hay `chunk` y `done`, pero no `final`.",
                                     _expected(final_text=None, degraded=True, valid=9))
    dup = lines[:5] + [lines[4]] + lines[5:]
    cases["duplicate_events.ndjson"] = ("\n".join(dup) + "\n", "Un evento repetido (mismo `seq`).", _expected(duplicates=1))
    shuffled = [lines[i] for i in (2, 0, 1, 4, 3, 6, 5, 7, 9, 8)]
    cases["out_of_order.ndjson"] = ("\n".join(shuffled) + "\n", "Líneas desordenadas dentro de una misma lectura.", _expected())
    err = [event(0, "meta", data={"language": "spanish"}), event(1, "stage", stage="retrieval", status="start"),
           event(2, "error", code="TIMEOUT", message="Legal query timed out", retryable=True), event(3, "done")]
    cases["error_event.ndjson"] = (render(err), "Error terminal `TIMEOUT` reintentable.",
                                   _expected(final_text=None, chunk_text="", error_code="TIMEOUT", valid=4))
    future = [dict(e, v=2) for e in ok]
    cases["unsupported_version.ndjson"] = (render(future), "Todos los eventos con `v: 2`.",
                                           _expected(final_text=None, chunk_text="", incomplete=True, unsupported=10, valid=0, missing_done=False))
    legacy = [{"type": "chunk", "delta": FINAL_TEXT}, {"type": "final", "data": FINAL_DATA}]
    cases["legacy_no_seq.ndjson"] = (render(legacy), "Servidor antiguo: eventos sin `v` ni `seq`.", _expected(legacy=2, valid=2))
    cases["empty.ndjson"] = ("", "Respuesta vacía.", _expected(final_text=None, chunk_text="", incomplete=True, valid=0))
    mixed = lines[:3] + [dumps(event(3, "stage", OTHER_REQUEST_ID, stage="generation", status="start"))] + lines[3:]
    cases["foreign_request_id.ndjson"] = ("\n".join(mixed) + "\n", "Un evento de otra petición (distinto `request_id`).", _expected(invalid=1))
    cases["only_stages.ndjson"] = (render(ok[:4]), "Solo `meta` y etapas; el stream termina sin terminal.",
                                   _expected(final_text=None, chunk_text="", incomplete=True, missing_done=True, valid=4))
    return cases


def write(directory=FIXTURES_DIR) -> list:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, (text, description, expected) in build().items():
        (directory / name).write_bytes(text.encode("utf-8"))
        manifest[name] = {"description": description, "expected": expected}
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return sorted(manifest)


if __name__ == "__main__":
    print(f"{len(write())} streams escritos en {FIXTURES_DIR}")
