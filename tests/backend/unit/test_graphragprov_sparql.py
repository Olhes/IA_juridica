"""Unit tests for the pure-Python SPARQL SELECT parser and N[X] provenance evaluator."""
from __future__ import annotations

import pytest

from services.graphragprov.localizer import format_occurrence_rdf_star, localize_evidence, mint_occurrence_token
from services.graphragprov.models import (
    DEFAULT_NAMESPACES,
    EvalLimits,
    GroundedGraph,
    RDFTerm,
    RDF_TYPE_IRI,
    SourceUnitText,
    StatementOccurrence,
    XSD_INTEGER_IRI,
)
from services.graphragprov.sparql import (
    SparqlSafetyError,
    SparqlSyntaxError,
    evaluate_sparql,
    parse_sparql,
)

SAT = DEFAULT_NAMESPACES["sat"]
LEGAL = DEFAULT_NAMESPACES["legal"]
ENTITY = DEFAULT_NAMESPACES["entity"]


def _iri(val: str, label: str) -> RDFTerm:
    return RDFTerm(kind="iri", value=val, label=label)


def _lit(val: str, *, lang: str | None = "es", dt: str | None = None) -> RDFTerm:
    return RDFTerm(kind="literal", value=val, label=val, language=None if dt else lang, datatype=dt)


def _build_fixture_graph() -> GroundedGraph:
    text = (
        "Artículo 1. El Poder Judicial deberá crear el REDAM en un plazo de 15 días. "
        "Artículo 2. El Poder Judicial deberá administrar el REDAM y prohíbe cobros indebidos. "
        "Artículo 3. El Ministerio de la Mujer deberá supervisar en un plazo de 30 días."
    )
    units = {
        "art1": SourceUnitText(id="art1", label="Artículo 1", kind="article", text=text, global_start=0, global_end=len(text)),
    }
    raw_triples = [
        # Two separate occurrences of (norm, hasComponent, art1) / (pj, obligates, ...) to test multiplicity & joins
        ("art1", 0, 20, _iri(f"{ENTITY}norma", "Ley 28970"), _iri(f"{SAT}hasComponent", "sat:hasComponent"), _iri(f"{ENTITY}art1", "Artículo 1"), "Artículo 1"),
        ("art1", 12, 74, _iri(f"{ENTITY}art1", "Artículo 1"), _iri(f"{LEGAL}obligates", "legal:obligates"), _iri(f"{ENTITY}pj", "Poder Judicial"), "Poder Judicial"),
        ("art1", 12, 74, _iri(f"{ENTITY}pj", "Poder Judicial"), _iri(f"{LEGAL}setsDeadline", "legal:setsDeadline"), _lit("15", dt=XSD_INTEGER_IRI), "15 días"),
        ("art1", 75, 160, _iri(f"{ENTITY}pj", "Poder Judicial"), _iri(f"{LEGAL}prohibits", "legal:prohibits"), _lit("cobros indebidos"), "cobros indebidos"),
        ("art1", 75, 160, _iri(f"{ENTITY}art1", "Artículo 1"), _iri(f"{LEGAL}obligates", "legal:obligates"), _iri(f"{ENTITY}pj", "Poder Judicial"), "administrar el REDAM"),
        ("art1", 161, len(text), _iri(f"{ENTITY}mimp", "MIMP"), _iri(f"{LEGAL}setsDeadline", "legal:setsDeadline"), _lit("30", dt=XSD_INTEGER_IRI), "30 días"),
        ("art1", 161, len(text), _iri(f"{ENTITY}mimp", "MIMP"), _iri(RDF_TYPE_IRI, "rdf:type"), _iri(f"{ENTITY}entidad", "Entidad"), "Ministerio de la Mujer"),
    ]
    occurrences: list[StatementOccurrence] = []
    for cid, start, end, s, p, o, obj_q in raw_triples:
        spans = localize_evidence(
            text, s.label, p.label, obj_q,
            component_start_in_doc=0, component_id=cid, allow_inferred_subject=True,
        )
        assert spans is not None
        tok = mint_occurrence_token("pe:ley:test", cid, start, end, s, p, o)
        nt = format_occurrence_rdf_star(tok, "pe:ley:test", s, p, o, spans)
        occurrences.append(
            StatementOccurrence(
                token=tok,
                doc_id="pe:ley:test",
                passage_id=cid,
                subject=s,
                predicate=p,
                object=o,
                origin="deterministic_legal",
                confidence_rule="fixture",
                spans=spans,
                rdf_star_nt=nt,
            )
        )
    occ_tuple = tuple(occurrences)
    return GroundedGraph(
        doc_id="pe:ley:test",
        revision="rev:1",
        source_kind="published",
        markdown_sha256="b" * 64,
        namespaces=dict(DEFAULT_NAMESPACES),
        source_units=units,
        occurrences=occ_tuple,
        by_token={occ.token: idx for idx, occ in enumerate(occ_tuple)},
        predicates=tuple(sorted({occ.predicate.value for occ in occ_tuple})),
        sample_queries=(),
    )


def test_multihop_join_and_duplicate_occurrence_produce_product_and_sum_provenance():
    graph = _build_fixture_graph()
    # Two distinct occurrences assert (art1, legal:obligates, pj).
    # Joining (norm hasComponent ?art) with (?art obligates ?ent) and (?ent setsDeadline ?d)
    # produces (t_comp ⊗ t_obl1 ⊗ t_dl) ⊕ (t_comp ⊗ t_obl2 ⊗ t_dl)!
    query = f"""
    PREFIX sat: <{SAT}>
    PREFIX legal: <{LEGAL}>
    SELECT DISTINCT ?norma ?ent ?plazo WHERE {{
      ?norma sat:hasComponent ?art .
      ?art legal:obligates ?ent .
      ?ent legal:setsDeadline ?plazo .
    }}
    """
    result = evaluate_sparql(graph, query)
    assert result.variables == ("norma", "ent", "plazo")
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.bindings["plazo"].value == "15"
    assert row.polynomial.total_multiplicity == 2
    assert len(row.polynomial.monomials) == 2
    assert "⊗" in row.polynomial.infix_display
    assert "⊕" in row.polynomial.infix_display
    for mon in row.polynomial.monomials:
        assert len(mon.factors) == 3


def test_optional_preserves_unmatched_left_rows_and_multiplies_matched_rows():
    graph = _build_fixture_graph()
    query = f"""
    PREFIX legal: <{LEGAL}>
    SELECT ?ent ?plazo ?proh WHERE {{
      ?ent legal:setsDeadline ?plazo .
      OPTIONAL {{ ?ent legal:prohibits ?proh . }}
    }}
    ORDER BY ASC(?plazo)
    """
    result = evaluate_sparql(graph, query)
    assert len(result.rows) == 2
    # Row 0: PJ (plazo=15) matched OPTIONAL prohibits -> 2-factor product
    r0 = result.rows[0]
    assert r0.bindings["plazo"].value == "15"
    assert r0.bindings["proh"] is not None
    assert len(r0.polynomial.monomials[0].factors) == 2
    # Row 1: MIMP (plazo=30) had no prohibits -> preserved with 1-factor provenance (p_L * 1)
    r1 = result.rows[1]
    assert r1.bindings["plazo"].value == "30"
    assert r1.bindings["proh"] is None
    assert len(r1.polynomial.monomials[0].factors) == 1


def test_union_sums_provenance_on_matching_bindings():
    graph = _build_fixture_graph()
    query = f"""
    PREFIX legal: <{LEGAL}>
    SELECT ?ent WHERE {{
      {{ ?ent legal:setsDeadline ?d . }}
      UNION
      {{ ?ent legal:prohibits ?p . }}
    }}
    """
    result = evaluate_sparql(graph, query)
    by_ent = {row.bindings["ent"].value: row for row in result.rows}
    pj_row = by_ent[f"{ENTITY}pj"]
    mimp_row = by_ent[f"{ENTITY}mimp"]
    # PJ matched both UNION branches -> 2 monomials summed with ⊕
    assert len(pj_row.polynomial.monomials) == 2
    assert "⊕" in pj_row.polynomial.infix_display
    assert len(mimp_row.polynomial.monomials) == 1


def test_filter_operators_functions_shorthands_and_pagination():
    graph = _build_fixture_graph()
    # Test `;`, `a` shorthand, REGEX, CONTAINS, LCASE, STR, BOUND, ISIRI, ISLITERAL, LANG, DATATYPE, ORDER BY, LIMIT/OFFSET
    query = f"""
    PREFIX legal: <{LEGAL}>
    SELECT * WHERE {{
      ?ent a <{ENTITY}entidad> ;
           legal:setsDeadline ?plazo .
      FILTER (?plazo >= 20 && ISIRI(?ent) && ISLITERAL(?plazo) && BOUND(?plazo) && REGEX(STR(?ent), "mimp", "i"))
    }}
    LIMIT 5 OFFSET 0
    """
    result = evaluate_sparql(graph, query)
    assert len(result.rows) == 1
    assert result.rows[0].bindings["plazo"].value == "30"

    # LANG / CONTAINS / LCASE / !=
    q_lang = f"""
    PREFIX legal: <{LEGAL}>
    SELECT ?proh WHERE {{
      ?ent legal:prohibits ?proh .
      FILTER (LANG(?proh) = "es" && CONTAINS(LCASE(STR(?proh)), "indebidos") && !(?proh = "otra"))
    }}
    """
    r_lang = evaluate_sparql(graph, q_lang)
    assert len(r_lang.rows) == 1


def test_safety_limits_reject_mutations_excessive_work_deep_ast_and_unsafe_regex():
    graph = _build_fixture_graph()

    for bad_mutation in (
        "INSERT DATA { <a> <b> <c> }",
        "DELETE WHERE { ?s ?p ?o }",
        "DROP ALL",
        "CLEAR GRAPH <http://example.org>",
    ):
        with pytest.raises(SparqlSafetyError):
            parse_sparql(bad_mutation)

    with pytest.raises(SparqlSyntaxError):
        parse_sparql("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")

    with pytest.raises(SparqlSafetyError):
        evaluate_sparql(
            graph,
            "SELECT * WHERE { ?a ?b ?c . ?d ?e ?f . }",
            limits=EvalLimits(max_join_work=5),
        )

    with pytest.raises(SparqlSafetyError):
        parse_sparql(
            'SELECT ?x WHERE { ?s ?p ?x . FILTER (REGEX(STR(?x), "(a+)+$")) }',
        )

    with pytest.raises(SparqlSafetyError):
        parse_sparql(
            'SELECT ?x WHERE { ?s ?p ?x . FILTER (REGEX(STR(?x), "' + ("a" * 300) + '")) }',
            limits=EvalLimits(max_regex_len=64),
        )
