"""Evaluación de recuperación: regla de solapamiento, métricas de evidencia y sistemas por etapa."""

import json
import math
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from evaluation.harness import retrieval_eval, retrieval_gold
from evaluation.harness.corpus import DEFAULT_CORPUS_DIR
from evaluation.harness.metrics import retrieval as m
from evaluation.harness.overlap import SegmentMatcher, shingles, unmapped_id
from evaluation.harness.retrieval_eval import Retrieved, evaluate_retrieval, index_audit, retrieve_bundle
from evaluation.harness.runner import offline_engine
from modules.rag.services import lightrag_engine

pytestmark = pytest.mark.harness


@pytest.fixture(scope="session")
def matcher(corpus):
    return SegmentMatcher(corpus)


@pytest.fixture(scope="session")
def retrieval_cases(gold, corpus):
    return retrieval_gold.derive(gold, corpus)


def segment_text(corpus, segment_id):
    return corpus.segments[segment_id].text


def test_overlap_rule_maps_containing_inside_and_unrelated_chunks(corpus, matcher):
    sid = next(s.id for s in corpus.segments.values() if "tope legal del 60%" in s.text)
    text = segment_text(corpus, sid)
    assert sid in [x.segment_id for x in matcher.matches("Texto previo irrelevante. " + text + " Texto posterior.")]
    assert sid in matcher.ids(text[: int(len(text) * 0.8)])  # un fragmento que es casi por completo parte del segmento
    other = matcher.ids("Una frase sobre astronomía y telescopios que no figura en ningún documento jurídico.")
    assert len(other) == 1 and other[0].startswith("unmapped:")
    assert other == [unmapped_id("Una frase sobre astronomía y telescopios que no figura en ningún documento jurídico.")]


def test_overlap_rule_is_insensitive_to_spacing_and_accents(corpus, matcher):
    sid = next(s.id for s in corpus.segments.values() if "tope legal del 60%" in s.text)
    text = segment_text(corpus, sid)
    assert sid in matcher.ids(text.upper().replace(" ", "  "))
    assert shingles("ab") == set()


def test_a_long_chunk_maps_to_every_segment_it_contains(corpus, matcher):
    segments = [s for s in corpus.documents["visitas"].segments][:4]
    ids = matcher.ids(" ".join(s.text for s in segments))
    assert {s.id for s in segments} <= set(ids)


def test_recall_precision_mrr_ndcg_follow_the_sat_definitions():
    ranked = [["a"], ["x"], ["b", "y"], ["z"]]
    relevant = ["a", "b", "c"]
    assert m.evidence_recall(ranked, relevant, 3).value == pytest.approx(2 / 3)
    assert m.evidence_precision(ranked, relevant, 3).value == pytest.approx(2 / 4)  # IDs: a, x, b, y
    assert m.chunk_precision(ranked, relevant, 3).value == pytest.approx(2 / 3)
    assert m.mrr(ranked, relevant).value == 1.0
    assert m.mrr([["x"], ["a"]], relevant).value == 0.5
    assert m.mrr([["x"]], relevant).value == 0.0
    perfect = m.ndcg([["a"], ["b"], ["c"]], relevant, 3).value
    assert perfect == pytest.approx(1.0)
    assert 0 < m.ndcg(ranked, relevant, 4).value < 1


def test_ndcg_uses_unique_segments_for_both_ranking_and_ideal():
    assert m.ndcg([["a"], ["a"]], ["a"], 5).value == pytest.approx(1.0)
    assert m.ndcg([["a"], ["a"], ["b"]], ["a", "b"], 3).value == pytest.approx(1.0)
    assert m.ndcg([["a", "b"]], ["a", "b"], 3).value == pytest.approx(1.0)
    assert m.ndcg([["a", "b"], ["a"], ["b"]], ["a", "b"], 3).value == pytest.approx(1.0)
    assert m.ndcg([["x"], ["a"], ["a"]], ["a", "a"], 3).value == pytest.approx(1 / math.log2(3))
    assert m.ndcg([["a"], ["b"]], ["a", "b"], 1).value == 1
    assert m.ndcg([["x"]], ["a"], 5).value == 0
    assert m.ndcg([], ["a"], 5).value == 0


def test_ndcg_ideal_includes_missing_evidence_and_respects_segment_cutoff():
    assert m.ndcg([["a"]], ["a", "b"], 5).value == pytest.approx(1 / (1 + 1 / math.log2(3)))
    assert m.ndcg([["x", "y"], ["a"]], ["a"], 2).value == 0
    assert m.ndcg([["x", "y"], ["a"]], ["a"], 3).value == pytest.approx(0.5)


@pytest.mark.parametrize("ranked", [[["a", "x"]], [["x", "a"]], [["a", "a", "x"], ["a"]]])
def test_ndcg_averages_ties_without_gold_based_ordering(ranked):
    assert m.ndcg(ranked, ["a"], 1).value == pytest.approx(0.5)
    assert m.ndcg(ranked, ["a"], 2).value == pytest.approx((1 + 1 / math.log2(3)) / 2)


@pytest.mark.parametrize("k", [0, -1])
def test_ndcg_rejects_nonpositive_cutoff(k):
    with pytest.raises(ValueError, match="k debe ser positivo"):
        m.ndcg([["a"]], ["a"], k)


def test_every_retrieval_metric_is_na_without_a_denominator():
    for score in (
        m.evidence_recall([["a"]], [], 3), m.evidence_precision([["a"]], [], 3), m.mrr([["a"]], []),
        m.ndcg([["a"]], [], 3), m.chunk_precision([["a"]], [], 3), m.jurisprudence_hit([["a"]], [], 3),
        m.empty_result(0, []), m.empty_when_unanswerable(0, False), m.fallback_used(None),
        m.evidence_precision([], ["a"], 3), m.chunk_precision([], ["a"], 3),
    ):
        assert not score.applicable, score


def test_empty_result_and_jurisprudence_flags():
    assert m.empty_result(0, ["a"]).value == 1.0 and m.empty_result(2, ["a"]).value == 0.0
    assert m.empty_when_unanswerable(0, True).value == 1.0 and m.empty_when_unanswerable(3, True).value == 0.0
    assert m.jurisprudence_hit([["x"], ["j"]], ["j"], 2).value == 1.0
    assert m.jurisprudence_hit([["x"], ["j"]], ["j"], 1).value == 0.0
    assert m.fallback_used("fallback_keyword_rerank").value == 1.0 and m.fallback_used("cohere_rerank").value == 0.0


def test_threshold_loss_counts_relevant_evidence_scored_under_the_minimum():
    ranked = [["a"], ["x"], ["b"]]
    scores = [0.9, 0.5, 0.05]
    assert m.threshold_loss(ranked, scores, ["a", "b"], 3, 0.1).value == 0.5
    assert not m.threshold_loss([["x"]], [0.9], ["a"], 3, 0.1).applicable


def test_retrieval_gold_is_derived_from_legal_qa_and_matches_the_checked_in_file(gold, corpus, retrieval_cases):
    # Solo español: la consulta en quechua se traduce antes de recuperar (recupera como su gemelo).
    assert [c.id for c in retrieval_cases] == sorted(c.id for c in gold if c.language == "spanish")
    assert retrieval_gold.load() == retrieval_cases
    by_id = {c.id: c for c in retrieval_cases}
    assert by_id["fuera-cts-renuncia"].relevant == [] and by_id["fuera-cts-renuncia"].must_abstain
    assert by_id["pension-tope-embargo"].relevant and set(by_id["pension-tope-embargo"].relevant).isdisjoint(by_id["pension-tope-embargo"].supporting)
    assert {c.status for c in retrieval_cases} == {"candidate"}


def test_jurisprudence_is_detected_by_casacion_citations_and_casacion_documents(retrieval_cases):
    jurisprudence = {c.id for c in retrieval_cases if c.jurisprudence}
    assert {"visitas-no-pago-pension", "visitas-articulo-88", "violencia-psicologica-definicion", "violencia-valor-informe-cem"} <= jurisprudence
    assert "pension-contenido-alimentos" not in jurisprudence


def oracle_bundle(case, corpus, extra=None):
    chunks = [{"content": corpus.segments[sid].text, "score": 0.9} for sid in case.relevant]
    return {"lexical": Retrieved(chunks, method="bm25"), "lightrag_naive": Retrieved(unavailable="LightRAG no está inicializado")}


def test_oracle_retrieval_is_perfect_and_unavailable_systems_are_na_with_reason(retrieval_cases, corpus, matcher):
    bundles = {c.id: oracle_bundle(c, corpus) for c in retrieval_cases}
    report = evaluate_retrieval(retrieval_cases, bundles, matcher, systems=("lexical", "lightrag_naive"))
    assert report["ndcg_definition"] == "binary_unique_segments_tie_averaged_v1"
    lexical = report["main"]["lexical"]
    assert lexical["evidence_recall@5"]["macro"]["value"] == pytest.approx(1.0)
    assert lexical["mrr"]["macro"]["value"] == 1.0 and lexical["chunk_precision@5"]["macro"]["value"] == 1.0
    assert lexical["empty_when_unanswerable"]["macro"]["value"] == 1.0
    graph = report["main"]["lightrag_naive"]["evidence_recall@5"]
    assert graph["macro"]["value"] is None and "no disponible" in graph["macro"]["na_reason"]
    assert report["by_stratum"]["positivo"]["lexical"]["evidence_recall@5"]["n"] > 0
    assert report["by_stratum"]["negativo"]["lexical"]["evidence_recall@5"]["n"] == 0


def test_irrelevant_results_score_zero_recall_but_are_not_empty(retrieval_cases, corpus, matcher):
    junk = {"lexical": Retrieved([{"content": "Texto ajeno sobre astronomía y telescopios gigantes.", "score": 1.0}], method="bm25")}
    report = evaluate_retrieval(retrieval_cases, {c.id: junk for c in retrieval_cases}, matcher, systems=("lexical",))
    metrics = report["main"]["lexical"]
    assert metrics["evidence_recall@5"]["macro"]["value"] == 0.0 and metrics["mrr"]["macro"]["value"] == 0.0
    assert metrics["empty_when_answerable"]["macro"]["value"] == 0.0
    assert metrics["empty_when_unanswerable"]["macro"]["value"] == 0.0


def test_threshold_loss_is_measured_from_the_rerank_scores(retrieval_cases, corpus, matcher):
    case = next(c for c in retrieval_cases if c.id == "pension-tope-embargo")
    relevant_text = corpus.segments[case.relevant[0]].text
    reranked = Retrieved(
        [],  # el umbral lo descartó todo
        method="no_match",
        extra={"threshold": 0.1, "reranker": "cohere", "rerank": [[1, 0.04], [0, 0.03]], "candidates": ["Otro texto cualquiera sin relación.", relevant_text], "top_k": 5},
    )
    report = evaluate_retrieval([case], {case.id: {"current_reranked": reranked}}, matcher, systems=("current_reranked",))
    assert report["main"]["current_reranked"]["threshold_loss"]["macro"]["value"] == 1.0
    assert report["main"]["current_reranked"]["empty_when_answerable"]["macro"]["value"] == 1.0


def test_retrieved_round_trips_through_json():
    original = Retrieved([{"content": "x", "score": 0.5}], method="bm25", extra={"top_k": 5})
    assert Retrieved.from_json(json.loads(json.dumps(original.to_json()))) == original


def test_index_audit_reports_segments_no_indexed_chunk_can_reach(corpus, matcher):
    covered = segment_text(corpus, "visitas#2")
    audit = index_audit(corpus, [covered, "Chunk obsoleto que ya no está en el corpus."], matcher, {"c1": ["visitas#2", "tenencia#2"]})
    assert audit["indexed_chunks"] == 2 and audit["chunks_without_segment"] == 1
    assert audit["gold_segments_covered"] == 1 and audit["gold_segments_missing"] == ["tenencia#2"]
    assert 0 < audit["segment_coverage"] < 1


def test_corpus_quality_flags_spaced_ocr_documents_and_gold_dependence(corpus, retrieval_cases):
    quality = retrieval_eval.corpus_quality(corpus, {c.id: c.relevant for c in retrieval_cases})
    assert len(quality["spaced_documents"]) == 4
    assert all(d["spaced_ocr_ratio"] > 0.5 for d in quality["documents"] if d["doc_id"] in quality["spaced_documents"])


async def test_offline_engine_runs_lexical_mix_and_fallback_rerank_without_network(corpus, retrieval_cases):
    engine = offline_engine(DEFAULT_CORPUS_DIR)
    case = next(c for c in retrieval_cases if c.id == "pension-tope-embargo")
    bundle = await retrieve_bundle(engine, case.query, budget=50, top_k=5)
    assert bundle["lightrag_mix"].unavailable and bundle["reranked_no_threshold"].unavailable
    assert bundle["lexical"].method == "bm25" and bundle["lexical"].chunks
    assert bundle["current_reranked"].method.startswith("fallback")
    assert bundle["current_reranked"].extra["reranker"] == "fallback_keyword"
    assert len(bundle["current_reranked"].chunks) <= 5
    again = await retrieve_bundle(engine, case.query, budget=50, top_k=5)
    assert [c["content"] for c in again["lexical"].chunks] == [c["content"] for c in bundle["lexical"].chunks]


async def test_trace_exposes_every_rerank_score_without_changing_the_selection(rag, monkeypatch):
    monkeypatch.setattr(lightrag_engine, "COHERE_AVAILABLE", True)
    entries = [SimpleNamespace(index=1, relevance_score=0.9), SimpleNamespace(index=0, relevance_score=0.05)]
    rerank = AsyncMock(return_value=SimpleNamespace(results=entries))
    rag.cohere_client = SimpleNamespace(rerank=rerank)
    plain = await rag.query_with_rerank("tasa licencia municipal", top_k=2)
    assert rerank.await_args.kwargs["top_n"] == 2
    trace = {}
    traced = await rag.query_with_rerank("tasa licencia municipal", top_k=2, trace=trace)
    assert rerank.await_args.kwargs["top_n"] == 2  # con 2 candidatos pide todos
    assert [d["id"] for d in traced["documents"]] == [d["id"] for d in plain["documents"]] and len(traced["documents"]) == 1
    assert trace["rerank"] == [(1, 0.9), (0, 0.05)] and trace["reranker"] == "cohere" and trace["threshold"] == 0.1
    assert len(trace["candidates"]) == 2


async def test_trace_without_reranker_marks_the_fallback(rag):
    trace = {}
    result = await rag.query_with_rerank("tasa licencia municipal", top_k=1, trace=trace)
    assert result["method"] == "fallback_keyword_rerank" and trace["reranker"] == "fallback_keyword" and trace["rerank"] is None
