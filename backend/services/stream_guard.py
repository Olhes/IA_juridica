"""StreamGuard: garantiza que lo que sale del stream NDJSON v1 cumple el contrato.

Envuelve el generador de líneas y, pase lo que pase aguas arriba, entrega:

* cada línea válida contra el esquema, con ``seq`` consecutivo desde 0 y un único ``request_id``;
* a lo sumo **un** evento terminal (``final`` o ``error``) y después un único ``done``;
* texto (``chunk``) solo si coincide con el de ``final``: un ``chunk`` se retiene hasta ver
  su ``final`` y, si difieren o el ``final`` no llega, no se entrega;
* un ``error`` ``TIMEOUT`` si el origen se queda mudo más de ``idle_timeout_s`` (watchdog).

Una violación nunca se silencia: se registra (solo el tipo, jamás el contenido) y el cliente
recibe un ``error`` ``INTERNAL_ERROR`` en lugar de datos dudosos.
"""

import asyncio
import json
import logging
from typing import Callable, Optional

from pydantic import ValidationError

from models.stream_events import (
    ERROR_MESSAGES,
    RETRYABLE_CODES,
    ChunkEvent,
    DoneEvent,
    ErrorEvent,
    MetaEvent,
    parse_stream_event,
)

logger = logging.getLogger("ia_juridica.stream")


def _line(event) -> str:
    return json.dumps(event.model_dump(exclude_none=True), ensure_ascii=False) + "\n"


class StreamGuard:
    def __init__(self, *, extract_text: Callable[[dict], str], request_id: str):
        self._extract_text = extract_text
        self._request_id = request_id
        self.violations: list = []
        self._seq = 0
        self._terminal: Optional[str] = None
        self._done = False
        self._held_chunk: Optional[ChunkEvent] = None
        self._saw_meta = False
        self._meta_emitted = False

    # ── emisión ────────────────────────────────────────────────────────────
    def _emit(self, cls, **fields) -> str:
        event = cls(seq=self._seq, request_id=self._request_id, **fields)
        self._seq += 1
        return _line(event)

    def _violation(self, kind: str) -> None:
        self.violations.append(kind)
        logger.error("stream_contract_violation kind=%s", kind)

    def _fail(self, code: str = "INTERNAL_ERROR") -> list:
        """Cierra el stream con un error (si aún no hay terminal) y ``done``."""
        out = []
        self._held_chunk = None
        if not self._meta_emitted:
            # El cliente siempre ve `meta` primero, incluso si el origen falló antes de enviarlo.
            self._meta_emitted = True
            out.append(self._emit(MetaEvent, data={"language": "unknown"}))
        if self._terminal is None:
            self._terminal = "error"
            out.append(self._emit(ErrorEvent, code=code, message=ERROR_MESSAGES[code], retryable=code in RETRYABLE_CODES))
        if not self._done:
            self._done = True
            out.append(self._emit(DoneEvent))
        return out

    # ── validación ─────────────────────────────────────────────────────────
    def feed(self, raw_line: str) -> list:
        """Procesa una línea del origen y devuelve las líneas a entregar."""
        if self._done:
            self._violation("event_after_done")
            return []
        try:
            event = parse_stream_event(raw_line)
        except (ValidationError, ValueError):
            self._violation("invalid_event")
            return self._fail()
        if event.request_id != self._request_id:
            self._violation("request_id_changed")
            return self._fail()
        if not self._saw_meta and event.type != "meta":
            self._violation("meta_missing")
            return self._fail()
        if event.type == "meta" and self._saw_meta:
            self._violation("duplicate_meta")
            return self._fail()
        if self._terminal is not None and event.type != "done":
            self._violation("event_after_terminal")
            return self._fail()
        self._saw_meta = True

        if event.type == "chunk":
            if self._held_chunk is not None:
                self._violation("multiple_chunks")
                return self._fail()
            self._held_chunk = event
            return []
        if event.type == "final":
            held, self._held_chunk = self._held_chunk, None
            if held is not None and held.delta != self._extract_text(event.data):
                self._violation("chunk_final_mismatch")
                return self._fail()
            self._terminal = "final"
            out = [self._emit(ChunkEvent, delta=held.delta)] if held is not None else []
            out.append(self._emit(type(event), data=event.data))
            return out
        if event.type == "error":
            self._held_chunk = None
            self._terminal = "error"
            return [self._emit(ErrorEvent, code=event.code, message=event.message, retryable=event.retryable)]
        if event.type == "done":
            if self._terminal is None:
                self._violation("done_without_terminal")
                return self._fail()
            self._done = True
            return [self._emit(DoneEvent)]
        # meta / stage: se reenumeran con el contador del guardián
        self._meta_emitted = self._meta_emitted or event.type == "meta"
        return [self._emit(type(event), **{k: v for k, v in event.model_dump(exclude_none=True).items()
                                           if k not in {"v", "seq", "request_id", "type"}})]

    @property
    def finished(self) -> bool:
        return self._done

    def close(self) -> list:
        """El origen terminó: completa el contrato si faltaba el terminal o ``done``."""
        if self._done:
            return []
        if self._terminal is None:
            self._violation("stream_ended_without_terminal")
        return self._fail()

    def timeout(self) -> list:
        self._violation("idle_timeout")
        return self._fail("TIMEOUT")


async def guard_stream(source, *, extract_text, request_id, idle_timeout_s: float):
    """Generador asíncrono que aplica ``StreamGuard`` a las líneas de ``source``."""
    guard = StreamGuard(extract_text=extract_text, request_id=request_id)
    iterator = source.__aiter__()
    try:
        while True:
            try:
                raw = await asyncio.wait_for(iterator.__anext__(), idle_timeout_s)
            except StopAsyncIteration:
                for line in guard.close():
                    yield line
                return
            except asyncio.TimeoutError:
                for line in guard.timeout():
                    yield line
                return
            for line in guard.feed(raw):
                yield line
            if guard.finished:
                return
    finally:
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:  # noqa: BLE001 - el cierre del origen no puede romper la respuesta
                pass
