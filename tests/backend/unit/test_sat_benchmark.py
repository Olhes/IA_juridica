"""Métricas reproducibles; ningún juez LLM ni dependencia de un score esperado alto."""

from copy import deepcopy

import pytest

from research.sat_benchmark import paired_interval, run, score_case, validate_dataset
from retrieval.voyage import VoyageError
from tests.backend.fixtures.sat_experiment import dataset


def test_metric_denominators_and_deduplication():
    result = score_case(["a", "b"], ["a", "a", "wrong"], answerable=True)
    assert result["recall"] == 0.5 and result["precision"] == 0.5
    assert result["retrieved"] == 2
    negative = score_case([], [], answerable=False)
    assert negative["recall"] is None and negative["precision"] is None
    assert negative["correct_abstention"] is True
    assert score_case(["a"], [], answerable=True)["unnecessary_abstention"] is True
    assert score_case(["a"], [], answerable=True)["ndcg"] == 0
    assert score_case(["a", "b"], ["a"], answerable=True, k=3)["ndcg"] < 1


def test_metric_top_k_excludes_late_gold_consistently():
    result = score_case(["gold"], ["wrong", "wrong", "gold"], answerable=True, k=1)
    assert result["recall"] == result["precision"] == result["ndcg"] == 0
    assert result["matched"] == 0 and result["retrieved"] == 1


@pytest.mark.parametrize("status,code", [("completed", 0), ("incomplete", 1)])
def test_benchmark_entrypoint_exit_status(status, code, monkeypatch):
    import research.sat_benchmark as benchmark

    monkeypatch.setattr(benchmark, "main", lambda argv: {"status": status})
    assert benchmark.cli([]) == code


def test_reference_coverage_requires_correct_edition_and_complete_span():
    from research.sat_benchmark import score_reference_spans

    refs = [{"version_id": "gold", "start": 10, "end": 20}]
    assert score_reference_spans([], []) is None
    assert (
        score_reference_spans(refs, [{"version_id": "wrong", "start": 0, "end": 50}])
        == 0
    )
    assert (
        score_reference_spans(refs, [{"version_id": "gold", "start": 10, "end": 19}])
        == 0
    )
    assert (
        score_reference_spans(refs, [{"version_id": "gold", "start": 0, "end": 20}])
        == 1
    )


def test_bootstrap_is_seeded_and_preserves_paired_sample_size():
    assert paired_interval([]) is None
    result = paired_interval([0, 0.5, 1])
    assert result == paired_interval([0, 0.5, 1])
    assert result["pairs"] == 3 and result["mean_delta"] == 0.5


@pytest.mark.parametrize(
    "defect",
    [
        "unknown_gold",
        "negative_gold",
        "duplicate",
        "empty",
        "invalid_level",
        "root_on_synthetic",
    ],
)
def test_invalid_gold_dataset_fails(defect):
    data = deepcopy(dataset())
    if defect == "unknown_gold":
        data["cases"][0]["expected_version_ids"] = ["unknown"]
    elif defect == "negative_gold":
        data["cases"][0]["answerable"] = False
    elif defect == "duplicate":
        data["cases"].append(data["cases"][0])
    elif defect in {"invalid_level", "root_on_synthetic"}:
        data["evaluation_level"] = (
            "unknown" if defect == "invalid_level" else "documentary_root"
        )
    else:
        data["cases"] = []
    with pytest.raises(ValueError):
        validate_dataset(data)


def test_offline_ablation_is_paired_and_keeps_heldout_unread():
    result = run(dataset(), repetitions=2)
    assert result["provider"] == "none_offline"
    assert len(result["records"]) == 6 * 12
    assert all("heldout" not in row["case_id"] for row in result["records"])
    for strategy, summary in result["summaries"].items():
        assert summary["cases"] == 12 and summary["answerable"] == 8
        assert summary["api"]["requests"] == 0
        if strategy != "flat_bm25":
            assert summary["ineligible_query_count"] == 0
            assert summary["correct_abstentions"] == 4
    assert all(row["stable_ranking"] for row in result["records"])


def test_heldout_requires_explicit_selection():
    result = run(dataset(), split="heldout", repetitions=1)
    assert len(result["records"]) == 6 * 2
    assert result["split"] == "heldout"


def test_api_failure_preserves_baselines_and_is_not_scored_as_abstention():
    class Unavailable:
        dimension = 1024

        def embed(self, *args, **kwargs):
            raise VoyageError("Voyage respondió HTTP 429")

        def usage(self):
            return {"requests": 1, "reported_tokens": 0}

    checkpoints = []
    result = run(
        dataset(),
        provider=Unavailable(),
        repetitions=1,
        prewarm=True,
        checkpoint=checkpoints.append,
    )
    assert result["status"] == "incomplete"
    assert len(result["records"]) == 36 and len(result["failures"]) == 36
    assert len(checkpoints) == 72
    assert result["summaries"]["bm25"]["cases"] == 12
    assert result["summaries"]["hybrid"]["macro_recall"] is None
    assert result["summaries"]["hybrid"]["correct_abstentions"] == 0
    assert result["summaries"]["hybrid"]["failed_cases"] == 12


def test_prewarm_uses_eligibility_not_gold_and_records_preparation_separately(tmp_path):
    import httpx
    from retrieval.voyage import VoyageProvider
    from tests.backend.unit.test_voyage_provider import response_for

    calls = []

    def handler(request):
        calls.append(request)
        return response_for(request)

    client = VoyageProvider(
        "test",
        tmp_path / "v.db",
        dimension=256,
        requests_per_minute=1000,
        token_bound_per_minute=100000,
        transport=httpx.MockTransport(handler),
    )
    result = run(dataset(), provider=client, repetitions=1, prewarm=True)
    assert result["status"] == "completed"
    assert result["preparation"]["api"]["requests"] == 2
    assert all(row["api"]["requests"] <= 1 for row in result["records"])
    assert all(
        row["api"]["requests"] == 0
        for row in result["records"]
        if row["strategy"] in {"ppr", "tree"}
    )


def test_rerank_only_cache_misses_are_case_local_and_unscored():
    from retrieval.sat import RankStages
    from retrieval.voyage import VoyageCacheMiss

    data = dataset()
    missing_query = data["cases"][0]["plan"]["query"]

    class PartialCache:
        dimension, cache_only = 256, True

        def embed(self, *args, **kwargs):
            pytest.fail("rerank-only no calcula embeddings ni prewarm")

        def rerank(self, query, docs, **kwargs):
            if query == missing_query:
                raise VoyageCacheMiss("Resultado ausente en caché")
            return [(i, 1) for i in range(len(docs))], dict(
                requests=0, tokens=0, cache_hits=1
            )

        def usage(self):
            return dict(requests=0, reported_tokens=0)

    result = run(
        data,
        provider=PartialCache(),
        stages=RankStages(dense=False),
        repetitions=2,
        prewarm=True,
    )
    assert result["status"] == "incomplete" and not result["preparation"]["enabled"]
    assert (
        result["provider"] == "rerank-3-lite"
        and result["provider_mode"] == "cache_only"
    )
    failures = result["failures"]
    missing_ids = {
        c["id"]
        for c in data["cases"]
        if c["split"] == "development" and c["plan"]["query"] == missing_query
    }
    assert len(failures) == 3 * len(missing_ids)
    assert {f["case_id"] for f in failures} == missing_ids
    assert all(f["error_type"] == "cache_miss" and "scores" not in f for f in failures)
    assert result["summaries"]["hybrid"]["cases"] == 12 - len(missing_ids)
    assert all(
        row["api_stages"]["dense"]["cache_hits"] == 0 for row in result["records"]
    )


def test_cache_miss_in_prewarm_does_not_disable_cached_queries():
    from retrieval.sat import RankStages
    from retrieval.voyage import VoyageCacheMiss

    class CachedQueries:
        dimension, cache_only, first = 256, True, True

        def embed(self, groups, **kwargs):
            if self.first:
                self.first = False
                raise VoyageCacheMiss("Lote no completo")
            return [[[1, 0] for _ in group] for group in groups], dict(
                requests=0, tokens=0, cache_hits=len(groups)
            )

        def usage(self):
            return dict(requests=0, reported_tokens=0)

    result = run(
        dataset(),
        provider=CachedQueries(),
        stages=RankStages(rerank=False),
        repetitions=1,
        prewarm=True,
    )
    assert result["status"] == "incomplete"
    assert (
        result["preparation"]["error_type"] == "cache_miss" and not result["failures"]
    )
    assert len(result["records"]) == 72 and result["provider"] == "voyage-context-4"
    assert all(
        s["api_stages"]["rerank"]["requests"] == 0 for s in result["summaries"].values()
    )


def test_cache_only_cli_does_not_load_credentials_and_records_stage_mode(
    tmp_path, monkeypatch
):
    import json
    import dotenv
    import research.sat_benchmark as benchmark

    def forbidden(*args, **kwargs):
        pytest.fail("cache-only no lee .env ni llama API")

    class CacheOnly:
        dimension, cache_only = 256, True
        embed = rerank = forbidden

        def __init__(self, key, path, **kwargs):
            assert key == "" and kwargs == dict(dimension=256, cache_only=True)

        def usage(self):
            return dict(requests=0, reported_tokens=0)

    monkeypatch.setattr(dotenv, "dotenv_values", forbidden)
    monkeypatch.setattr(benchmark, "VoyageProvider", CacheOnly)
    source, output = tmp_path / "dataset.json", tmp_path / "result.json"
    source.write_text(json.dumps(dataset()), encoding="utf-8")
    assert (
        benchmark.cli(
            [
                str(source),
                "--output",
                str(output),
                "--cache-only",
                "--stages",
                "lexical",
                "--dimension",
                "256",
                "--repetitions",
                "1",
                "--ppr-weight",
                "0.25",
            ]
        )
        == 0
    )
    result = json.loads(output.read_text(encoding="utf-8"))
    assert (
        result["provider_mode"] == "cache_only" and result["provider"] == "none_offline"
    )
    assert result["requested_stages"] == dict(
        dense=False, rerank=False, ppr_weight=0.25
    )
    assert all(
        row["ppr_runs"][0]["weight"] == 0.25
        for row in result["records"]
        if row["strategy"] == "ppr"
    )
    assert all(
        e == dict(dense="not_run", rerank="not_run")
        for r in result["records"]
        for e in r["stage_executions"]
    )
    with pytest.raises(SystemExit) as error:
        benchmark.main(
            [
                str(source),
                "--output",
                str(tmp_path / "invalid.json"),
                "--voyage",
                "--cache-only",
            ]
        )
    assert error.value.code == 2
