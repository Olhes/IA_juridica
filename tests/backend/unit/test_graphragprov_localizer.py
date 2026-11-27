"""Unit tests for deterministic Unicode evidence localization and RDF-star export."""
from __future__ import annotations

import pytest

from services.graphragprov.localizer import (
    export_rdf_star_ntriples,
    format_occurrence_rdf_star,
    localize_evidence,
    mint_occurrence_token,
)
from services.graphragprov.models import (
    DEFAULT_NAMESPACES,
    GroundedGraph,
    RDFTerm,
    SourceUnitText,
    StatementOccurrence,
)


def test_localize_evidence_exact_unicode_codepoints_with_accents_n_tilde_and_emoji():
    prefix = "Encabezado 😀\n"
    comp_text = "Artículo 1. El Poder Judicial deberá garantizar protección integral a la niñez ñ y 😀."
    full_markdown = prefix + comp_text
    comp_offset = len(prefix)

    spans = localize_evidence(
        comp_text,
        "Poder Judicial",
        "deberá garantizar",
        "protección integral a la niñez ñ y 😀",
        component_start_in_doc=comp_offset,
        component_id="art1",
        version_id="v:art1",
        text_unit_id="t:art1",
    )
    assert spans is not None
    assert spans.subject_span is not None
    assert spans.predicate_span is not None
    assert spans.object_span is not None
    assert spans.subject_span.quality == "exact"
    assert spans.object_span.quality == "exact"

    # Verify exact Unicode codepoint slicing against full document markdown.
    assert full_markdown[spans.subject_span.start : spans.subject_span.end] == "Poder Judicial"
    assert full_markdown[spans.predicate_span.start : spans.predicate_span.end] == "deberá garantizar"
    assert (
        full_markdown[spans.object_span.start : spans.object_span.end]
        == "protección integral a la niñez ñ y 😀"
    )
    assert (
        full_markdown[spans.doc_evidence_span.start : spans.doc_evidence_span.end]
        == spans.doc_evidence_span.surface_text
    )
    assert spans.doc_evidence_span.start == comp_offset + spans.evidence_span.start
    assert spans.doc_evidence_span.end == comp_offset + spans.evidence_span.end


def test_localize_evidence_normalized_diacritics_and_whitespace_maps_back_to_exact_codepoints():
    comp_text = "Artículo 2.\nLa  entidad   pública  deberá   remitir   información   periódica."
    spans = localize_evidence(
        comp_text,
        "entidad publica",
        "debera remitir",
        "informacion periodica",
        component_start_in_doc=10,
        component_id="art2",
    )
    assert spans is not None
    assert spans.subject_span is not None and spans.subject_span.quality == "normalized"
    assert spans.object_span is not None and spans.object_span.quality == "normalized"
    assert spans.subject_span.surface_text == "entidad   pública"
    assert spans.object_span.surface_text == "información   periódica"
    assert comp_text[spans.object_span.start - 10 : spans.object_span.end - 10] == "información   periódica"


def test_localize_evidence_span_width_minimization_picks_closest_cooccurrence():
    comp_text = (
        "El Estado promueve políticas generales en todo el territorio nacional. "
        "En materia alimentaria, el Estado garantiza pensión justa de manera inmediata."
    )
    spans = localize_evidence(
        comp_text,
        "Estado",
        "garantiza",
        "pensión justa",
        component_start_in_doc=0,
        component_id="art3",
    )
    assert spans is not None
    assert spans.subject_span is not None
    assert spans.object_span is not None
    # Must choose the second "Estado" (inside the second sentence), minimizing span width.
    second_sentence_start = comp_text.index("En materia alimentaria")
    assert spans.subject_span.start >= second_sentence_start
    assert spans.evidence_span.start >= second_sentence_start


def test_localize_evidence_heading_inherited_subject_and_ungrounded_rejection():
    comp_text = "Artículo 5. Deberes.\nSe prohíbe cobrar tasas adicionales por el trámite."
    spans = localize_evidence(
        comp_text,
        "Artículo 5",
        "Se prohíbe",
        "cobrar tasas adicionales por el trámite",
        component_start_in_doc=0,
        component_id="art5",
        heading_label="Artículo 5",
        allow_inferred_subject=True,
    )
    assert spans is not None
    assert spans.subject_span is not None
    assert spans.subject_span.quality == "inferred_from_heading"
    assert spans.subject_span.surface_text == "Artículo 5"

    # When heading does not contain the subject and allow_inferred_subject=True, subject_span is None.
    no_subj = localize_evidence(
        "Se prohíbe cobrar tasas adicionales.",
        "Entidad Implícita",
        "Se prohíbe",
        "cobrar tasas adicionales",
        component_start_in_doc=0,
        component_id="art5b",
        allow_inferred_subject=True,
    )
    assert no_subj is not None
    assert no_subj.subject_span is None
    assert no_subj.object_span is not None

    # Ungrounded object is strictly rejected (returns None).
    rejected = localize_evidence(
        comp_text,
        "Artículo 5",
        "obliga",
        "texto completamente inventado por un modelo",
        component_start_in_doc=0,
        component_id="art5",
        allow_inferred_subject=False,
    )
    assert rejected is None


def test_mint_occurrence_token_determinism_and_rdf_star_ntriples_export():
    s = RDFTerm(kind="iri", value="http://iajuridica.pe/entity/poder_judicial", label="Poder Judicial")
    p = RDFTerm(kind="iri", value="http://iajuridica.pe/legal/obligates", label="legal:obligates")
    o = RDFTerm(kind="literal", value="administrar el REDAM", label="administrar el REDAM", language="es")

    tok1 = mint_occurrence_token("pe:ley:28970", "art1", 0, 40, s, p, o)
    tok1_repeat = mint_occurrence_token("pe:ley:28970", "art1", 0, 40, s, p, o)
    tok2 = mint_occurrence_token("pe:ley:28970", "art2", 45, 90, s, p, o)

    assert tok1 == tok1_repeat
    assert tok1.startswith("occ_") and len(tok1) == 16
    assert tok1 != tok2

    comp_text = "El Poder Judicial deberá administrar el REDAM."
    spans = localize_evidence(
        comp_text, "Poder Judicial", "deberá", "administrar el REDAM",
        component_start_in_doc=100, component_id="art1",
    )
    assert spans is not None
    nt_block = format_occurrence_rdf_star(tok1, "pe:ley:28970", s, p, o, spans)
    assert "<< <http://iajuridica.pe/entity/poder_judicial>" in nt_block
    assert "textprov/occurrenceOf> <urn:textprov:occ:" in nt_block
    assert '"100"^^<http://www.w3.org/2001/XMLSchema#integer>' in nt_block

    occ = StatementOccurrence(
        token=tok1,
        doc_id="pe:ley:28970",
        passage_id="t:art1",
        subject=s,
        predicate=p,
        object=o,
        origin="deterministic_legal",
        confidence_rule="test-rule",
        spans=spans,
        rdf_star_nt=nt_block,
    )
    graph = GroundedGraph(
        doc_id="pe:ley:28970",
        revision="rev:1",
        source_kind="published",
        markdown_sha256="a" * 64,
        namespaces=dict(DEFAULT_NAMESPACES),
        source_units={
            "art1": SourceUnitText(
                id="art1", label="Artículo 1", kind="article", text=comp_text, global_start=100, global_end=100 + len(comp_text)
            )
        },
        occurrences=(occ,),
        by_token={tok1: 0},
        predicates=(p.value,),
        sample_queries=(),
    )
    exported = export_rdf_star_ntriples(graph)
    assert f"# GraphRAGProv RDF-star N-Triples export for pe:ley:28970 (rev:1)" in exported
    assert tok1 in exported
