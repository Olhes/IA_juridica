"""Métricas del harness: regla n/a, macro/micro, factualidad, citas, abstención y calibración."""

import pytest

from evaluation.harness.answers import Answer, answer_from_payload
from evaluation.harness.metrics import abstention, citations, factuality, faithfulness
from evaluation.harness.metrics.calibration import calibration
from evaluation.harness.metrics.common import Score, aggregate, merge_samples

from .conftest import ABSTENTION_TEXT, oracle_answer

pytestmark = pytest.mark.harness


def test_na_is_never_a_silent_zero_in_macro_or_micro():
    result = aggregate([Score.ratio(1, 2), Score.na("sin citas"), Score.ratio(3, 4)])
    assert result["macro"] == {"value": pytest.approx(0.625), "n": 2}
    assert result["micro"]["value"] == pytest.approx(4 / 6)
    assert result["n"] == 2 and result["n_na"] == 1


def test_macro_and_micro_differ_when_cases_have_different_sizes():
    result = aggregate([Score.ratio(1, 1), Score.ratio(1, 4)])
    assert result["macro"]["value"] == pytest.approx(0.625)
    assert result["micro"]["value"] == pytest.approx(0.4)


def test_all_na_reports_reason_instead_of_a_number():
    result = aggregate([Score.na("la respuesta no cita normas"), Score.na("el caso no define citas aceptables")])
    assert result["macro"]["value"] is None and result["micro"]["value"] is None
    assert "no cita normas" in result["macro"]["na_reason"] and result["n"] == 0
    assert aggregate([])["macro"]["value"] is None


def test_zero_denominator_is_na_and_samples_are_merged():
    assert not Score.ratio(0, 0).applicable
    merged = merge_samples([Score.ratio(1, 2), Score.na("x"), Score.ratio(2, 2)])
    assert merged.value == pytest.approx(0.75) and merged.den == 4
    assert not merge_samples([Score.na("x"), Score.na("y")]).applicable


def test_fact_recall_counts_covered_facts_and_is_na_when_abstention_is_required(cases):
    case = cases["visitas-requisitos-conciliacion"]
    full = factuality.fact_recall(case, "Necesitas la copia del DNI, el acta de nacimiento del hijo y el acta de matrimonio.")
    assert full.value == 1.0
    partial = factuality.fact_recall(case, "Solo necesitas tu DNI.")
    assert partial.value == pytest.approx(1 / 3) and partial.den == 3
    assert not factuality.fact_recall(cases["fuera-cts-renuncia"], "lo que sea").applicable


def test_legal_factuality_zeroes_out_when_a_forbidden_claim_is_made(cases):
    case = cases["visitas-no-pago-pension"]
    good = "No pagar la pensión no elimina el derecho a las visitas, y condicionarlas no preserva el interés superior."
    bad = good + " Aun así, si no pagas la pensión pierdes el derecho de visitas."
    assert factuality.legal_factuality(case, good).value == 1.0
    assert factuality.forbidden_hits(case, bad) == ["pierde-visitas"]
    assert factuality.legal_factuality(case, bad).value == 0.0
    assert factuality.factual_pass(case, bad) is False and factuality.factual_pass(case, good) is True


def test_negated_forbidden_claim_is_not_flagged(cases):
    case = cases["visitas-no-pago-pension"]
    assert factuality.forbidden_hits(case, "Si no pagas la pensión, no pierdes el derecho de visitas.") == []


def test_forbidden_claim_is_na_when_the_case_defines_none(cases):
    assert not factuality.forbidden_claim(cases["pension-asignacion-anticipada"], "x").applicable
    assert factuality.forbidden_claim(cases["pension-tope-embargo"], "Se puede embargar el 100% de tus ingresos.").value == 1.0


def test_oracle_answers_are_fully_factual_for_every_answerable_case(gold):
    for case in gold:
        if case.must_abstain:
            continue
        answer = oracle_answer(case)
        assert factuality.fact_recall(case, answer.text).value == 1.0, case.id
        assert factuality.forbidden_hits(case, answer.text) == [], case.id


def test_citation_precision_uses_the_corpus_and_the_acceptable_list(corpus, cases):
    index = citations.CorpusIndex(corpus)
    text = "Según el artículo 475 CC y la Ley 30364; también la Ley 99999 y la Casación 9999-2099."
    in_corpus = citations.citation_in_corpus(text, index)
    assert (in_corpus.num, in_corpus.den) == (2, 4)
    case = cases["pension-prelacion-obligados"]
    acceptable = citations.citation_acceptable(case, "Rige el artículo 475 del Código Civil y el artículo 999 del Código Civil.")
    assert (acceptable.num, acceptable.den) == (1, 2)


def test_citation_metrics_are_na_without_citations_or_acceptable_list(corpus, cases):
    index = citations.CorpusIndex(corpus)
    assert not citations.citation_in_corpus("Sin ninguna norma citada.", index).applicable
    assert not citations.citation_acceptable(cases["pension-contenido-alimentos"], "Ley 30364").applicable
    assert not citations.citation_acceptable(cases["pension-prelacion-obligados"], "Sin normas.").applicable


def test_citation_index_finds_citations_in_spaced_ocr_documents(corpus):
    index = citations.CorpusIndex(corpus)
    text = "La Casación 1293-2021 y el artículo 8 definen la violencia psicológica."
    assert citations.citation_in_corpus(text, index).value == 1.0


def test_citation_grounded_reads_runtime_statuses():
    none = Answer(text="x")
    assert not citations.citation_grounded(none).applicable
    assert not citations.citation_grounded(Answer(text="x", citations=[])).applicable
    mixed = Answer(text="x", citations=[{"status": "verified"}, {"status": "unverified"}])
    assert citations.citation_grounded(mixed).value == 0.5


def test_abstention_metrics_are_complementary_and_semantic_markers_count(cases):
    must, may = cases["fuera-cts-renuncia"], cases["pension-contenido-alimentos"]
    refusal = Answer(text=ABSTENTION_TEXT, evidence_status="insufficient_evidence")
    semantic = Answer(text="El corpus no indica el plazo exacto de resolución.", evidence_status="retrieved")
    answered = Answer(text="La pensión cubre vivienda y salud.", evidence_status="retrieved")
    assert abstention.abstention_recall(must, refusal).value == 1.0
    assert abstention.abstention_recall(must, semantic).value == 1.0
    assert abstention.abstention_recall(must, answered).value == 0.0
    assert not abstention.abstention_recall(may, refusal).applicable
    assert abstention.unnecessary_abstention(may, refusal).value == 1.0
    assert abstention.unnecessary_abstention(may, answered).value == 0.0
    assert not abstention.unnecessary_abstention(must, refusal).applicable
    assert abstention.formal_abstention(must, semantic).value == 0.0


def test_calibration_perfect_overconfident_and_empty():
    perfect = calibration([(1.0, True), (0.0, False)] * 3)
    assert perfect["ece"] == pytest.approx(0.0) and perfect["brier"] == pytest.approx(0.0) and perfect["n"] == 6
    over = calibration([(0.95, False)] * 4)
    assert over["ece"] == pytest.approx(0.95) and over["brier"] > 0.9
    empty = calibration([(None, True)])
    assert empty["n"] == 0 and empty["ece"] is None and "sin casos" in empty["na_reason"]


def test_faithfulness_is_a_diagnostic_with_na_when_missing():
    assert not faithfulness.faithfulness_overlap(Answer(text="x")).applicable
    assert faithfulness.faithfulness_overlap(Answer(text="x", cross_check_overlap=0.8)).value == 0.8
    assert not faithfulness.faithfulness_judge(None).applicable
    assert faithfulness.faithfulness_judge(0.5).value == 0.5


def test_answer_from_payload_reads_the_pipeline_contract():
    payload = {
        "response": {"respuesta_espanol": "Texto final"},
        "sources": ["a.md"],
        "validation": {"confidence_score": 0.7, "is_reliable": True, "cross_check": {"overlap_score": 0.4}},
        "metadata": {"evidence_status": "retrieved", "timings": {"total_ms": 3}, "citations": [{"status": "verified"}]},
    }
    answer = answer_from_payload(payload)
    assert (answer.text, answer.confidence_score, answer.cross_check_overlap) == ("Texto final", 0.7, 0.4)
    assert answer.timings == {"total_ms": 3} and answer.citations == [{"status": "verified"}]
    assert not answer.abstained
    abstained = answer_from_payload({"response": {"respuesta_espanol": ABSTENTION_TEXT}, "metadata": {"evidence_status": "insufficient_evidence"}})
    assert abstained.abstained_formal and abstained.abstained_semantic
