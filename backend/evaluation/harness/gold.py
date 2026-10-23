"""Esquema, carga y verificación del gold de preguntas jurídicas (``legal_qa``).

El gold describe **lo que el corpus afirma**, no la verdad jurídica: cada hecho
exigido cita un fragmento textual del segmento de origen y el cargador lo
comprueba contra el corpus. Un caso solo cuenta para un lanzamiento cuando está
``adjudicated`` (doble revisión ciega por abogados); los casos ``candidate``
sirven para medir un baseline y para depurar el harness.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from evaluation.harness.corpus import Corpus
from evaluation.harness.matching import anchor_matches, compile_pattern, pattern_matches
from services.citation_verifier import citation_matches, despace, evidence_keys
from utils.text_match import contains

GOLD_DIR = Path(__file__).resolve().parents[3] / "tests" / "backend" / "fixtures" / "gold"
LEGAL_QA_PATH = GOLD_DIR / "legal_qa.v1.jsonl"

Stratum = Literal["positivo", "limite", "negativo"]
Split = Literal["dev", "holdout"]
Topic = Literal[
    "pension_alimentos",
    "regimen_visitas",
    "tenencia",
    "violencia_familiar",
    "omision_asistencia_familiar",
    "fuera_de_corpus",
]
Status = Literal["candidate", "reviewed", "adjudicated"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Reviewer(_Model):
    id: str = Field(min_length=1)
    role: Literal["abogado"]
    blind: bool
    verdict: Literal["approve", "revise", "reject"]
    reviewed_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class SegmentRef(_Model):
    segment_id: str
    sha: str = Field(pattern=r"^[0-9a-f]{12}$")


class SourceQuote(_Model):
    segment_id: str
    quote: str = Field(min_length=8)


class Fact(_Model):
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    text: str = Field(min_length=8)
    source: SourceQuote
    # AND de grupos; dentro de un grupo basta una alternativa (``re:`` = expresión regular).
    anchors: list[list[str]] = Field(min_length=1)


class ForbiddenClaim(_Model):
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    text: str = Field(min_length=8)
    kind: Literal["contradicted", "unsupported"]
    reason: str = Field(min_length=8)
    patterns: list[str] = Field(min_length=1)
    # Frase que un modelo podría decir; los patrones deben detectarla (se comprueba al cargar).
    example: str = Field(min_length=8)
    contradicted_by: Optional[SourceQuote] = None

    @model_validator(mode="after")
    def _kind_matches_evidence(self):
        if (self.kind == "contradicted") != (self.contradicted_by is not None):
            raise ValueError("`contradicted` exige `contradicted_by`; `unsupported` no lo admite")
        return self


class GoldCase(_Model):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    version: int = Field(ge=1)
    status: Status
    reviewers: list[Reviewer]
    topic: Topic
    query: str = Field(min_length=8)
    language: Literal["spanish", "quechua"]
    stratum: Stratum
    split: Split
    must_abstain: bool
    reference_segments: list[SegmentRef]
    required_facts: list[Fact]
    forbidden_claims: list[ForbiddenClaim]
    acceptable_citations: list[str]
    absent_terms: list[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def _consistency(self):
        if self.status == "candidate" and self.reviewers:
            raise ValueError("un caso `candidate` no puede tener revisores")
        if self.status != "candidate":
            ids = {r.id for r in self.reviewers}
            if self.status == "adjudicated" and (
                len(ids) < 2
                or not all(r.blind and r.verdict == "approve" for r in self.reviewers)
            ):
                raise ValueError("`adjudicated` exige >= 2 revisores distintos, ciegos y que aprueban")
            if self.status == "reviewed" and not ids:
                raise ValueError("`reviewed` exige al menos un revisor")
        if self.must_abstain and self.required_facts:
            raise ValueError("si `must_abstain`, no hay hechos exigidos")
        if not self.must_abstain and not self.required_facts:
            raise ValueError("sin `must_abstain` se exige al menos un hecho")
        if self.stratum == "negativo":
            if not self.must_abstain or self.reference_segments or not self.absent_terms:
                raise ValueError("`negativo`: debe abstenerse, sin segmentos y con `absent_terms`")
            if self.topic != "fuera_de_corpus":
                raise ValueError("`negativo` usa el tema `fuera_de_corpus`")
        else:
            if not self.reference_segments:
                raise ValueError("`positivo`/`limite` exigen segmentos de referencia")
            if self.topic == "fuera_de_corpus":
                raise ValueError("`fuera_de_corpus` solo es válido en `negativo`")
        for group in (self.required_facts, self.forbidden_claims):
            labels = [item.id for item in group]
            if len(labels) != len(set(labels)):
                raise ValueError("identificadores repetidos dentro del caso")
        return self


class GoldValidationError(ValueError):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("Gold inválido:\n- " + "\n- ".join(self.problems))


def verify_case(case: GoldCase, corpus: Corpus) -> list:
    """Problemas de ``case`` frente al corpus (lista vacía si todo se sustenta)."""
    problems = []
    tag = case.id
    refs = {}
    for ref in case.reference_segments:
        segment = corpus.segments.get(ref.segment_id)
        if segment is None:
            problems.append(f"{tag}: segmento inexistente {ref.segment_id}")
        elif segment.sha != ref.sha:
            problems.append(f"{tag}: el texto de {ref.segment_id} cambió (sha {segment.sha} != {ref.sha})")
        else:
            refs[ref.segment_id] = segment

    def check_quote(label, source: SourceQuote, must_be_referenced: bool):
        segment = corpus.segments.get(source.segment_id)
        if segment is None:
            problems.append(f"{tag}/{label}: segmento inexistente {source.segment_id}")
        elif must_be_referenced and source.segment_id not in refs:
            problems.append(f"{tag}/{label}: {source.segment_id} no está en reference_segments")
        elif not contains(segment.text, source.quote):
            problems.append(f"{tag}/{label}: la cita no aparece en {source.segment_id}")

    for fact in case.required_facts:
        check_quote(fact.id, fact.source, True)
        for group in fact.anchors:
            for anchor in group:
                try:
                    anchor_matches("", anchor)
                except re.error:
                    problems.append(f"{tag}/{fact.id}: expresión regular inválida {anchor!r}")
    whole = corpus.all_text()
    whole_variants = (whole, despace(whole))
    for claim in case.forbidden_claims:
        for pattern in claim.patterns:
            try:
                compile_pattern(pattern)
            except re.error:
                problems.append(f"{tag}/{claim.id}: expresión regular inválida {pattern!r}")
        if not any(pattern_matches(claim.example, p) for p in claim.patterns):
            problems.append(f"{tag}/{claim.id}: ningún patrón detecta su `example`")
        if claim.kind == "contradicted":
            check_quote(claim.id, claim.contradicted_by, False)
        else:
            hit = next((p for p in claim.patterns if any(pattern_matches(v, p) for v in whole_variants)), None)
            if hit:
                problems.append(f"{tag}/{claim.id}: el patrón {hit!r} aparece en el corpus; no es `unsupported`")
    if refs:
        cited = sorted({key for s in refs.values() for key in evidence_keys(s.text)})
        for acceptable in case.acceptable_citations:
            if not any(citation_matches(c, acceptable) or citation_matches(acceptable, c) for c in cited):
                problems.append(f"{tag}: la cita aceptable {acceptable} no aparece en los segmentos de referencia")
    elif case.acceptable_citations:
        problems.append(f"{tag}: sin segmentos de referencia no hay citas aceptables")
    for term in case.absent_terms:
        if contains(whole, term):
            problems.append(f"{tag}: el término {term!r} sí aparece en el corpus")
    return problems


def parse_case(line: str) -> GoldCase:
    return GoldCase.model_validate_json(line)


def load_gold(path=LEGAL_QA_PATH, *, corpus: Optional[Corpus] = None, verify=True, splits=None, only_adjudicated=False):
    """Carga el gold con validación estricta; con ``verify`` lo contrasta con el corpus."""
    problems, cases = [], []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(parse_case(line))
        except ValidationError as error:
            problems.append(f"línea {number}: {error.errors(include_url=False)[0]['msg']}")
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        problems.append("hay `id` repetidos")
    if verify:
        corpus = corpus or Corpus.load()
        for case in cases:
            problems.extend(verify_case(case, corpus))
    if problems:
        raise GoldValidationError(problems)
    if splits:
        cases = [c for c in cases if c.split in splits]
    if only_adjudicated:
        cases = [c for c in cases if c.status == "adjudicated"]
    return cases


def gold_hash(path=LEGAL_QA_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]


def dump_cases(cases, path):
    lines = [json.dumps(c.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) for c in sorted(cases, key=lambda c: c.id)]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
