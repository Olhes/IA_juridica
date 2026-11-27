"""Source-grounded legal triple extraction (deterministic + optional Cohere)."""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Sequence
import unicodedata

from retrieval.sat_citations import references as extract_sat_references
from services.graphragprov.localizer import (
    format_occurrence_rdf_star,
    localize_evidence,
    mint_occurrence_token,
)
from services.graphragprov.models import (
    DEFAULT_NAMESPACES,
    ExtractionOrigin,
    GroundedGraph,
    RDFTerm,
    SampleProvenanceQuery,
    SourceKind,
    SourceUnitText,
    StatementOccurrence,
    XSD_INTEGER_IRI,
    XSD_STRING_IRI,
)

SAT_NS = DEFAULT_NAMESPACES["sat"]
LEGAL_NS = DEFAULT_NAMESPACES["legal"]
PE_NS = DEFAULT_NAMESPACES["pe"]
ENTITY_NS = DEFAULT_NAMESPACES["entity"]

_NORM_REF_RE = re.compile(
    r"\b("
    r"Ley\s+(?:N\.?\s*[°º]?\s*)?\d{4,6}"
    r"|Decreto\s+Legislativo\s+(?:N\.?\s*[°º]?\s*)?\d{1,5}"
    r"|D\.?\s*L\.?\s+(?:N\.?\s*[°º]?\s*)?\d{1,5}"
    r"|Decreto\s+Supremo\s+(?:N\.?\s*[°º]?\s*)?\d{1,4}\s*-\s*\d{4}(?:\s*-\s*[A-Za-z]+)?"
    r"|Resoluci[oó]n\s+Ministerial\s+(?:N\.?\s*[°º]?\s*)?\d{1,4}\s*-\s*\d{4}(?:\s*-\s*[A-Za-z]+)?"
    r"|C[oó]digo\s+Procesal\s+Civil"
    r"|Art[ií]culo\s+\d{1,4}(?:-[A-Za-z])?"
    r")\b",
    re.IGNORECASE,
)

_AMEND_VERB_RE = re.compile(r"\b(modif[ií]c\w+|sustituy\w+|reform\w+)\b", re.IGNORECASE)
_REPEAL_VERB_RE = re.compile(r"\b(derog\w+|deja\s+sin\s+efecto)\b", re.IGNORECASE)
_INCORP_VERB_RE = re.compile(r"\b(incorpor\w+|adicion\w+|agreg\w+)\b", re.IGNORECASE)
_CITE_VERB_RE = re.compile(
    r"\b(conforme\s+a|de\s+conformidad\s+con|seg[uú]n|en\s+aplicaci[oó]n\s+de|previst[oa]\s+en|establecid[oa]\s+en|citad[oa]|remite\s+a)\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+|\n+")

_DEONTIC_RULES: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
    (
        "legal:obligates",
        "legal-deontic-obligation-v1",
        "obliga a",
        re.compile(
            r"\b(?P<verb>deber[aá]n?|deben?|est[aá]n?\s+obligad[oa]s?\s+a|tiene\s+la\s+obligaci[oó]n\s+de|obliga\s+a|establece\s+la\s+obligaci[oó]n\s+de)\s+(?P<obj>[^.;\n]{4,220})",
            re.IGNORECASE,
        ),
    ),
    (
        "legal:prohibits",
        "legal-deontic-prohibition-v1",
        "prohíbe",
        re.compile(
            r"\b(?P<verb>se\s+proh[ií]be|proh[ií]be|queda\s+prohibid[oa]|est[aá]\s+prohibid[oa]|no\s+podr[aá]n?)\s+(?P<obj>[^.;\n]{4,220})",
            re.IGNORECASE,
        ),
    ),
    (
        "legal:defines",
        "legal-definition-v1",
        "define",
        re.compile(
            r"\b(?P<verb>se\s+entiende\s+por|se\s+considera|constituye|se\s+define\s+como|define\s+como)\s+(?P<obj>[^.;\n]{4,220})",
            re.IGNORECASE,
        ),
    ),
    (
        "legal:grantsRight",
        "legal-right-v1",
        "garantiza derecho",
        re.compile(
            r"\b(?P<verb>tienen?\s+derecho\s+a|se\s+garantiza|garantiza\s+el\s+derecho\s+a|garantiza|se\s+reconoce\s+el\s+derecho\s+a|gozan?\s+del\s+derecho\s+a)\s+(?P<obj>[^.;\n]{4,220})",
            re.IGNORECASE,
        ),
    ),
    (
        "legal:sanctions",
        "legal-sanction-v1",
        "sanciona",
        re.compile(
            r"\b(?P<verb>ser[aá]n?\s+sancionad[oa]s?\s+con|se\s+sanciona\s+con|sanciona\s+con|constituye\s+infracci[oó]n|impone\s+multa\s+de)\s+(?P<obj>[^.;\n]{4,220})",
            re.IGNORECASE,
        ),
    ),
    (
        "legal:assignsCompetence",
        "legal-competence-v1",
        "asigna competencia",
        re.compile(
            r"\b(?P<verb>es\s+competente\s+para|corresponde\s+a|a\s+cargo\s+de|administra|supervisa|encargad[oa]\s+de)\s+(?P<obj>[^.;\n]{4,220})",
            re.IGNORECASE,
        ),
    ),
)

_DEADLINE_RE = re.compile(
    r"\b(?P<verb>en\s+un\s+plazo\s+(?:m[aá]ximo\s+)?de|dentro\s+de\s+(?:los\s+)?|plazo\s+(?:m[aá]ximo\s+)?de)\s+(?P<num>\d{1,4})\s+(?P<unit>d[ií]as(?:\s+h[aá]biles|\s+calendario)?|meses|a[nñ]os|horas)\b",
    re.IGNORECASE,
)

_ENTITY_SUBJECT_RE = re.compile(
    r"\b("
    r"Poder\s+Judicial"
    r"|Ministerio\s+(?:de\s+(?:la\s+|los\s+|las\s+)?[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+y\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*|P[uú]blico)"
    r"|Polic[ií]a\s+Nacional(?:\s+del\s+Per[uú])?"
    r"|Registro\s+de\s+Deudores\s+Alimentarios\s+Morosos"
    r"|REDAM"
    r"|Estado(?:\s+peruano)?"
    r"|Consejo\s+Ejecutivo\s+del\s+Poder\s+Judicial"
    r"|Defensor[ií]a\s+del\s+Pueblo"
    r"|El\s+[oó]rgano\s+jurisdiccional"
    r"|El\s+juez|La\s+jueza|Los\s+jueces"
    r"|Las\s+entidades\s+p[uú]blicas"
    r")\b",
    re.IGNORECASE,
)


def _slug(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    ascii_only = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    cleaned = re.sub(r"[^a-z0-9]+", "_", ascii_only.casefold()).strip("_")
    return cleaned[:64] or "item"


def _doc_iri(doc_id: str) -> str:
    return f"{PE_NS}{doc_id}"


def _component_iri(doc_id: str, component_id: str) -> str:
    return f"{PE_NS}{doc_id}/comp/{_slug(component_id)}"


def _entity_iri(label: str) -> str:
    return f"{ENTITY_NS}{_slug(label)}"


def _norm_ref_iri(label: str) -> str:
    _, resources, articles, _, _, _ = extract_sat_references(label)
    if resources:
        return f"{PE_NS}{sorted(resources)[0]}"
    if articles:
        return f"{PE_NS}art/{articles[0][1]}"
    return _entity_iri(label)


def _predicate_term(prefixed: str, label: str) -> RDFTerm:
    prefix, local = prefixed.split(":", 1)
    base = DEFAULT_NAMESPACES[prefix]
    return RDFTerm(kind="iri", value=f"{base}{local}", label=label)


def _build_source_units(
    doc_payload: dict[str, Any],
    *,
    edition_override: dict[str, Any] | None = None,
    component_ids: Sequence[str] | None = None,
) -> tuple[str, str, SourceKind, str, dict[str, SourceUnitText], dict[str, dict[str, Any]]]:
    """Normalize editable, draft, candidate, or non-editable SAT docs into SourceUnitTexts."""
    doc_id = str(doc_payload.get("id") or "unknown")
    scope_set = set(component_ids) if component_ids else None
    versions_by_comp: dict[str, dict[str, Any]] = {}
    for ver in doc_payload.get("versions") or ():
        if ver.get("archived"):
            continue
        cid = ver.get("component_id") or ver.get("id")
        if cid:
            versions_by_comp[str(cid)] = ver

    edition = edition_override if edition_override is not None else doc_payload.get("edition")
    if edition_override is not None:
        source_kind: SourceKind = "draft"
    elif doc_id.startswith("candidate:") or doc_payload.get("candidate"):
        source_kind = "candidate"
    else:
        source_kind = "published"

    units: dict[str, SourceUnitText] = {}
    markdown = ""
    revision = "unknown"

    if edition and edition.get("markdown") and edition.get("components"):
        markdown = str(edition["markdown"])
        revision = str(edition.get("revision") or "edition")
        for comp in edition["components"]:
            cid = str(comp["id"])
            if scope_set is not None and cid not in scope_set:
                continue
            start = int(comp["start"])
            end = int(comp["end"])
            if not (0 <= start < end <= len(markdown)):
                continue
            ver = versions_by_comp.get(cid)
            units[cid] = SourceUnitText(
                id=cid,
                label=str(comp.get("label") or cid),
                kind=str(comp.get("kind") or "component"),
                text=markdown[start:end],
                global_start=start,
                global_end=end,
                parent_id=comp.get("parent_id"),
                version_id=ver.get("id") if ver else None,
            )
    else:
        # Non-editable or compacted document without edition.markdown: assemble contiguous units from versions.
        revision = str((edition or {}).get("revision") or (doc_payload.get("revisions") or ["snapshot"])[0])
        comp_meta = {
            str(c["id"]): c for c in ((edition or {}).get("components") or ())
        }
        parts: list[str] = []
        cursor = 0
        for ver in doc_payload.get("versions") or ():
            if ver.get("archived"):
                continue
            cid = str(ver.get("component_id") or ver["id"])
            if scope_set is not None and cid not in scope_set:
                continue
            texts = ver.get("texts") or ()
            if not texts:
                continue
            raw_text = str(texts[0].get("text") or "")
            if not raw_text.strip():
                continue
            if parts:
                parts.append("\n\n")
                cursor += 2
            g_start = cursor
            parts.append(raw_text)
            cursor += len(raw_text)
            meta = comp_meta.get(cid, {})
            units[cid] = SourceUnitText(
                id=cid,
                label=str(meta.get("label") or ver.get("label") or cid),
                kind=str(meta.get("kind") or ver.get("kind") or "component"),
                text=raw_text,
                global_start=g_start,
                global_end=cursor,
                parent_id=meta.get("parent_id"),
                version_id=str(ver["id"]),
            )
        markdown = "".join(parts)

    return doc_id, revision, source_kind, markdown, units, versions_by_comp


def _make_occurrence(
    *,
    doc_id: str,
    unit: SourceUnitText,
    text_unit_id: str | None,
    subject: RDFTerm,
    predicate: RDFTerm,
    obj: RDFTerm,
    subject_quote: str,
    predicate_quote: str,
    object_quote: str,
    origin: ExtractionOrigin,
    rule_id: str,
    evidence_hint: str | None = None,
    heading_label: str | None = None,
    allow_inferred_subject: bool = False,
) -> StatementOccurrence | None:
    spans = localize_evidence(
        unit.text,
        subject_quote,
        predicate_quote,
        object_quote,
        component_start_in_doc=unit.global_start,
        component_id=unit.id,
        version_id=unit.version_id,
        text_unit_id=text_unit_id,
        evidence_hint=evidence_hint,
        heading_label=heading_label,
        allow_inferred_subject=allow_inferred_subject,
    )
    if spans is None:
        return None
    token = mint_occurrence_token(
        doc_id,
        unit.id,
        spans.doc_evidence_span.start,
        spans.doc_evidence_span.end,
        subject,
        predicate,
        obj,
    )
    rdf_star_nt = format_occurrence_rdf_star(token, doc_id, subject, predicate, obj, spans)
    return StatementOccurrence(
        token=token,
        doc_id=doc_id,
        passage_id=text_unit_id or unit.version_id or unit.id,
        subject=subject,
        predicate=predicate,
        object=obj,
        origin=origin,
        confidence_rule=rule_id,
        spans=spans,
        rdf_star_nt=rdf_star_nt,
    )


def _generate_sample_queries(
    occurrences: Sequence[StatementOccurrence],
) -> tuple[SampleProvenanceQuery, ...]:
    preds = {occ.predicate.value for occ in occurrences}
    samples: list[SampleProvenanceQuery] = []

    has_deontic = any(
        p in preds
        for p in (
            f"{LEGAL_NS}obligates",
            f"{LEGAL_NS}prohibits",
            f"{LEGAL_NS}grantsRight",
            f"{LEGAL_NS}defines",
            f"{LEGAL_NS}setsDeadline",
            f"{LEGAL_NS}cites",
        )
    )

    if f"{LEGAL_NS}obligates" in preds and f"{LEGAL_NS}prohibits" in preds:
        samples.append(
            SampleProvenanceQuery(
                id="deontic-union",
                title="Obligaciones y prohibiciones (UNION / ⊕)",
                question="¿Qué obligaciones o prohibiciones establece la norma?",
                sparql=(
                    f"PREFIX legal: <{LEGAL_NS}>\n"
                    "SELECT DISTINCT ?sujeto ?disposicion WHERE {\n"
                    "  { ?sujeto legal:obligates ?disposicion . }\n"
                    "  UNION\n"
                    "  { ?sujeto legal:prohibits ?disposicion . }\n"
                    "}"
                ),
                highlights_algebra="disyunción (⊕) mediante UNION entre obligaciones y prohibiciones",
            )
        )
    elif f"{LEGAL_NS}obligates" in preds:
        samples.append(
            SampleProvenanceQuery(
                id="obligations-multihop",
                title="Obligaciones por componente (Join / ⊗)",
                question="¿Qué obligaciones existen y en qué componente se ubican?",
                sparql=(
                    f"PREFIX sat: <{SAT_NS}>\n"
                    f"PREFIX legal: <{LEGAL_NS}>\n"
                    "SELECT DISTINCT ?norma ?componente ?obligacion WHERE {\n"
                    "  ?norma sat:hasComponent ?componente .\n"
                    "  ?componente legal:obligates ?obligacion .\n"
                    "}"
                ),
                highlights_algebra="join multi-salto (⊗) entre estructura SAT y obligaciones",
            )
        )

    if f"{LEGAL_NS}cites" in preds or f"{LEGAL_NS}amends" in preds or f"{LEGAL_NS}repeals" in preds:
        samples.append(
            SampleProvenanceQuery(
                id="normative-refs",
                title="Referencias y modificaciones normativas (UNION / ⊕)",
                question="¿Qué normas son citadas, modificadas o derogadas?",
                sparql=(
                    f"PREFIX legal: <{LEGAL_NS}>\n"
                    "SELECT DISTINCT ?origen ?norma_citada WHERE {\n"
                    "  { ?origen legal:cites ?norma_citada . }\n"
                    "  UNION\n"
                    "  { ?origen legal:amends ?norma_citada . }\n"
                    "  UNION\n"
                    "  { ?origen legal:repeals ?norma_citada . }\n"
                    "}"
                ),
                highlights_algebra="disyunción (⊕) de citas, reformas y derogaciones",
            )
        )

    if f"{LEGAL_NS}setsDeadline" in preds:
        samples.append(
            SampleProvenanceQuery(
                id="deadlines-filter",
                title="Plazos legales numéricos (FILTER)",
                question="¿Qué plazos legales establece la norma?",
                sparql=(
                    f"PREFIX legal: <{LEGAL_NS}>\n"
                    "SELECT DISTINCT ?sujeto ?plazo WHERE {\n"
                    "  ?sujeto legal:setsDeadline ?plazo .\n"
                    "  FILTER (?plazo > 0)\n"
                    "}\n"
                    "ORDER BY ASC(?plazo)"
                ),
                highlights_algebra="filtrado numérico XSD con trazabilidad exacta de ocurrencias",
            )
        )

    # Always guarantee a multi-hop join (⊗) over structural graph + attributes/clauses.
    samples.append(
        SampleProvenanceQuery(
            id="structure-multihop",
            title="Estructura multi-salto (Join / ⊗)",
            question="¿Cómo se relacionan la norma, sus componentes y sus encabezados?",
            sparql=(
                f"PREFIX sat: <{SAT_NS}>\n"
                "SELECT DISTINCT ?norma ?componente ?encabezado WHERE {\n"
                "  ?norma sat:hasComponent ?componente .\n"
                "  ?componente sat:hasHeading ?encabezado .\n"
                "}"
            ),
            highlights_algebra="join multi-salto (⊗) combinando pertenencia y encabezado",
        )
    )

    if not has_deontic or len(samples) < 3:
        samples.append(
            SampleProvenanceQuery(
                id="structure-union",
                title="Metadatos estructurales (UNION / ⊕)",
                question="¿Qué tipos y encabezados tienen los componentes de la norma?",
                sparql=(
                    f"PREFIX sat: <{SAT_NS}>\n"
                    "SELECT DISTINCT ?componente ?valor WHERE {\n"
                    "  { ?componente sat:hasHeading ?valor . }\n"
                    "  UNION\n"
                    "  { ?componente sat:hasKind ?valor . }\n"
                    "}"
                ),
                highlights_algebra="disyunción (⊕) combinando rutas alternativas",
            )
        )

    return tuple(samples[:5])


class DeterministicLegalExtractor:
    """Offline Peruvian legal triple extractor producing grounded RDF-star occurrences."""

    def extract(
        self,
        doc_payload: dict[str, Any],
        *,
        edition_override: dict[str, Any] | None = None,
        component_ids: Sequence[str] | None = None,
    ) -> GroundedGraph:
        doc_id, revision, source_kind, markdown, units, versions_by_comp = _build_source_units(
            doc_payload,
            edition_override=edition_override,
            component_ids=component_ids,
        )
        doc_title = str(doc_payload.get("title") or doc_id)
        doc_term = RDFTerm(kind="iri", value=_doc_iri(doc_id), label=doc_title)

        occurrences: list[StatementOccurrence] = []
        seen_tokens: set[str] = set()
        unlocalized = 0

        def add_occ(occ: StatementOccurrence | None) -> None:
            nonlocal unlocalized
            if occ is None:
                unlocalized += 1
                return
            if occ.token not in seen_tokens:
                seen_tokens.add(occ.token)
                occurrences.append(occ)

        # Avoid duplicating text-level extraction on container nodes (e.g. root instrument)
        # when child components already cover its body.
        parent_ids_with_children = {
            u.parent_id for u in units.values() if u.parent_id and u.parent_id in units
        }

        for unit in units.values():
            ver = versions_by_comp.get(unit.id, {})
            texts = ver.get("texts") or ()
            text_unit_id = str(texts[0]["id"]) if texts and texts[0].get("id") else None
            first_line = unit.text.split("\n", 1)[0].strip() or unit.label
            heading_quote = first_line[:240]
            comp_term = RDFTerm(
                kind="iri",
                value=_component_iri(doc_id, unit.id),
                label=unit.label,
            )

            # Pass 1: Structural SAT triples grounded to component heading.
            add_occ(
                _make_occurrence(
                    doc_id=doc_id,
                    unit=unit,
                    text_unit_id=text_unit_id,
                    subject=doc_term,
                    predicate=_predicate_term("sat:hasComponent", "sat:hasComponent"),
                    obj=comp_term,
                    subject_quote=doc_title,
                    predicate_quote=unit.kind,
                    object_quote=heading_quote,
                    origin="structural",
                    rule_id="sat-structure:has-component",
                    evidence_hint=heading_quote,
                    heading_label=heading_quote,
                    allow_inferred_subject=True,
                )
            )
            add_occ(
                _make_occurrence(
                    doc_id=doc_id,
                    unit=unit,
                    text_unit_id=text_unit_id,
                    subject=comp_term,
                    predicate=_predicate_term("sat:hasHeading", "sat:hasHeading"),
                    obj=RDFTerm(kind="literal", value=heading_quote, label=heading_quote, language="es"),
                    subject_quote=unit.label,
                    predicate_quote=heading_quote,
                    object_quote=heading_quote,
                    origin="structural",
                    rule_id="sat-structure:has-heading",
                    evidence_hint=heading_quote,
                    heading_label=heading_quote,
                    allow_inferred_subject=True,
                )
            )
            add_occ(
                _make_occurrence(
                    doc_id=doc_id,
                    unit=unit,
                    text_unit_id=text_unit_id,
                    subject=comp_term,
                    predicate=_predicate_term("sat:hasKind", "sat:hasKind"),
                    obj=RDFTerm(kind="literal", value=unit.kind, label=unit.kind, datatype=XSD_STRING_IRI),
                    subject_quote=heading_quote,
                    predicate_quote=unit.kind,
                    object_quote=heading_quote,
                    origin="structural",
                    rule_id="sat-structure:has-kind",
                    evidence_hint=heading_quote,
                    heading_label=heading_quote,
                    allow_inferred_subject=True,
                )
            )
            if unit.parent_id and unit.parent_id in units:
                parent_unit = units[unit.parent_id]
                parent_term = RDFTerm(
                    kind="iri",
                    value=_component_iri(doc_id, parent_unit.id),
                    label=parent_unit.label,
                )
                add_occ(
                    _make_occurrence(
                        doc_id=doc_id,
                        unit=unit,
                        text_unit_id=text_unit_id,
                        subject=comp_term,
                        predicate=_predicate_term("sat:partOf", "sat:partOf"),
                        obj=parent_term,
                        subject_quote=heading_quote,
                        predicate_quote=unit.kind,
                        object_quote=heading_quote,
                        origin="structural",
                        rule_id="sat-structure:part-of",
                        evidence_hint=heading_quote,
                        heading_label=heading_quote,
                        allow_inferred_subject=True,
                    )
                )

            amending = ver.get("amending_source")
            if isinstance(amending, dict) and amending.get("title"):
                amend_title = str(amending["title"])
                amend_term = RDFTerm(kind="iri", value=_norm_ref_iri(amend_title), label=amend_title)
                add_occ(
                    _make_occurrence(
                        doc_id=doc_id,
                        unit=unit,
                        text_unit_id=text_unit_id,
                        subject=comp_term,
                        predicate=_predicate_term("sat:amendedBy", "sat:amendedBy"),
                        obj=amend_term,
                        subject_quote=heading_quote,
                        predicate_quote="modificado",
                        object_quote=heading_quote,
                        origin="structural",
                        rule_id="sat-structure:amended-by",
                        evidence_hint=heading_quote,
                        heading_label=heading_quote,
                        allow_inferred_subject=True,
                    )
                )

            # Skip semantic/clause passes on broad structural containers that have child units.
            if unit.id in parent_ids_with_children and unit.kind in (
                "instrument",
                "document",
                "titulo",
                "capitulo",
                "seccion",
            ):
                continue

            # Pass 2 & 3: Sentence-level normative references and deontic/semantic clauses.
            for raw_sentence in _SENTENCE_SPLIT_RE.split(unit.text):
                sentence = raw_sentence.strip()
                if len(sentence) < 12:
                    continue

                # Pass 2: Normative cross-references.
                for ref_match in _NORM_REF_RE.finditer(sentence):
                    ref_surface = ref_match.group(1).strip()
                    # Avoid self-citing the component's own article heading at the start of the line.
                    if ref_match.start() == 0 and sentence.startswith(heading_quote[: len(ref_surface)]):
                        continue
                    if _AMEND_VERB_RE.search(sentence):
                        pred_key, pred_label, verb_m = "legal:amends", "legal:amends", _AMEND_VERB_RE.search(sentence)
                    elif _REPEAL_VERB_RE.search(sentence):
                        pred_key, pred_label, verb_m = "legal:repeals", "legal:repeals", _REPEAL_VERB_RE.search(sentence)
                    elif _INCORP_VERB_RE.search(sentence):
                        pred_key, pred_label, verb_m = "legal:incorporates", "legal:incorporates", _INCORP_VERB_RE.search(sentence)
                    else:
                        pred_key, pred_label, verb_m = "legal:cites", "legal:cites", _CITE_VERB_RE.search(sentence)
                    pred_quote = verb_m.group(0) if verb_m else ref_surface
                    add_occ(
                        _make_occurrence(
                            doc_id=doc_id,
                            unit=unit,
                            text_unit_id=text_unit_id,
                            subject=comp_term,
                            predicate=_predicate_term(pred_key, pred_label),
                            obj=RDFTerm(kind="iri", value=_norm_ref_iri(ref_surface), label=ref_surface),
                            subject_quote=unit.label,
                            predicate_quote=pred_quote,
                            object_quote=ref_surface,
                            origin="deterministic_legal",
                            rule_id=f"norm-ref:{pred_key.split(':', 1)[1]}",
                            evidence_hint=sentence,
                            heading_label=heading_quote,
                            allow_inferred_subject=True,
                        )
                    )

                # Pass 3a: Numeric deadline extraction (xsd:integer).
                for dl_match in _DEADLINE_RE.finditer(sentence):
                    num_str = dl_match.group("num")
                    phrase = dl_match.group(0).strip()
                    verb_q = dl_match.group("verb").strip()
                    subj_match = _ENTITY_SUBJECT_RE.search(sentence)
                    if subj_match:
                        subj_label = subj_match.group(1).strip()
                        subj_term = RDFTerm(kind="iri", value=_entity_iri(subj_label), label=subj_label)
                    else:
                        subj_label = unit.label
                        subj_term = comp_term
                    add_occ(
                        _make_occurrence(
                            doc_id=doc_id,
                            unit=unit,
                            text_unit_id=text_unit_id,
                            subject=subj_term,
                            predicate=_predicate_term("legal:setsDeadline", "legal:setsDeadline"),
                            obj=RDFTerm(
                                kind="literal",
                                value=num_str,
                                label=phrase,
                                datatype=XSD_INTEGER_IRI,
                            ),
                            subject_quote=subj_label,
                            predicate_quote=verb_q,
                            object_quote=phrase,
                            origin="deterministic_legal",
                            rule_id="legal-deadline-v1",
                            evidence_hint=sentence,
                            heading_label=heading_quote,
                            allow_inferred_subject=True,
                        )
                    )

                # Pass 3b: Deontic & semantic patterns.
                for pred_key, rule_id, _desc, pattern in _DEONTIC_RULES:
                    match = pattern.search(sentence)
                    if not match:
                        continue
                    verb_quote = match.group("verb").strip()
                    obj_text = match.group("obj").strip(" ,;:")
                    if len(obj_text) < 4:
                        continue
                    prefix_text = sentence[: match.start()].strip()
                    entity_m = _ENTITY_SUBJECT_RE.search(prefix_text)
                    if entity_m:
                        subj_label = entity_m.group(1).strip()
                        subj_term = RDFTerm(kind="iri", value=_entity_iri(subj_label), label=subj_label)
                    else:
                        subj_label = unit.label
                        subj_term = comp_term
                    add_occ(
                        _make_occurrence(
                            doc_id=doc_id,
                            unit=unit,
                            text_unit_id=text_unit_id,
                            subject=subj_term,
                            predicate=_predicate_term(pred_key, pred_key),
                            obj=RDFTerm(kind="literal", value=obj_text, label=obj_text, language="es"),
                            subject_quote=subj_label,
                            predicate_quote=verb_quote,
                            object_quote=obj_text,
                            origin="deterministic_legal",
                            rule_id=rule_id,
                            evidence_hint=sentence,
                            heading_label=heading_quote,
                            allow_inferred_subject=True,
                        )
                    )

        occ_tuple = tuple(occurrences)
        by_token = {occ.token: idx for idx, occ in enumerate(occ_tuple)}
        predicates = tuple(sorted({occ.predicate.value for occ in occ_tuple}))
        samples = _generate_sample_queries(occ_tuple)

        return GroundedGraph(
            doc_id=doc_id,
            revision=revision,
            source_kind=source_kind,
            markdown_sha256=sha256(markdown.encode("utf-8")).hexdigest(),
            namespaces=dict(DEFAULT_NAMESPACES),
            source_units=units,
            occurrences=occ_tuple,
            by_token=by_token,
            predicates=predicates,
            sample_queries=samples,
            cohere_used=False,
            unlocalized_discarded=unlocalized,
            document_markdown=markdown,
        )


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

_COHERE_EXTRACTION_PREAMBLE = (
    "You are a legal knowledge graph extractor for Peruvian statutes. "
    "Return ONLY a JSON array of objects with keys: "
    "subject, predicate, object, subject_quote, predicate_quote, object_quote, datatype (optional). "
    "Allowed predicates: legal:obligates, legal:prohibits, legal:defines, legal:grantsRight, "
    "legal:setsDeadline, legal:sanctions, legal:assignsCompetence, legal:cites, legal:amends, legal:repeals. "
    "Every quote MUST appear verbatim in the provided legal text."
)

_ALLOWED_LLM_PREDICATES = {
    "legal:obligates",
    "legal:prohibits",
    "legal:defines",
    "legal:grantsRight",
    "legal:setsDeadline",
    "legal:sanctions",
    "legal:assignsCompetence",
    "legal:cites",
    "legal:amends",
    "legal:repeals",
    "legal:incorporates",
}


class CohereGroundedExtractor:
    """Optional Cohere-assisted triple extractor gated strictly by localize_evidence()."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("COHERE_API_KEY es requerida para extracción híbrida con Cohere")
        from services.cohere_chat import CohereChat

        self.model = model
        self.client = CohereChat(api_key)

    async def extract(
        self,
        doc_payload: dict[str, Any],
        *,
        base_graph: GroundedGraph,
        max_units: int = 12,
    ) -> GroundedGraph:
        occurrences = list(base_graph.occurrences)
        seen_tokens = {occ.token for occ in occurrences}
        discarded = base_graph.unlocalized_discarded

        candidate_units = [
            u for u in base_graph.source_units.values() if len(u.text.strip()) >= 20
        ][:max_units]

        for unit in candidate_units:
            prompt = (
                f"Documento: {base_graph.doc_id}\n"
                f"Componente ({unit.kind}): {unit.label}\n"
                f"Texto literal:\n{unit.text[:4000]}\n\n"
                "Extrae tripletas jurídicas verificables en formato JSON."
            )
            response = await self.client.chat(
                message=prompt,
                preamble=_COHERE_EXTRACTION_PREAMBLE,
                model=self.model,
                temperature=0.0,
            )
            raw_text = _JSON_FENCE_RE.sub("", (response.text or "").strip()).strip()
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError:
                discarded += 1
                continue
            if not isinstance(parsed, list):
                discarded += 1
                continue

            heading_line = unit.text.split("\n", 1)[0].strip()
            for item in parsed:
                if not isinstance(item, dict):
                    discarded += 1
                    continue
                pred_key = str(item.get("predicate") or "").strip()
                if pred_key not in _ALLOWED_LLM_PREDICATES:
                    discarded += 1
                    continue
                subj_val = str(item.get("subject") or "").strip()
                obj_val = str(item.get("object") or "").strip()
                subj_quote = str(item.get("subject_quote") or subj_val).strip()
                pred_quote = str(item.get("predicate_quote") or "").strip()
                obj_quote = str(item.get("object_quote") or obj_val).strip()
                if not subj_val or not obj_val or not obj_quote:
                    discarded += 1
                    continue

                dtype = item.get("datatype")
                if dtype == "xsd:integer" or (pred_key == "legal:setsDeadline" and obj_val.isdigit()):
                    obj_term = RDFTerm(
                        kind="literal",
                        value=obj_val,
                        label=obj_quote,
                        datatype=XSD_INTEGER_IRI,
                    )
                elif pred_key in ("legal:cites", "legal:amends", "legal:repeals", "legal:incorporates"):
                    obj_term = RDFTerm(kind="iri", value=_norm_ref_iri(obj_val), label=obj_val)
                else:
                    obj_term = RDFTerm(kind="literal", value=obj_val, label=obj_val, language="es")

                subj_term = RDFTerm(kind="iri", value=_entity_iri(subj_val), label=subj_val)
                occ = _make_occurrence(
                    doc_id=base_graph.doc_id,
                    unit=unit,
                    text_unit_id=None,
                    subject=subj_term,
                    predicate=_predicate_term(pred_key, pred_key),
                    obj=obj_term,
                    subject_quote=subj_quote,
                    predicate_quote=pred_quote,
                    object_quote=obj_quote,
                    origin="cohere_llm",
                    rule_id=f"cohere:{self.model}",
                    heading_label=heading_line,
                    allow_inferred_subject=False,
                )
                if occ is None:
                    discarded += 1
                    continue
                if occ.token not in seen_tokens:
                    seen_tokens.add(occ.token)
                    occurrences.append(occ)

        occ_tuple = tuple(occurrences)
        return GroundedGraph(
            doc_id=base_graph.doc_id,
            revision=base_graph.revision,
            source_kind=base_graph.source_kind,
            markdown_sha256=base_graph.markdown_sha256,
            namespaces=dict(base_graph.namespaces),
            source_units=base_graph.source_units,
            occurrences=occ_tuple,
            by_token={occ.token: idx for idx, occ in enumerate(occ_tuple)},
            predicates=tuple(sorted({occ.predicate.value for occ in occ_tuple})),
            sample_queries=_generate_sample_queries(occ_tuple),
            cohere_used=True,
            unlocalized_discarded=discarded,
            document_markdown=base_graph.document_markdown,
        )
