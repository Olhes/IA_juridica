"""Esquema estricto, procedencia y verificación del gold contra el corpus."""

import json
from collections import Counter

import pytest

from evaluation.harness.corpus import Corpus, doc_id_for, segment_text
from evaluation.harness.gold import (
    LEGAL_QA_PATH,
    GoldCase,
    GoldValidationError,
    gold_hash,
    load_gold,
    verify_case,
)
from evaluation.harness.matching import anchors_satisfied, pattern_matches
from evaluation.harness.seed_legal_qa import build_seed

pytestmark = pytest.mark.harness


def raw_case(cases, case_id):
    return json.loads(json.dumps(cases[case_id].model_dump(mode="json")))


def test_segmenter_is_deterministic_and_drops_page_noise():
    text = "## Título del documento\n\n<!-- image -->\n\nhttps://ejemplo.pe/x\n\n3/17\n\nUn párrafo con contenido jurídico suficiente.\n\nNotebookLM"
    first = segment_text("doc", text)
    assert first == segment_text("doc", text.replace("\n", "\r\n"))
    assert [s.id for s in first] == ["doc#1", "doc#2"]
    assert "ejemplo.pe" not in " ".join(s.text for s in first)


def test_document_ids_are_unique_and_stable(corpus):
    assert doc_id_for("Pensión de alimentos_ ¿qué abarca? [2025].md") == "pension-de-alimentos-que-abarca-2025"
    assert len(corpus.documents) == 18 and len(corpus.segments) > 1000
    assert corpus.revision() == Corpus.load().revision()


def test_seed_cases_are_candidates_without_reviewers(gold):
    assert len(gold) >= 30
    assert {c.status for c in gold} == {"candidate"}
    assert all(c.reviewers == [] for c in gold)
    assert all(c.version == 1 for c in gold)


def test_seed_covers_all_strata_splits_and_topics(gold):
    assert {c.stratum for c in gold} == {"positivo", "limite", "negativo"}
    assert {c.split for c in gold} == {"dev", "holdout"}
    assert {c.topic for c in gold} >= {
        "pension_alimentos", "regimen_visitas", "tenencia", "violencia_familiar",
        "omision_asistencia_familiar", "fuera_de_corpus",
    }
    counts = Counter((c.stratum, c.split) for c in gold)
    assert all(counts[(s, p)] for s in ("positivo", "limite", "negativo") for p in ("dev", "holdout"))


def test_every_fact_and_contradiction_quotes_the_corpus(gold, corpus):
    assert [p for c in gold for p in verify_case(c, corpus)] == []
    facts = [f for c in gold for f in c.required_facts]
    assert len(facts) >= 55
    assert all(f.source.segment_id in corpus.segments for f in facts)


def test_checked_in_jsonl_matches_the_seed_definition(corpus):
    """El JSONL se regenera con ``python -m evaluation.harness.seed_legal_qa``; no se edita a mano."""
    built = sorted(build_seed(corpus), key=lambda c: c.id)
    written = [GoldCase.model_validate_json(line) for line in LEGAL_QA_PATH.read_text(encoding="utf-8").splitlines()]
    assert built == written


def test_each_fact_text_satisfies_its_own_anchors(gold):
    """Un hecho redactado con sus propias palabras debe contar como cubierto."""
    misses = [(c.id, f.id) for c in gold for f in c.required_facts if not anchors_satisfied(f.text, f.anchors)]
    assert misses == []


def test_forbidden_patterns_detect_their_example_but_not_the_facts(gold):
    for case in gold:
        for claim in case.forbidden_claims:
            assert any(pattern_matches(claim.example, p) for p in claim.patterns), (case.id, claim.id)
        facts_text = " ".join(f.text for f in case.required_facts)
        for claim in case.forbidden_claims:
            assert not any(pattern_matches(facts_text, p) for p in claim.patterns), (case.id, claim.id)


def test_negative_cases_are_out_of_corpus_and_require_abstention(gold):
    negatives = [c for c in gold if c.stratum == "negativo"]
    assert len(negatives) >= 5
    for case in negatives:
        assert case.must_abstain and not case.reference_segments and case.topic == "fuera_de_corpus"
        assert case.absent_terms


def test_loader_filters_splits_and_adjudicated(corpus):
    assert {c.split for c in load_gold(corpus=corpus, splits=["holdout"])} == {"holdout"}
    assert load_gold(corpus=corpus, only_adjudicated=True) == []


def test_gold_hash_ignores_line_endings(tmp_path):
    original = LEGAL_QA_PATH.read_bytes().replace(b"\r\n", b"\n")
    crlf = tmp_path / "crlf.jsonl"
    crlf.write_bytes(original.replace(b"\n", b"\r\n"))
    assert gold_hash(crlf) == gold_hash(LEGAL_QA_PATH)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(extra="campo no permitido"),
        lambda c: c.update(reviewers=[{"id": "a", "role": "abogado", "blind": True, "verdict": "approve", "reviewed_at": "2026-10-22"}]),
        lambda c: c.update(status="adjudicated"),
        lambda c: c.update(status="adjudicated", reviewers=[
            {"id": "a", "role": "abogado", "blind": True, "verdict": "approve", "reviewed_at": "2026-10-22"},
            {"id": "a", "role": "abogado", "blind": True, "verdict": "approve", "reviewed_at": "2026-10-22"}]),
        lambda c: c.update(must_abstain=True),
        lambda c: c.update(required_facts=[]),
        lambda c: c.update(reference_segments=[]),
        lambda c: c.update(stratum="inventado"),
        lambda c: c.update(split="validacion"),
        lambda c: c.update(id="Mayúsculas y espacios"),
    ],
)
def test_schema_rejects_inconsistent_cases(cases, mutate):
    data = raw_case(cases, "pension-contenido-alimentos")
    mutate(data)
    with pytest.raises(ValueError):
        GoldCase.model_validate(data)


def test_negative_with_segments_or_without_absent_terms_is_rejected(cases):
    data = raw_case(cases, "fuera-cts-renuncia")
    with pytest.raises(ValueError):
        GoldCase.model_validate({**data, "absent_terms": []})
    with pytest.raises(ValueError):
        GoldCase.model_validate({**data, "topic": "pension_alimentos"})


def test_two_blind_approvals_make_a_case_adjudicated(cases):
    data = raw_case(cases, "pension-contenido-alimentos")
    reviewers = [
        {"id": r, "role": "abogado", "blind": True, "verdict": "approve", "reviewed_at": "2026-10-22"} for r in ("ab-1", "ab-2")
    ]
    assert GoldCase.model_validate({**data, "status": "adjudicated", "reviewers": reviewers}).status == "adjudicated"


def test_verification_detects_invented_quote_changed_text_and_corpus_leaks(cases, corpus):
    data = raw_case(cases, "pension-contenido-alimentos")
    data["required_facts"][0]["source"]["quote"] = "La pensión cubre el transporte aéreo internacional"
    assert any("la cita no aparece" in p for p in verify_case(GoldCase.model_validate(data), corpus))

    data = raw_case(cases, "pension-contenido-alimentos")
    data["reference_segments"][0]["sha"] = "0" * 12
    assert any("cambió" in p for p in verify_case(GoldCase.model_validate(data), corpus))

    data = raw_case(cases, "pension-monto-sin-cifra")
    data["forbidden_claims"][0]["patterns"] = ["re:criterios"]
    assert any("aparece en el corpus" in p for p in verify_case(GoldCase.model_validate(data), corpus))

    data = raw_case(cases, "fuera-pension-argentina")
    data["absent_terms"] = ["alimentos"]
    assert any("sí aparece en el corpus" in p for p in verify_case(GoldCase.model_validate(data), corpus))

    data = raw_case(cases, "pension-tope-embargo")
    data["acceptable_citations"] = ["cc:art:9999"]
    assert any("cita aceptable" in p for p in verify_case(GoldCase.model_validate(data), corpus))


def test_loader_reports_every_problem_with_its_line(tmp_path, cases):
    good = json.dumps(cases["pension-contenido-alimentos"].model_dump(mode="json"), ensure_ascii=False)
    path = tmp_path / "broken.jsonl"
    path.write_text(good + "\n{ no es json\n" + good + "\n", encoding="utf-8")
    with pytest.raises(GoldValidationError) as error:
        load_gold(path, verify=False)
    assert any("línea 2" in p for p in error.value.problems)
    assert any("repetidos" in p for p in error.value.problems)
