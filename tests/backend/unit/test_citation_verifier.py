"""Extracción y verificación determinista de citas (sin modelos)."""

import pytest

from services.citation_verifier import (
    citation_matches,
    despace,
    extract_citations,
    verify_citations,
)


def keys(text):
    return [c.key for c in extract_citations(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Prelación (Art. 475 CC)", ["cc:art:475"]),
        ("Excepción (Art; 478): la deuda pasa al siguiente", ["art:478"]),
        ("según el artículo 26 de la Ley N.° 30364", ["ley30364:art:26", "ley:30364"]),
        ("Arts. 74 y 418 del Código Civil", ["cc:art:74", "cc:art:418"]),
        ("Art. 2, inc. 24, lit. C, Constitución Política", ["const:art:2"]),
        ("Art. 122-B del Código Penal", ["cp:art:122-b"]),
        ("Art. 648 CPC y Art. 344 CPP", ["cpc:art:648", "cpp:art:344"]),
        ("Casación 1293-2021, Piura", ["casacion:1293-2021"]),
        ("Decreto Supremo N.° 009-2016-MIMP", ["ds:009-2016-mimp"]),
        ("Ley N. 0 30364", ["ley:30364"]),
        ("Sin ninguna norma citada", []),
    ],
)
def test_extracts_normalised_citation_keys(text, expected):
    assert keys(text) == expected


def test_extraction_keeps_the_original_text_of_each_citation():
    (citation,) = extract_citations("Lo dispone el Artículo 475 del Código Civil.")
    assert citation.raw == "Artículo 475"


def test_code_is_not_borrowed_from_a_later_citation():
    assert keys("el Art; 478, la Ley 30364") == ["art:478", "ley:30364"]


def test_codeless_article_matches_by_number_but_different_codes_do_not():
    assert citation_matches("cc:art:475", "art:475") and citation_matches("art:475", "cc:art:475")
    assert not citation_matches("cc:art:475", "cp:art:475")
    assert not citation_matches("cc:art:475", "cc:art:476")


def test_despace_joins_letter_spaced_ocr_runs():
    assert despace("e l a r t í c u l o 8 d e l a l e y") == "elartículo8delaley"
    assert despace("Texto normal con palabras") == "Texto normal con palabras"


def test_verification_marks_traceable_and_untraceable_citations_with_excerpt():
    evidence = [{"source": "guia.md", "text": "Prelación de obligados (Art. 475 CC). Ley N. 0 30364 sobre violencia."}]
    results = verify_citations("Aplican la Ley 30364, el artículo 475 CC y la Casación 999-2020.", evidence)
    by_key = {r["key"]: r for r in results}
    assert by_key["ley:30364"]["status"] == "verified" and by_key["ley:30364"]["source"] == "guia.md"
    assert by_key["cc:art:475"]["status"] == "verified" and "475" in by_key["cc:art:475"]["excerpt"]
    assert by_key["casacion:999-2020"] == {
        "key": "casacion:999-2020", "text": "Casación 999-2020", "status": "unverified", "source": None, "excerpt": None,
    }


def test_verification_reads_spaced_ocr_evidence():
    spaced = "e l a r t í c u l o 8 d e l a l e y e s t a b l e c e l o s t i p o s"
    results = verify_citations("Ver el artículo 8.", [{"source": "ocr.md", "text": spaced}])
    assert results[0]["status"] == "verified"


def test_law_citation_is_traceable_to_the_retrieved_document_title():
    """El título de la fuente nombra la norma aunque el fragmento sea solo el artículo."""
    evidence = [{"source": "Ley 28970", "text": "Artículo 3.- La licencia municipal es gratuita."}]
    (result,) = verify_citations("La Ley 28970 regula la licencia municipal.", evidence)
    assert result["status"] == "verified" and result["source"] == "Ley 28970"


def test_verification_without_evidence_leaves_everything_unverified():
    assert [r["status"] for r in verify_citations("Ley 30364 y artículo 8", [])] == ["unverified", "unverified"]


def test_verification_requires_the_cited_law_not_a_number_or_unqualified_article():
    assert verify_citations("Ley 31464", [{"source": "Nota", "text": "Teléfono 991314649"}])[0]["status"] == "unverified"
    evidence = [{"source": "Código de los Niños y Adolescentes", "text": "Artículo 164-A. Postulación."}]
    by_key = {r["key"]: r for r in verify_citations("artículo 164-A de la Ley 31464", evidence)}
    assert by_key["ley31464:art:164-a"]["status"] == "unverified"
    evidence[0]["citation"] = "Artículo 164-A de la Ley 31464"
    assert verify_citations("artículo 164-A de la Ley 31464", evidence)[0]["status"] == "verified"


def test_sat_section_does_not_hide_a_misattributed_article():
    from services.legal_queries import _response_citations

    documents = [{"content": "Artículo 164-A. Postulación.", "metadata": {
        "retrieval_origin": "sat", "title": "Código de los Niños y Adolescentes",
        "sat_section": {"version_id": "v1", "title": "Artículo 164-A"},
    }}]
    checks = _response_citations("artículo 164-A de la Ley 31464", documents)
    assert next(c for c in checks if c["key"] == "ley31464:art:164-a")["status"] == "unverified"


def test_extracts_decreto_legislativo_and_dl_qualified_articles():
    assert keys("Decreto Legislativo N.° 768 y DL 635") == ["dl:768", "dl:635"]
    assert keys("artículo 2 del D.L. 1377") == ["dl1377:art:2", "dl:1377"]


def test_verification_inherits_code_from_evidence_source_without_allowing_misattribution():
    evidence = [
        {
            "source": "Código Procesal Civil — DL 768 / TUO RM 010-93-JUS",
            "text": "Artículo 566.- Ejecución anticipada y ejecución forzada.",
        },
        {
            "source": "Código Penal — DL 635, copia del Congreso",
            "text": "Artículo 149°.- Omisión de prestación de alimentos.",
        },
        {
            "source": "Ley 27337 — Código de los Niños y Adolescentes",
            "text": "Artículo 96º.- Competencia.",
        },
    ]
    answer = (
        "Aplica el art. 566 del Código Procesal Civil (DL 768), "
        "el art. 149 del Código Penal, el art. 96 del Código de los Niños y Adolescentes, "
        "y no el art. 566 del Código Penal."
    )
    by_key = {r["key"]: r for r in verify_citations(answer, evidence)}
    assert by_key["cpc:art:566"]["status"] == "verified"
    assert by_key["cpc:art:566"]["source"] == "Código Procesal Civil — DL 768 / TUO RM 010-93-JUS"
    assert by_key["dl:768"]["status"] == "verified"
    assert by_key["cp:art:149"]["status"] == "verified"
    assert by_key["cna:art:96"]["status"] == "verified"
    assert by_key["cp:art:566"]["status"] == "unverified"

