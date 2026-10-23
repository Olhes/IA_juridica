"""Evaluación del gold con respuestas sintéticas, cassettes, umbrales y resultados en disco."""

import json

import pytest

from evaluation.harness import thresholds
from evaluation.harness.answers import Answer
from evaluation.harness.cassettes import REPLAY, Cassette, CassetteMiss, canonical_key
from evaluation.harness.judges import CallableJudge, DeepEvalJudge, NoJudge, make_judge
from evaluation.harness.pipeline_eval import evaluate_gold
from evaluation.harness.runner import cassette_answer_fn, collect_metadata, write_result

from .conftest import oracle_answer

pytestmark = pytest.mark.harness


async def run(cases, corpus, answer_for, **kwargs):
    async def answer_fn(case, sample):
        return answer_for(case, sample)

    return await evaluate_gold(cases, answer_fn, corpus=corpus, **kwargs)


async def test_oracle_answers_score_perfectly_on_every_applicable_metric(gold, corpus):
    report = await run(gold, corpus, lambda case, _: oracle_answer(case))
    metrics = report["metrics"]
    assert report["n_cases"] == len(gold) and report["n_errors"] == 0
    assert metrics["legal_factuality"]["macro"]["value"] == 1.0
    assert metrics["fact_recall"]["micro"]["value"] == 1.0
    assert metrics["forbidden_claim"]["macro"]["value"] == 0.0
    assert metrics["abstention_recall"]["macro"]["value"] == 1.0
    assert metrics["unnecessary_abstention"]["macro"]["value"] == 0.0
    assert metrics["abstention_formal"]["macro"]["value"] == 1.0
    assert report["gold"]["adjudicated"] == 0 and report["gold"]["status"] == {"candidate": len(gold)}
    assert set(report["by_stratum"]) == {"positivo", "limite", "negativo"}
    assert report["by_stratum"]["negativo"]["legal_factuality"]["macro"]["value"] is None
    assert report["by_split"]["holdout"]["fact_recall"]["n"] > 0


async def test_degraded_answers_lower_factuality_and_expose_missing_facts(gold, corpus):
    def degraded(case, _):
        if case.must_abstain:
            return Answer(text="Claro, el trámite consiste en acudir a la oficina correspondiente.", evidence_status="retrieved")
        return Answer(text="Es un tema complejo; consulta a un profesional.", evidence_status="retrieved", confidence_score=0.9)

    report = await run(gold, corpus, degraded)
    assert report["metrics"]["legal_factuality"]["macro"]["value"] == 0.0
    assert report["metrics"]["abstention_recall"]["macro"]["value"] == 0.0
    assert report["calibration"]["ece"] == pytest.approx(0.9)
    first = next(c for c in report["cases"] if c["stratum"] == "positivo")
    assert first["missing_facts"] and first["factual_pass"] == 0.0


async def test_forbidden_claim_in_an_otherwise_correct_answer_is_reported(cases, corpus):
    case = cases["pension-tope-embargo"]
    answer = Answer(text="El embargo tiene un tope legal del 60% de los ingresos, aunque se puede embargar el 100% de tus ingresos.")
    report = await run([case], corpus, lambda *_: answer)
    assert report["cases"][0]["forbidden_hits"] == ["embargo-total"]
    assert report["metrics"]["legal_factuality"]["macro"]["value"] == 0.0


async def test_errors_are_counted_not_converted_into_zeros(gold, corpus):
    def flaky(case, _):
        if case.id == "pension-contenido-alimentos":
            raise TimeoutError("PRIVADO: texto de la excepción")
        return oracle_answer(case)

    report = await run(gold, corpus, flaky)
    assert report["n_errors"] == 1 and report["n_cases"] == len(gold) - 1
    assert report["errors"] == [{"case_id": "pension-contenido-alimentos", "sample": 0, "error": "TimeoutError"}]
    assert "PRIVADO" not in json.dumps(report)
    assert report["metrics"]["legal_factuality"]["macro"]["value"] == 1.0


async def test_samples_are_merged_per_case(cases, corpus):
    case = cases["visitas-requisitos-conciliacion"]
    good, bad = oracle_answer(case), Answer(text="No sé.", evidence_status="retrieved")
    report = await run([case], corpus, lambda _case, sample: good if sample == 0 else bad, samples=2)
    assert report["samples"] == 2 and len(report["answers"]) == 2
    assert report["metrics"]["fact_recall"]["macro"]["value"] == pytest.approx(0.5)


async def test_judge_metrics_are_na_without_a_judge_and_present_with_one(cases, corpus):
    case = cases["pension-contenido-alimentos"]
    plain = await run([case], corpus, lambda c, _: oracle_answer(c))
    assert plain["judge"]["available"] is False and plain["judge"]["name"] == "none"
    assert plain["metrics"]["faithfulness_judge"]["macro"]["value"] is None
    assert "juez no disponible" in plain["metrics"]["fact_recall_judge"]["macro"]["na_reason"]
    judge = CallableJudge(faithfulness=lambda *_: 0.75, fact_present=lambda _answer, _fact: True)
    judged = await run([case], corpus, lambda c, _: oracle_answer(c), judge=judge)
    assert judged["judge"] == {"name": "callable", "model": "test-judge", "available": True, "unavailable_reason": None}
    assert judged["metrics"]["faithfulness_judge"]["macro"]["value"] == 0.75
    assert judged["metrics"]["fact_recall_judge"]["macro"]["value"] == 1.0


def test_judge_factory_registers_availability_without_calling_models(monkeypatch):
    monkeypatch.delenv("EVAL_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert make_judge("none").info()["available"] is False
    deep = make_judge("deepeval")
    assert isinstance(deep, DeepEvalJudge) and not deep.available and "EVAL_JUDGE_MODEL" in deep.unavailable_reason
    monkeypatch.setenv("EVAL_JUDGE_MODEL", "modelo-juez")
    monkeypatch.setenv("OPENAI_API_KEY", "clave-ficticia")
    configured = make_judge("deepeval").info()
    assert configured["available"] is True and configured["model"] == "modelo-juez" and "clave" not in json.dumps(configured)
    with pytest.raises(ValueError):
        make_judge("desconocido")
    assert isinstance(NoJudge(), NoJudge)


async def test_cassette_replays_records_and_refuses_unrecorded_requests(tmp_path, cases):
    case = cases["visitas-requisitos-conciliacion"]
    path = tmp_path / "cassette.json"
    calls = []

    async def live(c, sample):
        calls.append((c.id, sample))
        return oracle_answer(c)

    replay = Cassette(path, REPLAY)
    with pytest.raises(CassetteMiss):
        await cassette_answer_fn(replay)(case, 0)
    recorder = Cassette(path, "record_missing")
    recorded = await cassette_answer_fn(recorder, live)(case, 0)
    recorder.save()
    assert calls == [(case.id, 0)] and recorded.text
    again = await cassette_answer_fn(Cassette(path, REPLAY))(case, 0)
    assert again == recorded and calls == [(case.id, 0)]
    with pytest.raises(PermissionError):
        Cassette(path, REPLAY).put({"x": 1}, {})
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert list(stored["entries"].values())[0]["request"]["case"] == case.id
    assert canonical_key({"b": 1, "a": 2}) == canonical_key({"a": 2, "b": 1})


async def test_result_file_carries_reproducibility_metadata(gold, corpus, tmp_path):
    report = await run(gold[:3], corpus, lambda c, _: oracle_answer(c))
    meta = collect_metadata(corpus=corpus, judge=NoJudge(), samples=1, eval_mode=False)
    path = write_result(report, meta, "legal_qa", tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert path == tmp_path / meta["sha"] / "legal_qa.json"
    for key in ("sha", "prompt_digest", "corpus_revision", "gold_hash", "models", "judge", "judge_available", "eval_mode", "samples"):
        assert key in saved["meta"], key
    assert saved["meta"]["judge_available"] is False and len(saved["meta"]["prompt_digest"]) == 64
    assert saved["meta"]["models"]["llm"] and saved["metrics"] and saved["gold"]["adjudicated"] == 0


def baseline_file(tmp_path, adjudicated=0, gold_hash="g1"):
    path = tmp_path / "legal_qa.json"
    path.write_text(json.dumps({
        "meta": {"sha": "abc", "gold_hash": gold_hash, "prompt_digest": "d"},
        "gold": {"adjudicated": adjudicated},
        "metrics": {"legal_factuality": {"macro": {"value": 0.6}, "micro": {"value": 0.5}},
                    "citation_acceptable": {"macro": {"value": None}}},
    }), encoding="utf-8")
    return path


def test_thresholds_are_unregistered_by_default_and_never_pass_silently():
    document = thresholds.load_thresholds()
    assert document["status"] == "unregistered" and document["thresholds"] == {}
    verdict = thresholds.check({"meta": {"gold_hash": "x"}, "metrics": {}}, document)
    assert verdict["status"] == "unregistered" and verdict["checks"] == []


def test_registration_requires_a_baseline_measurement_and_adjudicated_gold(tmp_path):
    rules = {"legal_factuality": {"scope": "macro", "min": 0.5}}
    with pytest.raises(thresholds.ThresholdError, match="baseline"):
        thresholds.register(tmp_path / "no-existe.json", rules, tmp_path / "t.json")
    with pytest.raises(thresholds.ThresholdError, match="adjudicados"):
        thresholds.register(baseline_file(tmp_path), rules, tmp_path / "t.json")
    with pytest.raises(thresholds.ThresholdError, match="n/a"):
        thresholds.register(baseline_file(tmp_path), {"citation_acceptable": {"min": 0.5}}, tmp_path / "t.json", allow_unadjudicated=True)
    with pytest.raises(thresholds.ThresholdError):
        thresholds.register(baseline_file(tmp_path), {"legal_factuality": {"scope": "macro"}}, tmp_path / "t.json", allow_unadjudicated=True)


def test_registered_thresholds_pass_fail_and_go_stale_with_the_gold(tmp_path):
    out = tmp_path / "t.json"
    document = thresholds.register(baseline_file(tmp_path, adjudicated=4), {"legal_factuality": {"scope": "macro", "min": 0.55}}, out)
    assert document["provisional"] is False and document["baseline"]["sha"] == "abc" and len(document["baseline"]["result_sha256"]) == 64
    loaded = thresholds.load_thresholds(out)
    ok = {"meta": {"gold_hash": "g1"}, "metrics": {"legal_factuality": {"macro": {"value": 0.7}}}}
    low = {"meta": {"gold_hash": "g1"}, "metrics": {"legal_factuality": {"macro": {"value": 0.4}}}}
    missing = {"meta": {"gold_hash": "g1"}, "metrics": {"legal_factuality": {"macro": {"value": None}}}}
    assert thresholds.check(ok, loaded)["status"] == "pass"
    assert thresholds.check(low, loaded)["status"] == "fail"
    assert thresholds.check(missing, loaded)["status"] == "fail"
    assert thresholds.check({**ok, "meta": {"gold_hash": "otro"}}, loaded)["status"] == "stale"
    provisional = thresholds.register(baseline_file(tmp_path), {"legal_factuality": {"min": 0.1}}, tmp_path / "p.json", allow_unadjudicated=True)
    assert provisional["provisional"] is True
