"""Contrato NDJSON v1 de `/legal-query-stream`.

Cada línea del stream es un `StreamEvent` con `{v, seq, request_id, type}`.
`scripts/export_stream_contract.py` exporta este módulo a JSON Schema y a tipos
TypeScript; un test falla si los archivos generados quedan desactualizados.
"""

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

STREAM_CONTRACT_VERSION = 1

StageName = Literal[
    "translate_in", "retrieval", "generation", "validation", "translate_out"
]
StageStatus = Literal["start", "end"]
ErrorCode = Literal[
    "RETRIEVAL_UNAVAILABLE",
    "GENERATION_UNAVAILABLE",
    "TRANSLATION_UNAVAILABLE",
    "TIMEOUT",
    "INTERNAL_ERROR",
]

# Mensajes fijos: un error nunca repite texto de la consulta ni de la excepción.
ERROR_MESSAGES: dict[str, str] = {
    "RETRIEVAL_UNAVAILABLE": "Legal retrieval unavailable",
    "GENERATION_UNAVAILABLE": "Legal response unavailable",
    "TRANSLATION_UNAVAILABLE": "Translation unavailable",
    "TIMEOUT": "Legal query timed out",
    "INTERNAL_ERROR": "Legal query stream failed",
}
RETRYABLE_CODES = frozenset(
    {"RETRIEVAL_UNAVAILABLE", "GENERATION_UNAVAILABLE", "TRANSLATION_UNAVAILABLE", "TIMEOUT"}
)


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: Literal[1] = STREAM_CONTRACT_VERSION
    seq: int = Field(ge=0)
    request_id: str


class MetaEvent(_Event):
    type: Literal["meta"] = "meta"
    data: dict[str, Any]


class StageEvent(_Event):
    type: Literal["stage"] = "stage"
    stage: StageName
    status: StageStatus
    elapsed_ms: float | None = Field(default=None, ge=0)


class ChunkEvent(_Event):
    type: Literal["chunk"] = "chunk"
    delta: str


class FinalEvent(_Event):
    type: Literal["final"] = "final"
    data: dict[str, Any]


class ErrorEvent(_Event):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str
    retryable: bool


class DoneEvent(_Event):
    type: Literal["done"] = "done"


StreamEvent = Annotated[
    Union[MetaEvent, StageEvent, ChunkEvent, FinalEvent, ErrorEvent, DoneEvent],
    Field(discriminator="type"),
]
STREAM_EVENT_ADAPTER: TypeAdapter = TypeAdapter(StreamEvent)
TERMINAL_TYPES = frozenset({"final", "error"})


def parse_stream_event(raw: Any):
    """Valida un evento (dict o JSON) contra el contrato; lanza ValidationError."""
    if isinstance(raw, (str, bytes)):
        return STREAM_EVENT_ADAPTER.validate_json(raw)
    return STREAM_EVENT_ADAPTER.validate_python(raw)
