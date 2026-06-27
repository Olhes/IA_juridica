"""
Schemas Pydantic para el pipeline de validación de IA Jurídica.
Todos los módulos de validación comparten estos contratos de datos.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enumeraciones ──────────────────────────────────────────────────────────────

class ConfidenceLevel(str, Enum):
    """Nivel de confianza en la respuesta validada."""
    HIGH   = "high"    # score ≥ 0.80
    MEDIUM = "medium"  # score ≥ 0.55
    LOW    = "low"     # score < 0.55

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        if score >= 0.80:
            return cls.HIGH
        if score >= 0.55:
            return cls.MEDIUM
        return cls.LOW


class ValidationStatus(str, Enum):
    PASSED   = "passed"    # Sin problemas
    WARNED   = "warned"    # Advertencias, pero respuesta válida
    CORRECTED = "corrected" # Se aplicó self-correction
    FAILED   = "failed"    # No superó el umbral mínimo


# ── Modelos de datos ───────────────────────────────────────────────────────────

class RAGChunk(BaseModel):
    """Fragmento del corpus RAG con su score de relevancia."""
    content : str
    source  : str
    score   : float = Field(ge=0.0, le=1.0)

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or len(v.strip()) < 5:
            raise ValueError("El chunk no puede estar vacío")
        return v.strip()


class HallucinationFlag(BaseModel):
    """Un patrón problemático detectado en la respuesta."""
    pattern_name : str
    description  : str
    severity     : float = Field(ge=0.0, le=1.0, default=0.3)


class CrossCheckSummary(BaseModel):
    """Resumen del cross-check entre RAG y LLM."""
    is_grounded       : bool
    overlap_score     : float = Field(ge=0.0, le=1.0)
    ungrounded_claims : List[str] = []
    supporting_chunks : List[str] = []


class ValidationReport(BaseModel):
    """
    Informe completo generado por ResponseValidator.
    Contiene todos los sub-resultados de cada capa de validación.
    """
    status              : ValidationStatus
    confidence          : ConfidenceLevel
    confidence_score    : float = Field(ge=0.0, le=1.0)
    hallucination_risk  : float = Field(ge=0.0, le=1.0)
    is_grounded         : bool
    corrections_applied : int = 0
    flags               : List[HallucinationFlag] = []
    cross_check         : Optional[CrossCheckSummary] = None
    cultural_issues     : List[str] = []
    warnings            : List[str] = []
    processing_time_ms  : Optional[float] = None
    validated_at        : datetime = Field(default_factory=datetime.utcnow)


class ValidatedResponse(BaseModel):
    """
    Envoltorio final que une la respuesta original con su informe de validación.
    Este es el objeto que devuelve el endpoint /legal-query al frontend.
    """
    # Respuesta del LLM (puede ser dict serializado de GeneralLegalResponse, etc.)
    answer_data          : Dict[str, Any]
    validation_report    : ValidationReport
    query                : str
    language             : str
    sources              : List[str] = []

    @model_validator(mode="after")
    def ensure_answer_has_content(self) -> "ValidatedResponse":
        if not self.answer_data:
            raise ValueError("answer_data no puede estar vacío")
        return self

    @property
    def is_reliable(self) -> bool:
        """True si la respuesta pasó validación con confianza HIGH o MEDIUM."""
        return (
            self.validation_report.status in (ValidationStatus.PASSED, ValidationStatus.WARNED, ValidationStatus.CORRECTED)
            and self.validation_report.confidence != ConfidenceLevel.LOW
        )