"""Stream NDJSON v1 de una consulta jurídica.

Emite `meta` y `stage` mientras corre el pipeline y el texto solo cuando ya está
validado (nunca borradores). Termina siempre con un único `final` o `error`,
seguido de `done`. La autorización y la conversación ajena se validan antes de
abrir el stream; todo fallo posterior sale como evento `error`.
"""

import asyncio
import json
import logging
import time

from fastapi.encoders import jsonable_encoder

from models.stream_events import (
    ERROR_MESSAGES,
    RETRYABLE_CODES,
    ChunkEvent,
    DoneEvent,
    ErrorEvent,
    FinalEvent,
    MetaEvent,
    StageEvent,
)

logger = logging.getLogger("ia_juridica.stream")


def encode_event(event) -> str:
    """Serializa un evento del contrato como una línea NDJSON."""
    return json.dumps(jsonable_encoder(event.model_dump(exclude_none=True)), ensure_ascii=False) + "\n"


def error_code_for(error) -> str:
    code = getattr(error, "code", None)
    if code in ERROR_MESSAGES:
        return code
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return "TIMEOUT"
    return "INTERNAL_ERROR"


async def stream_legal_query(
    *, run_pipeline, extract_text, persist, request_id, language, timeout_s
):
    """Genera las líneas NDJSON de una consulta.

    `run_pipeline(on_stage)` ejecuta `answer_query`; `persist(result)` guarda la
    respuesta del asistente; `extract_text(result)` devuelve el texto del chunk.
    """
    seq = 0

    def next_event(cls, **fields):
        nonlocal seq
        event = cls(seq=seq, request_id=request_id, **fields)
        seq += 1
        return encode_event(event)

    queue: asyncio.Queue = asyncio.Queue()

    async def on_stage(event):
        queue.put_nowait(("stage", event))

    async def run():
        try:
            queue.put_nowait(("result", await run_pipeline(on_stage)))
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - se traduce a evento `error`
            queue.put_nowait(("error", error))

    yield next_event(MetaEvent, data={"language": language, "pipeline": "validated-before-delivery-v1"})
    task = asyncio.create_task(run())
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            remaining = deadline - time.monotonic()
            try:
                kind, value = await asyncio.wait_for(queue.get(), max(remaining, 0))
            except asyncio.TimeoutError:
                kind, value = "error", TimeoutError()
            if kind == "stage":
                yield next_event(StageEvent, **value)
                continue
            if kind == "result":
                try:
                    await persist(value)
                except Exception as error:  # noqa: BLE001
                    kind, value = "error", error
                else:
                    yield next_event(ChunkEvent, delta=extract_text(value))
                    yield next_event(FinalEvent, data=jsonable_encoder(value))
                    break
            code = error_code_for(value)
            logger.error("stream_failed code=%s error_type=%s", code, type(value).__name__)
            yield next_event(
                ErrorEvent, code=code, message=ERROR_MESSAGES[code],
                retryable=code in RETRYABLE_CODES,
            )
            break
        yield next_event(DoneEvent)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
