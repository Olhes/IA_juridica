"""Exporta el contrato NDJSON v1 a JSON Schema y a tipos TypeScript.

Uso:  uv run python backend/scripts/export_stream_contract.py [--check]

`--check` no escribe: falla si los archivos generados no coinciden con
`backend/models/stream_events.py` (lo ejecuta también un test).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from models.stream_events import STREAM_EVENT_ADAPTER  # noqa: E402

SCHEMA_PATH = ROOT / "backend" / "contracts" / "stream_event.v1.schema.json"
TS_PATH = ROOT / "frontend" / "src" / "domain" / "legal" / "streamEvents.generated.ts"


def _ts_type(schema, defs):
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(_ts_type(s, defs) for s in schema["anyOf"])
    kind = schema.get("type")
    if kind == "string":
        return "string"
    if kind in ("integer", "number"):
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "null":
        return "null"
    if kind == "object":
        return "Record<string, unknown>"
    raise ValueError(f"Tipo JSON Schema no soportado: {schema}")


def build_typescript(schema) -> str:
    defs = schema["$defs"]
    lines = [
        "// Generado por backend/scripts/export_stream_contract.py. No editar a mano.",
        "",
        "export const STREAM_CONTRACT_VERSION = 1;",
        "",
    ]
    for name, definition in defs.items():
        if "enum" in definition:
            lines.append(f"export type {name} = {_ts_type(definition, defs)};")
            lines.append("")
            continue
        lines.append(f"export interface {name} {{")
        required = set(definition.get("required", []))
        for field, spec in definition["properties"].items():
            optional = "" if field in required else "?"
            if field in ("v", "type") and "default" in spec:
                optional = ""
            lines.append(f"  {field}{optional}: {_ts_type(spec, defs)};")
        lines.append("}")
        lines.append("")
    union = " | ".join(ref["$ref"].rsplit("/", 1)[-1] for ref in schema["oneOf"])
    lines.append(f"export type StreamEvent = {union};")
    lines.append("")
    return "\n".join(lines)


def build_schema():
    raw = STREAM_EVENT_ADAPTER.json_schema()
    # `oneOf` explícito y sin el `discriminator` de OpenAPI, para que lo consuma cualquier validador.
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "StreamEvent",
        "description": "Contrato NDJSON v1 de /legal-query-stream",
        "oneOf": raw.get("oneOf") or raw["anyOf"],
        "$defs": raw["$defs"],
    }
    return schema


def render():
    schema = build_schema()
    return (
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        build_typescript(schema),
    )


def main(argv):
    schema_text, ts_text = render()
    if "--check" in argv:
        stale = [
            str(path.relative_to(ROOT))
            for path, text in ((SCHEMA_PATH, schema_text), (TS_PATH, ts_text))
            if not path.exists() or path.read_text(encoding="utf-8").replace("\r\n", "\n") != text
        ]
        if stale:
            print("Contrato desactualizado:", ", ".join(stale))
            return 1
        return 0
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    TS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(schema_text, encoding="utf-8", newline="\n")
    TS_PATH.write_text(ts_text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
