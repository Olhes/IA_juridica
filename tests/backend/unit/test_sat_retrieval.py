"""Recuperación sobre textos inventados; no certifica legislación peruana."""

from copy import deepcopy
from datetime import datetime
from hashlib import sha256

import pytest
from pydantic import ValidationError

from tests.backend.fixtures.sat_store import FixtureSATStore as SATGraphStore
from retrieval.sat import (
    SATRetriever,
    SearchPlan,
    RankStages,
    bm25,
    ranked,
    rrf,
)
from tests.backend.unit.test_sat_graph import RESOURCE, amendment, review, staged, unit
from utils.vectors import cosine, cosine_scores


@pytest.fixture
def corpus(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    old = staged(tmp_path, store, "Protección ficticia anterior", "old")
    old_id = store.review(review(old, [unit("Protección ficticia anterior")]))[
        "version_ids"
    ][0]
    new = staged(tmp_path, store, "Protección ficticia nueva", "new")
    new_id = store.review(amendment(new, "Protección ficticia nueva", old_id))[
        "version_ids"
    ][0]
    return store, old_id, new_id


def plan(**overrides):
    return SearchPlan(query="protección", as_of="2025-01-01", **overrides)


@pytest.mark.parametrize(
    "values",
    [
        {"query": " "},
        {"as_of": "2025"},
        {"as_of": 1735689600},
        {"as_of": datetime(2025, 1, 1)},
        {"component": "art-1"},
        {"scope": "BR"},
        {"unknown": True},
        {"top_k": 10, "candidates": 5},
    ],
)
def test_plan_fails_closed_on_ambiguous_constraints(values):
    with pytest.raises(ValidationError):
        SearchPlan.model_validate(
            {"query": "protección", "as_of": "2025-01-01", **values}
        )


@pytest.mark.parametrize("when,which", [("2024-12-31", 1), ("2025-01-01", 2)])
def test_temporal_gate_precedes_every_strategy(corpus, when, which):
    store, old, new = corpus
    engine = SATRetriever(store.export())
    for strategy in ("bm25", "metadata", "hybrid", "ppr", "tree"):
        result = engine.search(
            SearchPlan(query="protección", as_of=when, strategy=strategy)
        )
        assert [hit["version_id"] for hit in result["hits"]] == [
            old if which == 1 else new
        ]
        assert result["api"]["requests"] == 0
        assert result["dense_status"] == "not_run"


def test_no_soft_relaxation_of_resource_component_or_coverage(corpus):
    store, *_ = corpus
    engine = SATRetriever(store.export())
    for overrides in (
        {"resource_ids": ["pe:absent"]},
        {"resource_ids": [RESOURCE], "component": "absent"},
        {"as_of": "2026-10-08"},
    ):
        values = {"query": "protección", "as_of": "2025-01-01", **overrides}
        result = engine.search(SearchPlan(**values))
        assert result["state"] == "abstain" and not result["hits"]


def test_candidates_and_conflicting_versions_never_enter_retrieval(corpus):
    store, _, new_id = corpus
    snapshot = store.export()
    duplicate = deepcopy(next(n for n in snapshot["nodes"] if n["id"] == new_id))
    duplicate["id"] = "conflicting-version"
    snapshot["nodes"].append(duplicate)
    assert SATRetriever(snapshot).search(plan())["state"] == "abstain"


def test_snapshot_and_revision_are_isolated_from_external_mutations(corpus):
    store, _, new_id = corpus
    snapshot = store.export()
    engine = SATRetriever(snapshot)
    before = engine.search(plan())
    next(n for n in snapshot["nodes"] if n["id"] == new_id)[
        "checked_through"
    ] = "1900-01-01"
    snapshot["edges"].clear()
    assert engine.search(plan()) == before


def test_subchunks_roundtrip_unicode_and_global_offsets(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    prefix, text = "Prólogo\n", "Niñez y protección. " * 20
    evidence = staged(tmp_path, store, prefix + text)
    store.review(
        review(evidence, [unit(text, start=len(prefix), end=len(prefix + text))])
    )
    chunks = SATRetriever(store.export()).chunks(plan(chunk_chars=100))
    assert "".join(c["content"] for c in chunks) == text
    assert len({c["id"] for c in chunks}) == len(chunks)
    for chunk in chunks:
        assert (prefix + text)[chunk["start"] : chunk["end"]] == chunk["content"]
        assert sha256(chunk["content"].encode()).hexdigest() == chunk["text_sha256"]
        assert chunk["resource_label"].startswith("Ley 30364")


def test_context_budget_does_not_truncate_canonical_text(corpus):
    store, *_ = corpus
    engine = SATRetriever(store.export())
    result = engine.search(plan(context_bytes=100))
    assert result["context_bytes"] <= 100
    assert all(
        hit["end"] - hit["start"] == len(hit["content"]) for hit in result["hits"]
    )


def test_history_reconstructs_causal_edges(corpus):
    store, old, new = corpus
    result = SATRetriever(store.export()).history(RESOURCE, "art-1")
    assert [v["id"] for v in result["versions"]] == [old, new]
    assert result["actions"][0]["kind"] == "amend"
    assert {e["type"] for e in result["causal_edges"]} == {
        "produces",
        "terminates",
        "source",
    }
    assert (
        SATRetriever(store.export()).history(RESOURCE, "absent")["state"] == "abstain"
    )


def test_ppr_expands_only_eligible_memberships(tmp_path):
    store = SATGraphStore(tmp_path / "sat.db")
    text = "protección ficticia"
    evidence = staged(tmp_path, store, text)
    result = store.review(
        review(evidence, [unit(text, "root"), unit(text, parent_component="root")])
    )
    snapshot = store.export()
    parent, child = result["version_ids"]
    snapshot["edges"].append(
        {"source": parent, "target": child, "type": "contains_version"}
    )
    engine = SATRetriever(snapshot)
    chunks = engine.chunks(plan())
    scores = engine._ppr(chunks, [chunks[0]["id"]])
    assert len(scores) == 2 and all(value > 0 for value in scores.values())
    assert sum(scores.values()) == pytest.approx(1)
    # Two undirected nodes, one seed: the analytical solution needs >50 iterations
    # to reach SAT's 1e-10 tolerance from the seed-only distribution.
    assert scores[chunks[0]["id"]] == pytest.approx(1 / 1.85, abs=1e-10, rel=0)
    assert scores[chunks[1]["id"]] == pytest.approx(0.85 / 1.85, abs=1e-10, rel=0)


def test_rank_math_is_deterministic_and_rejects_bad_vectors():
    assert ranked(bm25("proteccion", {"a": "Protección", "b": "otro"})) == ["a"]
    assert rrf([["a", "a"], ["b", "a"]])["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert cosine([1, 0], [1, 0]) == 1
    for vector in ([], [1], [float("nan"), 0]):
        with pytest.raises(ValueError):
            cosine([1, 0], vector)


def test_cosine_scores_preserves_row_order_and_handles_zero_vectors():
    rows = [[3, 4], [0, 0], [-3, -4], [4, -3], [3, 4]]
    assert cosine_scores(rows, [3, 4]) == pytest.approx([1.0, 0.0, -1.0, 0.0, 1.0])
    assert cosine_scores(rows, [0, 0]) == [0.0] * len(rows)
    assert cosine_scores([], [3, 4]) == []
    with pytest.raises(ValueError, match="Vector no finito"):
        cosine_scores([[1, 2], [float("inf"), 3]], [1, 2])
    with pytest.raises(ValueError):
        cosine_scores([[1, 2], [3]], [1, 2])


def test_weighted_rrf_preserves_default_and_excludes_zero_weight_candidates():
    rankings = [["a", "b"], ["b", "c"], ["c", "d"]]
    assert rrf(rankings) == rrf(rankings, weights=[1.0, 1.0, 1.0])
    weighted = rrf(rankings, weights=[1.0, 1.0, 0.25])
    assert weighted["c"] == pytest.approx(1 / 62 + 0.25 / 61)
    assert "d" not in rrf(rankings, weights=[1.0, 1.0, 0.0])
    for weights in ([1.0], [1.0, 1.0, -1.0], [1.0, 1.0, float("nan")]):
        with pytest.raises(ValueError):
            rrf(rankings, weights=weights)


@pytest.mark.parametrize(
    "dense,rerank", [(False, False), (True, False), (False, True), (True, True)]
)
@pytest.mark.parametrize("strategy", ["bm25", "metadata", "hybrid", "ppr", "tree"])
def test_rank_stages_are_independent_and_accounted(corpus, dense, rerank, strategy):
    store, _, new = corpus
    calls = []

    class Probe:
        def embed(self, groups, **kwargs):
            calls.append("dense")
            return [[[1, 0] for _ in group] for group in groups], dict(
                requests=1, tokens=3, cache_hits=0
            )

        def rerank(self, query, docs, **kwargs):
            calls.append("rerank")
            return [(i, 1) for i in reversed(range(len(docs)))], dict(
                requests=1, tokens=7, cache_hits=0
            )

    engine = SATRetriever(store.export())
    advanced = strategy in {"hybrid", "ppr", "tree"}
    result = engine.search(
        plan(strategy=strategy),
        provider=Probe(),
        stages=RankStages(dense=dense, rerank=rerank),
    )
    assert calls == (["dense", "dense"] if advanced and dense else []) + (
        ["rerank"] if advanced and rerank else []
    )
    assert result["dense_status"] == ("executed" if advanced and dense else "not_run")
    assert result["rerank_status"] == ("executed" if advanced and rerank else "not_run")
    assert result["api"]["tokens"] == (6 * dense + 7 * rerank if advanced else 0)
    assert result["api"] == {
        key: sum(stage[key] for stage in result["api_stages"].values())
        for key in result["api"]
    }
    assert [hit["version_id"] for hit in result["hits"]] == [new]
    if not dense and not rerank:
        assert result == engine.search(plan(strategy=strategy))
    empty = engine.search(
        plan(strategy=strategy, resource_ids=["pe:absent"]),
        provider=Probe(),
        stages=RankStages(dense=dense, rerank=rerank),
    )
    assert empty["api"]["requests"] == 0 and empty["state"] == "abstain"


@pytest.mark.parametrize(
    "values",
    [
        {"dense": "false"},
        {"rerank": 0},
        {"unknown": True},
        {"ppr_weight": -0.1},
        {"ppr_weight": 2.1},
        {"ppr_weight": float("nan")},
        {"ppr_weight": "0.25"},
    ],
)
def test_rank_stage_contract_rejects_coercion_and_unknown_flags(values):
    with pytest.raises(ValidationError):
        RankStages(**values)
def test_bm25s_matches_legacy_formula_for_many_queries():
    import random
    from collections import Counter
    from math import log

    from retrieval.sat import _BM25Index, terms

    rng = random.Random(12345)
    words = ['niñez', 'alimentos', 'ámbito', 'violencia', '170-A', 'familia', 'salud', 'sección']
    texts = {str(i): ' '.join(rng.choices(words, k=rng.randrange(0, 40))) for i in range(100)}
    index = _BM25Index(texts)
    queries = ['NIÑEZ', 'NO EXISTE', ''] + [
        ' '.join(rng.choices(words + ['no-existe'], k=rng.randrange(0, 8))) for _ in range(100)
    ]
    counts = {identity: Counter(terms(text)) for identity, text in texts.items()}
    lengths = {identity: counter.total() for identity, counter in counts.items()}
    avg = sum(lengths.values()) / len(lengths)
    df = Counter(term for counter in counts.values() for term in counter)
    for query in queries:
        # Referencia de regresión independiente del índice de producción.
        expected = {}
        for identity, counter in counts.items():
            score = sum(
                log(1 + (len(counts) - df[term] + 0.5) / (df[term] + 0.5))
                * counter[term] * 2.2 / (counter[term] + 1.2 * (0.25 + 0.75 * lengths[identity] / avg))
                for term in set(terms(query)) if counter[term]
            )
            if score:
                expected[identity] = score
        assert index.score(query) == pytest.approx(expected, abs=1e-12, rel=1e-12)


def test_bm25_keeps_exact_tie_break_and_ignores_unknown_terms():
    texts = {"z": "NIÑEZ", "a": "niñez", "empty": "..."}
    scores = bm25("niñez", texts)
    assert ranked(scores) == ["a", "z"]
    assert scores["a"] == scores["z"]
    assert bm25("niñez NIÑEZ desconocido", texts) == scores
    assert bm25("...", texts) == {}
    assert bm25("niñez", {"empty": ""}) == {}
    assert bm25("niñez", {}) == {}
