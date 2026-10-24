"""Comparación entre commits: bootstrap pareado, veredicto, bloqueos, A/B ciego y orquestación con git worktree."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from evaluation.harness import ab, compare
from evaluation.harness.answers import Answer
from evaluation.harness.digest import pipeline_digest
from evaluation.harness.judges import CallableJudge, NoJudge
from evaluation.harness.pipeline_eval import evaluate_gold
from evaluation.harness.runner import collect_metadata, write_result
from optimization.query_cache import pipeline_digest as cache_digest

from .conftest import oracle_answer

pytestmark = pytest.mark.harness


def rows(values, metric="legal_factuality"):
    return {f"c{i:02d}": {metric: (v, v, 1.0)} for i, v in enumerate(values)}


def test_digest_matches_the_cache_key_digest():
    assert pipeline_digest() == cache_digest() and len(pipeline_digest()) == 64


def test_paired_bootstrap_detects_a_consistent_improvement_and_a_consistent_regression():
    base, head = rows([0.5] * 20), rows([0.7] * 20)
    better = compare.compare_metric(base, head, "legal_factuality", "macro", True)
    assert better["delta"] == pytest.approx(0.2) and better["ci"] == pytest.approx([0.2, 0.2]) and better["status"] == "better"
    assert compare.compare_metric(head, base, "legal_factuality", "macro", True)["status"] == "worse"
    lower = compare.compare_metric(base, head, "legal_factuality", "macro", False)
    assert lower["status"] == "worse"  # si menos es mejor, subir empeora


def test_noise_is_not_reported_as_a_change_and_small_samples_make_no_claim():
    base = rows([0.4, 0.8, 0.5, 0.9, 0.3, 0.7, 0.6, 0.2, 0.9, 0.5, 0.4, 0.6])
    head = rows([0.5, 0.7, 0.5, 0.9, 0.4, 0.6, 0.6, 0.3, 0.8, 0.5, 0.5, 0.5])
    noisy = compare.compare_metric(base, head, "legal_factuality", "macro", True)
    assert noisy["status"] == "same" and noisy["ci"][0] < 0 < noisy["ci"][1]
    tiny = compare.compare_metric(rows([0.1] * 4), rows([0.9] * 4), "legal_factuality", "macro", True)
    assert tiny["status"] == "insufficient" and tiny["delta"] == pytest.approx(0.8)


def test_bootstrap_is_deterministic_for_a_seed_and_pairs_cases_by_id():
    base, head = rows([0.1, 0.9, 0.4, 0.6, 0.2, 0.8, 0.5, 0.5, 0.3]), rows([0.2, 0.8, 0.5, 0.9, 0.2, 0.9, 0.4, 0.6, 0.5])
    first = compare.compare_metric(base, head, "legal_factuality", "macro", True, seed=3)
    assert first == compare.compare_metric(base, head, "legal_factuality", "macro", True, seed=3)
    head["solo-en-head"] = {"legal_factuality": (1.0, 1.0, 1.0)}
    del base["c00"]
    assert compare.compare_metric(base, head, "legal_factuality", "macro", True)["n"] == 8  # solo los casos presentes en ambos


def test_micro_pools_numerators_and_denominators_while_macro_averages_cases():
    base = {"a": {"m": (1.0, 1.0, 1.0)}, "b": {"m": (0.25, 1.0, 4.0)}}
    head = {"a": {"m": (1.0, 1.0, 1.0)}, "b": {"m": (0.75, 3.0, 4.0)}}
    micro = compare.paired_delta([(base[k]["m"], head[k]["m"]) for k in base], "micro")
    macro = compare.paired_delta([(base[k]["m"], head[k]["m"]) for k in base], "macro")
    assert micro["base"] == pytest.approx(2 / 5) and micro["head"] == pytest.approx(4 / 5)
    assert macro["base"] == pytest.approx(0.625) and macro["head"] == pytest.approx(0.875)
    assert compare.paired_delta([], "macro")["delta"] is None


def test_case_changes_lists_the_cases_that_moved_most():
    moves = compare.case_changes(rows([0.9, 0.5, 0.1]), rows([0.2, 0.5, 0.8]), "legal_factuality", True)
    assert [m["case_id"] for m in moves["regressed"]] == ["c00"] and [m["case_id"] for m in moves["improved"]] == ["c02"]


def result_of(case, hits=(), abstained=None):
    scores = {"abstention_recall": {"value": abstained, "num": 0, "den": 1}} if abstained is not None else {}
    return {"id": case, "stratum": "limite", "forbidden_hits": list(hits), "scores": scores}


def test_a_new_unsupported_claim_blocks_even_if_everything_else_is_unchanged():
    base = {"cases": [result_of("a"), result_of("b", hits=["viejo"])]}
    head = {"cases": [result_of("a", hits=["nuevo"]), result_of("b", hits=["viejo"])]}
    blocks = compare.legal_qa_blocks(base, head)
    assert [(b["kind"], b["case_id"], b["detail"]) for b in blocks] == [("afirmación_nueva_sin_respaldo", "a", ["nuevo"])]
    assert compare.legal_qa_blocks(head, base) == []  # dejar de afirmar algo prohibido no bloquea


def test_an_out_of_corpus_case_that_stops_abstaining_blocks():
    base, head = {"cases": [result_of("n1", abstained=1.0)]}, {"cases": [result_of("n1", abstained=0.0)]}
    assert [b["kind"] for b in compare.legal_qa_blocks(base, head)] == ["dejó_de_abstenerse"]


def metric(status, name="legal_factuality"):
    return {"metric": name, "status": status}


def test_verdict_rules():
    suite = lambda statuses, **extra: {"suite": "legal_qa", "metrics": [metric(s) for s in statuses], "blocks": [], **extra}  # noqa: E731
    assert compare.verdict([suite(["same", "insufficient"])])["verdict"] == compare.SAME
    assert compare.verdict([suite(["same", "better"])])["verdict"] == compare.IMPROVED
    assert compare.verdict([suite(["better", "worse"])])["verdict"] == compare.WORSE
    assert compare.verdict([suite(["same"], errors={"worse": True})])["verdict"] == compare.WORSE
    blocked = compare.verdict([suite(["better"], blocks=[{"kind": "x"}])])
    assert blocked["verdict"] == compare.WORSE and blocked["blocking"] is True
    assert compare.verdict([])["verdict"] == compare.SAME and compare.verdict([])["evidence"] == "insuficiente"


def test_meta_diff_reports_what_changed_and_flags_incomparable_measurements():
    base = {"prompt_digest": "a", "gold_hash": "g", "judge": {"name": "none"}, "models": {"llm": "x"}}
    head = {"prompt_digest": "b", "gold_hash": "g", "judge": {"name": "none"}, "models": {"llm": "y"}}
    diff = compare.meta_diff(base, head)
    assert set(diff["changed"]) == {"prompt_digest", "models"} and diff["comparable"] is True
    other_gold = compare.meta_diff(base, head | {"gold_hash": "otro"})
    assert other_gold["comparable"] is False and "gold_hash" in other_gold["problems"][0]
    assert compare.meta_diff(base, head | {"judge": {"name": "deepeval"}})["comparable"] is False


def test_stream_validity_drop_blocks_and_latency_is_reported():
    base = {"valid_stream_rate": 1.0, "final_rate": 1.0, "error_rate": 0.0, "n_streams": 5, "stage_ms": {"retrieval": {"p95": 10.0}}}
    head = {"valid_stream_rate": 0.8, "final_rate": 0.8, "error_rate": 0.2, "n_streams": 5, "stage_ms": {"retrieval": {"p95": 30.0}}}
    result = compare.compare_suite("stream", {"meta": {}, **base}, {"meta": {}, **head})
    assert [b["kind"] for b in result["blocks"]] == ["cayó_la_validez_del_stream"]
    assert {m["metric"]: m["status"] for m in result["metrics"]} == {"valid_stream_rate": "worse", "final_rate": "worse", "error_rate": "worse"}
    assert result["latency_p95_ms"]["retrieval"] == {"base": 10.0, "head": 30.0}


async def report_for(cases, corpus, tmp_path, name, answer_for):
    async def answer_fn(case, sample):
        return answer_for(case)

    report = await evaluate_gold(cases, answer_fn, corpus=corpus)
    meta = collect_metadata(corpus=corpus, judge=NoJudge(), samples=1, eval_mode=False) | {"sha": name}
    return write_result(report, meta, "legal_qa", tmp_path)


async def test_end_to_end_one_hallucination_blocks_while_a_general_improvement_is_recognised(gold, corpus, tmp_path):
    degraded = lambda c: Answer(text="Respuesta vaga sin datos.", evidence_status="retrieved", confidence_score=0.9) if not c.must_abstain else oracle_answer(c)  # noqa: E731
    answerable = next(c for c in gold if c.forbidden_claims and not c.must_abstain)

    def hallucinating(case):
        answer = oracle_answer(case)
        if case.id == answerable.id:
            answer.text += " " + answerable.forbidden_claims[0].example
        return answer

    paths = {name: await report_for(gold, corpus, tmp_path, name, fn)
             for name, fn in (("oracle", oracle_answer), ("degraded", degraded), ("halluc", hallucinating))}
    ref = lambda name: {"ref": name, "sha": name.ljust(40, "0"), "paths": {"legal_qa": paths[name]}}  # noqa: E731

    better = compare.build_report(ref("degraded"), ref("oracle"), suites=("legal_qa", "stream"))
    assert better["verdict"]["verdict"] == compare.IMPROVED and not better["verdict"]["blocking"]
    assert better["missing"] == ["`stream`: faltan resultados de base y head"] and better["comparable"] is True

    blocked = compare.build_report(ref("oracle"), ref("halluc"), suites=("legal_qa",))
    assert blocked["verdict"]["verdict"] == compare.WORSE and blocked["verdict"]["blocking"] is True
    assert blocked["verdict"]["blocks"][0]["case_id"] == answerable.id

    worse = compare.build_report(ref("oracle"), ref("degraded"), suites=("legal_qa",))
    assert worse["verdict"]["verdict"] == compare.WORSE and not worse["verdict"]["blocking"]

    same = compare.build_report(ref("oracle"), ref("oracle"), suites=("legal_qa",))
    assert same["verdict"]["verdict"] == compare.SAME

    markdown = compare.render_markdown(blocked)
    assert "**Veredicto: EMPEORÓ** — **BLOQUEANTE**" in markdown and answerable.id in markdown and "| `legal_factuality` |" in markdown
    json_path, md_path = compare.write_report(blocked, tmp_path / "out")
    assert json.loads(json_path.read_text(encoding="utf-8"))["verdict"]["blocking"] is True and md_path.read_text(encoding="utf-8") == markdown


def test_trials_are_blinded_crossed_and_skip_identical_answers():
    base = {"c1": "respuesta vieja", "c2": "igual", "c3": "otra vieja"}
    head = {"c1": "respuesta nueva", "c2": "igual", "c3": "otra nueva"}
    trials = ab.build_trials(base, head, {"c1": "¿q1?", "c3": "¿q3?"}, seed=5)
    assert len(trials) == 4 and {t.case_id for t in trials} == {"c1", "c3"}
    for case in ("c1", "c3"):
        pair = [t for t in trials if t.case_id == case]
        assert {t.a_is for t in pair} == {"base", "head"} and pair[0].answer_a == pair[1].answer_b
    for trial in trials:
        shown = json.dumps(trial.blinded())
        assert "base" not in shown and "head" not in shown and trial.case_id not in shown
        assert set(trial.blinded()) == {"trial_id", "query", "answer_a", "answer_b"}
    assert [t.trial_id for t in trials] == [t.trial_id for t in ab.build_trials(base, head, {}, seed=5)]
    assert len({t.trial_id for t in trials}) == 4


async def test_blind_ab_recognises_a_consistent_judge_and_exposes_position_bias():
    base = {f"c{i}": f"vieja {i}" for i in range(10)}
    head = {f"c{i}": f"nueva {i}" for i in range(10)}
    trials = ab.build_trials(base, head, {}, seed=1)
    prefers_new = CallableJudge(prefer=lambda q, a, b: "A" if a.startswith("nueva") else "B")
    resolved = ab.resolve(trials, await ab.judge_trials(prefers_new, trials))
    assert resolved["counts"]["head"] == 10 and resolved["head_win_rate"] == 1.0
    assert resolved["sign_test_p"] == pytest.approx(2 / 2**10) and resolved["position_bias_rate"] == 0.0
    always_a = CallableJudge(prefer=lambda q, a, b: "A")
    biased = ab.resolve(trials, await ab.judge_trials(always_a, trials))
    assert biased["counts"]["inconsistent"] == 10 and biased["head_win_rate"] is None and biased["position_bias_rate"] == 1.0
    ties = ab.resolve(trials, await ab.judge_trials(CallableJudge(prefer=lambda q, a, b: "tie"), trials))
    assert ties["counts"]["tie"] == 10
    unjudged = ab.resolve(trials, await ab.judge_trials(NoJudge(), trials))
    assert unjudged["counts"]["unjudged"] == 10 and unjudged["sign_test_p"] is None


def test_sign_test_matches_exact_binomial_values():
    assert ab.sign_test_p(8, 0) == pytest.approx(2 / 256)
    assert ab.sign_test_p(5, 5) == 1.0
    assert ab.sign_test_p(0, 0) is None
    assert ab.sign_test_p(7, 3) == pytest.approx(2 * (1 + 10 + 45 + 120) / 1024)


def git_env():
    return dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.test", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.test")


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "backend" / "services").mkdir(parents=True)
    run = lambda *args: subprocess.run(["git", *args], cwd=repo, env=git_env(), check=True, capture_output=True, text=True)  # noqa: E731
    run("init", "-q", "-b", "main")
    (repo / "backend" / "services" / "pipeline.py").write_text("VERSION = 'base'\n", encoding="utf-8")
    run("add", "-A"), run("commit", "-q", "-m", "base")
    run("tag", "v-base")
    (repo / "backend" / "services" / "pipeline.py").write_text("VERSION = 'head'\n", encoding="utf-8")
    run("commit", "-qam", "head")
    return repo, run


def test_results_are_reused_and_missing_ones_run_in_a_temporary_worktree_with_the_new_harness(tmp_path, monkeypatch):
    for key, value in git_env().items():
        monkeypatch.setenv(key, value)
    repo, run = make_repo(tmp_path)
    (repo / "backend" / "evaluation" / "harness").mkdir(parents=True)
    (repo / "backend" / "evaluation" / "harness" / "marker.py").write_text("HARNESS = 'nuevo'\n", encoding="utf-8")
    results = tmp_path / "results"
    base_sha = compare.resolve_sha(repo, "v-base")
    assert base_sha != compare.resolve_sha(repo, "HEAD") and len(base_sha) == 40
    seen = []

    def fake_runner(worktree, suite, results_dir, extra):
        seen.append((suite, (worktree / "backend" / "services" / "pipeline.py").read_text(encoding="utf-8").strip(),
                     (worktree / "backend" / "evaluation" / "harness" / "marker.py").exists(), tuple(extra)))
        target = compare.result_path(results_dir, base_sha, suite)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
        return 0

    nothing = compare.ensure_results(repo, "v-base", ["legal_qa"], results, run_missing=False, runner=fake_runner)
    assert nothing["paths"] == {"legal_qa": None} and seen == []
    first = compare.ensure_results(repo, "v-base", ["legal_qa", "retrieval"], results, run_missing=True, extra=["--x"],
                                   runner=fake_runner, worktree_base=tmp_path)
    assert [s[0] for s in seen] == ["legal_qa", "retrieval"]
    assert all(s[1] == "VERSION = 'base'" and s[2] is True and s[3] == ("--x",) for s in seen)  # código del commit + harness actual
    assert all(path and path.exists() for path in first["paths"].values())
    assert not compare.worktree_path(base_sha, tmp_path).exists()
    assert "iaj-wt-" not in run("worktree", "list").stdout
    again = compare.ensure_results(repo, "v-base", ["legal_qa"], results, run_missing=True, runner=fake_runner, worktree_base=tmp_path)
    assert len(seen) == 2 and again["paths"]["legal_qa"].exists()  # se reutiliza


def test_a_failing_run_still_removes_the_worktree(tmp_path, monkeypatch):
    for key, value in git_env().items():
        monkeypatch.setenv(key, value)
    repo, run = make_repo(tmp_path)

    def boom(*_args):
        raise RuntimeError("fallo del runner")

    with pytest.raises(RuntimeError):
        compare.ensure_results(repo, "HEAD", ["legal_qa"], tmp_path / "results", run_missing=True, runner=boom, worktree_base=tmp_path)
    assert "iaj-wt-" not in run("worktree", "list").stdout and not compare.worktree_path(compare.resolve_sha(repo, "HEAD"), tmp_path).exists()


def test_unknown_refs_fail_with_a_clear_message(tmp_path, monkeypatch):
    repo, _ = make_repo(tmp_path)
    with pytest.raises(RuntimeError, match="rev-parse"):
        compare.resolve_sha(repo, "no-existe")
