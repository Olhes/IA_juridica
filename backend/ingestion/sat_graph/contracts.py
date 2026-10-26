"""Manifiestos revisados por una persona; nunca se construyen con un LLM."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Span(Contract):
    # Índices de caracteres Unicode del Markdown exacto, no bytes ni páginas PDF.
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("El fragmento debe ser no vacío")
        return self


class ReviewedUnit(Span):
    resource_id: str = Field(pattern=r"^pe:[a-z0-9][a-z0-9:-]*$")
    component: str = Field(pattern=r"^[a-z0-9][a-z0-9/-]*$")
    label: str = Field(min_length=1)
    parent_component: str | None = None
    language: Literal["es"] = "es"
    scope: Literal["PE"] = "PE"
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def interval(self):
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("Intervalo legal vacío o invertido")
        return self


class ReviewedAction(Span):
    action_key: str = Field(min_length=1)
    kind: Literal["enact", "amend", "repeal"]
    effective_on: date
    terminates: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)


class Membership(Contract):
    parent_version: str
    child_version: str


class ReviewManifest(Contract):
    schema_version: Literal[1] = 1
    evidence_id: str = Field(pattern=r"^pdf-sha256-[a-f0-9]{64}$")
    # Recurso del PDF causal; las unidades modificadas pueden pertenecer a otra ley.
    source_resource_id: str
    pdf_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    markdown_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    checked_through: date
    effective_date_basis: str = Field(min_length=1)
    units: list[ReviewedUnit] = Field(default_factory=list)
    actions: list[ReviewedAction] = Field(default_factory=list)
    memberships: list[Membership] = Field(default_factory=list)

    @model_validator(mode="after")
    def explicit_review(self):
        if not self.units and not self.actions:
            raise ValueError("Una revisión debe contener versiones o acciones")
        if not self.reviewer.strip() or not self.effective_date_basis.strip():
            raise ValueError("La revisión y fundamento de vigencia son obligatorios")
        if self.reviewed_at.tzinfo is None:
            raise ValueError("reviewed_at requiere zona horaria")
        if self.checked_through > self.reviewed_at.date():
            raise ValueError("La cobertura no puede estar en el futuro de la revisión")
        if any(unit.valid_from > self.checked_through for unit in self.units):
            raise ValueError("Versión fuera de la cobertura revisada")
        return self
