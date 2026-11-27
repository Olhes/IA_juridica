"""FastAPI routes for the offline GraphRAGProv provenance workbench."""
from __future__ import annotations

import asyncio
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from config.settings import settings
from services.graphragprov.models import DEFAULT_NAMESPACES
from services.graphragprov.nl_sparql import PROVENANCE_TEMPLATES
from services.graphragprov.service import (
    ProvenanceWorkspaceService,
    parse_polynomial_expression,
    serialize_graph,
)
from services.graphragprov.sparql import SparqlSafetyError, SparqlSyntaxError
from services.quality_access import require_quality_admin
from services.sat_corpus import Edition, validate_edition
from services.sat_corpus_routes import call, review_document

router = APIRouter(prefix="/sat-graph/review", tags=["SAT GraphRAGProv provenance"])
workspace_service = ProvenanceWorkspaceService()

SUPPORTED_SPARQL_FEATURES = [
    "SELECT",
    "DISTINCT",
    "PREFIX",
    "BGP",
    "OPTIONAL",
    "UNION",
    "FILTER",
    "ORDER BY",
    "LIMIT",
    "OFFSET",
]

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class BuildProvenanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["deterministic", "hybrid_cohere"] = "deterministic"
    component_ids: list[str] | None = Field(default=None, max_length=500)
    draft_edition: Edition | None = None


class ProvenanceQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str | None = Field(default=None, max_length=2000)
    sparql: str | None = Field(default=None, max_length=16000)
    nl_mode: Literal["deterministic", "cohere"] = "deterministic"
    extraction_mode: Literal["deterministic", "hybrid_cohere"] = "deterministic"
    component_ids: list[str] | None = Field(default=None, max_length=500)
    draft_edition: Edition | None = None
    max_rows: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def require_question_or_sparql(self) -> ProvenanceQueryRequest:
        if not ((self.question and self.question.strip()) or (self.sparql and self.sparql.strip())):
            raise ValueError("Proporcione una pregunta en lenguaje natural o una consulta SPARQL SELECT")
        return self


class PolynomialParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str = Field(min_length=1, max_length=32000)
    max_terms: int = Field(default=512, ge=1, le=2048)


def _require_review_header(request: Request) -> None:
    if request.headers.get("X-SAT-Review") != "1":
        raise HTTPException(403, "Falta confirmación del editor")


def _require_cohere_key() -> str:
    api_key = (settings.COHERE_API_KEY or "").strip()
    if not api_key:
        raise HTTPException(
            422,
            "COHERE_API_KEY no está configurada; utilice el modo determinístico sin conexión.",
        )
    return api_key


async def _load_document(resource_id: str) -> dict:
    try:
        return await asyncio.to_thread(lambda: review_document(resource_id, include_texts=True))
    except ValueError as exc:
        message = str(exc)
        if "no encontrado" in message.lower():
            raise HTTPException(404, message) from exc
        raise HTTPException(422, message) from exc


def _validate_optional_draft(draft_edition: Edition | None) -> dict | None:
    if draft_edition is None:
        return None
    try:
        validated = validate_edition(draft_edition)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return validated.model_dump()


@router.get("/provenance/capabilities", dependencies=[Depends(require_quality_admin)])
async def provenance_capabilities():
    return {
        "offline_ready": True,
        "cohere_available": bool((settings.COHERE_API_KEY or "").strip()),
        "cohere_model": settings.COHERE_LLM_MODEL,
        "namespaces": dict(DEFAULT_NAMESPACES),
        "templates": list(PROVENANCE_TEMPLATES),
        "supported_sparql_features": list(SUPPORTED_SPARQL_FEATURES),
        "semiring": "N[X] Sum-of-Products + NPCS prefix",
    }


@router.post("/documents/{resource_id}/provenance-graph")
async def build_provenance_graph(
    resource_id: str,
    body: BuildProvenanceRequest,
    request: Request,
    _actor: str = Depends(require_quality_admin),
):
    _require_review_header(request)
    api_key = _require_cohere_key() if body.mode == "hybrid_cohere" else None
    draft_dict = _validate_optional_draft(body.draft_edition)
    doc = await _load_document(resource_id)

    try:
        graph = await workspace_service.get_or_build_graph(
            doc,
            mode=body.mode,
            component_ids=body.component_ids,
            edition_override=draft_dict,
            cohere_api_key=api_key,
            cohere_model=settings.COHERE_LLM_MODEL,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return serialize_graph(graph)


@router.get(
    "/documents/{resource_id}/provenance-graph/ntriples",
    dependencies=[Depends(require_quality_admin)],
)
async def export_provenance_ntriples(
    resource_id: str,
    mode: Literal["deterministic", "hybrid_cohere"] = Query(default="deterministic"),
):
    api_key = _require_cohere_key() if mode == "hybrid_cohere" else None
    doc = await _load_document(resource_id)
    try:
        graph = await workspace_service.get_or_build_graph(
            doc,
            mode=mode,
            cohere_api_key=api_key,
            cohere_model=settings.COHERE_LLM_MODEL,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    nt_text = workspace_service.export_ntriples(graph)
    safe_name = _SAFE_FILENAME_RE.sub("-", resource_id).strip("-") or "sat-doc"
    return Response(
        nt_text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-prov.nt"'},
    )


@router.post("/documents/{resource_id}/provenance-query")
async def query_provenance(
    resource_id: str,
    body: ProvenanceQueryRequest,
    request: Request,
    _actor: str = Depends(require_quality_admin),
):
    _require_review_header(request)
    needs_cohere = body.extraction_mode == "hybrid_cohere" or (
        not (body.sparql and body.sparql.strip()) and body.nl_mode == "cohere"
    )
    api_key = _require_cohere_key() if needs_cohere else None
    draft_dict = _validate_optional_draft(body.draft_edition)
    doc = await _load_document(resource_id)

    try:
        graph = await workspace_service.get_or_build_graph(
            doc,
            mode=body.extraction_mode,
            component_ids=body.component_ids,
            edition_override=draft_dict,
            cohere_api_key=api_key,
            cohere_model=settings.COHERE_LLM_MODEL,
        )
        return await workspace_service.run_query(
            graph,
            question=body.question,
            sparql=body.sparql,
            nl_mode=body.nl_mode,
            max_rows=body.max_rows,
            cohere_api_key=api_key,
            cohere_model=settings.COHERE_LLM_MODEL,
        )
    except (SparqlSyntaxError, SparqlSafetyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/provenance/polynomial/parse")
async def parse_provenance_polynomial(
    body: PolynomialParseRequest,
    request: Request,
    _actor: str = Depends(require_quality_admin),
):
    _require_review_header(request)
    return await call(lambda: parse_polynomial_expression(body.expression, max_terms=body.max_terms))
