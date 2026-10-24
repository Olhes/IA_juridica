"""Tiempos por etapa del pipeline legal.

`PipelineTimer` mide las etapas de `answer_query` y avisa a un `on_stage`
opcional (sincrónico o asíncrono) al empezar y terminar cada una. Solo guarda
nombres y milisegundos: nunca texto de la consulta ni de la respuesta.
"""

import inspect
import time
from contextlib import asynccontextmanager

STAGES = ("translate_in", "retrieval", "generation", "validation", "translate_out")


class PipelineTimer:
    def __init__(self, on_stage=None, clock=time.perf_counter):
        self._on_stage = on_stage
        self._clock = clock
        self._started = clock()
        self.stages: dict[str, float] = {}
        self.cache_hit = False

    async def _emit(self, stage, status, elapsed_ms=None):
        if self._on_stage is None:
            return
        event = {"stage": stage, "status": status}
        if elapsed_ms is not None:
            event["elapsed_ms"] = elapsed_ms
        result = self._on_stage(event)
        if inspect.isawaitable(result):
            await result

    @asynccontextmanager
    async def stage(self, name):
        if name not in STAGES:
            raise ValueError(f"Etapa desconocida: {name}")
        await self._emit(name, "start")
        began = self._clock()
        try:
            yield
        finally:
            elapsed = round((self._clock() - began) * 1000, 3)
            self.stages[name] = round(self.stages.get(name, 0.0) + elapsed, 3)
            await self._emit(name, "end", elapsed)

    def snapshot(self):
        return {
            "total_ms": round((self._clock() - self._started) * 1000, 3),
            "stages": dict(self.stages),
            "cache_hit": self.cache_hit,
        }
