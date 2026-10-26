"""Correcciones documentales de estructura; nunca aprobación de vigencia o CTV."""

from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InstrumentBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1)


class StructureReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    markdown_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_kind: Literal["ai_documentary", "human_documentary"]
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    instrument_boundaries: list[InstrumentBoundary] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def explicit_review(self):
        if not self.reviewer.strip() or self.reviewed_at.tzinfo is None:
            raise ValueError("Revisor y fecha documental con zona horaria requeridos")
        if any(not b.reason.strip() for b in self.instrument_boundaries):
            raise ValueError("Cada corrección requiere fundamento documental")
        return self


def reviewed_lines(markdown, lines, review):
    """Cortar la vista del parser en offsets explícitos, sin editar un carácter.

    Un conversor puede fusionar una firma y el título del anexo en una sola línea.
    La corrección queda vinculada a los bytes Unicode exactos de esa conversión.
    Los límites de citas/código se validan después en el parser, antes de publicar.
    """
    if review is None:
        return lines, {}, None
    review = StructureReview.model_validate(review)
    if sha256(markdown.encode()).hexdigest() != review.markdown_sha256:
        raise ValueError("Revisión estructural corresponde a otro Markdown")
    boundaries = sorted(review.instrument_boundaries, key=lambda b: b.start)
    previous_end = -1
    for boundary in boundaries:
        text = markdown[boundary.start : boundary.end]
        if (
            boundary.start < previous_end
            or boundary.end <= boundary.start
            or boundary.end > len(markdown)
            or not text.strip()
            or "\n" in text
            or "\r" in text
            or sha256(text.encode()).hexdigest() != boundary.text_sha256
        ):
            raise ValueError(
                "Límite documental fuera de rango, repetido o hash incorrecto"
            )
        previous_end = boundary.end
    cuts = sorted(
        {0, len(markdown), *(a for a, _, _ in lines)}
        | {p for b in boundaries for p in (b.start, b.end)}
    )
    return (
        [(a, b, markdown[a:b]) for a, b in zip(cuts, cuts[1:])],
        {b.start: b for b in boundaries},
        review.model_dump(mode="json"),
    )
