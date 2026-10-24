"""Respuesta normalizada del pipeline, independiente de cómo se obtuvo.

``answer_from_payload`` acepta la salida de ``answer_query`` (o su versión
grabada en un cassette). Las métricas solo leen un ``Answer``.
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from utils.text_match import normalize

# Marcas de una no-respuesta explícita (abstención semántica), sobre texto normalizado.
ABSTENTION_MARKERS = (
    r"no hay evidencia suficiente",
    r"el corpus no (contiene|indica|establece|incluye|menciona|precisa)",
    r"no (consta|se indica|se establece|se menciona|se precisa|se puede determinar|es posible determinar)"
    r"[^.]{0,60}(corpus|fuentes|documentos|informacion disponible)",
    r"no (puedo|podemos) (determinar|responder|confirmar)",
    r"(fuera|ajeno) (del|al) (alcance|corpus)",
    r"no cuento con (informacion|evidencia|fuentes)",
)
_MARKERS = re.compile("|".join(ABSTENTION_MARKERS))


@dataclass
class Answer:
    text: str = ""
    evidence_status: Optional[str] = None
    sources: list = field(default_factory=list)
    confidence_score: Optional[float] = None
    is_reliable: Optional[bool] = None
    cross_check_overlap: Optional[float] = None
    citations: Optional[list] = None  # metadata.citations del runtime, si existe
    timings: Optional[dict] = None
    error: Optional[str] = None
    # Respuesta validada en español (antes de traducir). En consultas en quechua los hechos y
    # citas se comprueban sobre ella; ``text`` conserva lo que vio el usuario.
    text_es: Optional[str] = None
    # Texto completo de los fragmentos recuperados (contexto de la fidelidad); ``sources`` solo
    # trae nombres de archivo.
    contexts: Optional[list] = None

    @property
    def fact_text(self) -> str:
        return self.text_es or self.text

    @property
    def abstained_formal(self) -> bool:
        return self.evidence_status == "insufficient_evidence"

    @property
    def abstained_semantic(self) -> bool:
        return bool(_MARKERS.search(normalize(self.text)) or _MARKERS.search(normalize(self.fact_text)))

    @property
    def abstained(self) -> bool:
        return self.abstained_formal or self.abstained_semantic

    def to_json(self):
        return asdict(self)


def _text_of(response, language):
    from services.legal_queries import response_text

    return response_text(response, language)


def answer_from_payload(payload: dict, language="spanish") -> Answer:
    validation = payload.get("validation") or {}
    metadata = payload.get("metadata") or {}
    cross = validation.get("cross_check") or {}
    return Answer(
        text=_text_of(payload.get("response"), language),
        evidence_status=metadata.get("evidence_status"),
        sources=list(payload.get("sources") or []),
        confidence_score=validation.get("confidence_score"),
        is_reliable=validation.get("is_reliable"),
        cross_check_overlap=cross.get("overlap_score") if isinstance(cross, dict) else None,
        citations=metadata.get("citations"),
        timings=metadata.get("timings"),
        text_es=_text_of(payload.get("response"), "spanish") or None,
    )


def answer_from_json(data: dict) -> Answer:
    return Answer(**data)
