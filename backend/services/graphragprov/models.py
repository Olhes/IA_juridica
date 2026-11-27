"""Pure domain models for the offline GraphRAGProv engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TermKind = Literal["iri", "literal", "bnode"]
SpanMatchQuality = Literal[
    "exact",
    "normalized",
    "clause_window",
    "inferred_from_heading",
    "anchored",
]
ExtractionOrigin = Literal["structural", "deterministic_legal", "cohere_llm"]
SourceKind = Literal["published", "draft", "candidate"]

RDF_TYPE_IRI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
XSD_STRING_IRI = "http://www.w3.org/2001/XMLSchema#string"
XSD_INTEGER_IRI = "http://www.w3.org/2001/XMLSchema#integer"
XSD_DECIMAL_IRI = "http://www.w3.org/2001/XMLSchema#decimal"
XSD_DOUBLE_IRI = "http://www.w3.org/2001/XMLSchema#double"
XSD_FLOAT_IRI = "http://www.w3.org/2001/XMLSchema#float"
XSD_BOOLEAN_IRI = "http://www.w3.org/2001/XMLSchema#boolean"
XSD_DATE_IRI = "http://www.w3.org/2001/XMLSchema#date"

NUMERIC_DATATYPES = frozenset({
    XSD_INTEGER_IRI,
    XSD_DECIMAL_IRI,
    XSD_DOUBLE_IRI,
    XSD_FLOAT_IRI,
})

DEFAULT_NAMESPACES: dict[str, str] = {
    "sat": "http://iajuridica.pe/sat/",
    "legal": "http://iajuridica.pe/legal/",
    "textprov": "http://iajuridica.pe/textprov/",
    "pe": "http://iajuridica.pe/pe/",
    "entity": "http://iajuridica.pe/entity/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


def _escape_nt_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return escaped


def _escape_nt_iri(value: str) -> str:
    return value.replace("<", "%3C").replace(">", "%3E").replace(" ", "%20").replace('"', "%22")


@dataclass(frozen=True, slots=True)
class RDFTerm:
    """Canonical RDF term supporting IRIs, blank nodes, and typed/lang literals."""

    kind: TermKind
    value: str
    label: str
    datatype: str | None = None
    language: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("iri", "literal", "bnode"):
            raise ValueError(f"Unsupported RDF term kind: {self.kind!r}")
        if not self.value:
            raise ValueError("RDFTerm.value must be non-empty")
        if not self.label:
            raise ValueError("RDFTerm.label must be non-empty")
        if self.kind != "literal" and (self.datatype is not None or self.language is not None):
            raise ValueError("datatype and language are only valid for RDF literal terms")
        if self.datatype is not None and self.language is not None:
            raise ValueError("RDF literal cannot carry both datatype and language tag")

    def ntriples(self) -> str:
        if self.kind == "iri":
            return f"<{_escape_nt_iri(self.value)}>"
        if self.kind == "bnode":
            cleaned = self.value[2:] if self.value.startswith("_:") else self.value
            return f"_:{cleaned}"
        quoted = f'"{_escape_nt_string(self.value)}"'
        if self.language:
            return f"{quoted}@{self.language}"
        if self.datatype and self.datatype != XSD_STRING_IRI:
            return f"{quoted}^^<{_escape_nt_iri(self.datatype)}>"
        return quoted

    def term_key(self) -> tuple[str, str, str | None, str | None]:
        return (self.kind, self.value, self.datatype, self.language)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "value": self.value,
            "label": self.label,
        }
        if self.datatype is not None:
            payload["datatype"] = self.datatype
        if self.language is not None:
            payload["language"] = self.language
        return payload


@dataclass(frozen=True, slots=True)
class CharSpan:
    """Half-open [start, end) Unicode codepoint range."""

    start: int
    end: int
    surface_text: str
    quality: SpanMatchQuality = "exact"

    def __post_init__(self) -> None:
        if isinstance(self.start, bool) or isinstance(self.end, bool):
            raise ValueError("CharSpan bounds must be integers, not booleans")
        if self.start < 0 or self.end <= self.start:
            raise ValueError(f"Invalid CharSpan bounds: [{self.start}, {self.end})")
        if not self.surface_text:
            raise ValueError("CharSpan.surface_text must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "surface_text": self.surface_text,
            "quality": self.quality,
        }


@dataclass(frozen=True, slots=True)
class LocalizedSpans:
    """Component-relative and document-relative codepoint spans for (s, p, o) and clause."""

    component_id: str
    evidence_span: CharSpan
    doc_evidence_span: CharSpan
    version_id: str | None = None
    text_unit_id: str | None = None
    subject_span: CharSpan | None = None
    predicate_span: CharSpan | None = None
    object_span: CharSpan | None = None
    component_start_in_doc: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "version_id": self.version_id,
            "text_unit_id": self.text_unit_id,
            "component_start_in_doc": self.component_start_in_doc,
            "evidence_span": self.evidence_span.to_dict(),
            "doc_evidence_span": self.doc_evidence_span.to_dict(),
            "subject_span": self.subject_span.to_dict() if self.subject_span else None,
            "predicate_span": self.predicate_span.to_dict() if self.predicate_span else None,
            "object_span": self.object_span.to_dict() if self.object_span else None,
        }


@dataclass(frozen=True, slots=True)
class StatementOccurrence:
    """GraphRAGProv symbolic chunk: one localized occurrence of (s, p, o)."""

    token: str
    doc_id: str
    passage_id: str
    subject: RDFTerm
    predicate: RDFTerm
    object: RDFTerm
    origin: ExtractionOrigin
    confidence_rule: str
    spans: LocalizedSpans
    rdf_star_nt: str

    def __post_init__(self) -> None:
        if not self.token.startswith("occ_") or len(self.token) != 16:
            raise ValueError(f"Invalid occurrence token format: {self.token!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "doc_id": self.doc_id,
            "passage_id": self.passage_id,
            "subject": self.subject.to_dict(),
            "predicate": self.predicate.to_dict(),
            "object": self.object.to_dict(),
            "origin": self.origin,
            "confidence_rule": self.confidence_rule,
            "spans": self.spans.to_dict(),
            "rdf_star_nt": self.rdf_star_nt,
        }


@dataclass(frozen=True, slots=True)
class SourceUnitText:
    """Grounded text unit so non-editable and editable documents both render spans cleanly."""

    id: str
    label: str
    kind: str
    text: str
    global_start: int
    global_end: int
    parent_id: str | None = None
    version_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "text": self.text,
            "global_start": self.global_start,
            "global_end": self.global_end,
            "parent_id": self.parent_id,
            "version_id": self.version_id,
        }


@dataclass(frozen=True, slots=True)
class SampleProvenanceQuery:
    """Tailored example SPARQL query highlighting provenance algebra on a graph."""

    id: str
    title: str
    question: str
    sparql: str
    highlights_algebra: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "question": self.question,
            "sparql": self.sparql,
            "highlights_algebra": self.highlights_algebra,
        }


@dataclass(frozen=True, slots=True)
class GroundedGraph:
    """Source-grounded RDF-star occurrence graph for one document revision or draft."""

    doc_id: str
    revision: str
    source_kind: SourceKind
    markdown_sha256: str
    namespaces: dict[str, str]
    source_units: dict[str, SourceUnitText]
    occurrences: tuple[StatementOccurrence, ...]
    by_token: dict[str, int]
    predicates: tuple[str, ...]
    sample_queries: tuple[SampleProvenanceQuery, ...]
    cohere_used: bool = False
    unlocalized_discarded: int = 0
    document_markdown: str = ""


@dataclass(frozen=True, slots=True)
class SparqlQuery:
    """Parsed SPARQL SELECT query AST."""

    prefixes: dict[str, str]
    distinct: bool
    projection: tuple[str, ...] | None
    where: Any
    order_by: tuple[tuple[str, Literal["ASC", "DESC"]], ...] = ()
    limit: int | None = None
    offset: int = 0


@dataclass(frozen=True, slots=True)
class EvalLimits:
    """Safety bounds for pure-Python SPARQL evaluation."""

    max_ast_depth: int = 32
    max_join_work: int = 50_000
    max_rows: int = 200
    max_monomials: int = 512
    max_regex_len: int = 256


@dataclass(frozen=True, slots=True)
class ProvenanceRow:
    """Single evaluated SPARQL answer binding with exact N[X] provenance."""

    bindings: dict[str, RDFTerm | None]
    expr: Any
    polynomial: Any


@dataclass(frozen=True, slots=True)
class SparqlEvalResult:
    """Pure evaluation result from executing a SPARQL SELECT over a GroundedGraph."""

    variables: tuple[str, ...]
    rows: tuple[ProvenanceRow, ...]
    referenced_tokens: tuple[str, ...]
    elapsed_ms: float
    truncated_rows: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)
