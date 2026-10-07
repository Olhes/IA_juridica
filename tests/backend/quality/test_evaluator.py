"""Controles del evaluador: dobles locales, sin generación ni juez externos."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from evaluation.deepeval_tests import LegalEvaluationSuite
from evaluation.model_quality import (
    QualityCase,
    evaluate_case,
    load_cases,
    require_credentials,
    save_report,
)

pytestmark = pytest.mark.quality


def fake_metric(score, threshold, *, lower_is_better=False, error=None):
    async def measure(case):
        if error:
            raise error

    return SimpleNamespace(
        score=score,
        threshold=threshold,
        reason="Juez simulado para test unitario",
        a_measure=AsyncMock(side_effect=measure),
        is_successful=lambda: (
            score <= threshold if lower_is_better else score >= threshold
        ),
    )


@pytest.mark.parametrize(
    "name,score,expected",
    [
        ("bias", 0.1, True),
        ("bias", 0.8, False),
        ("bias", 0.3, True),
        ("hallucination", 0.0, True),
        ("hallucination", 0.8, False),
        ("relevancy", 0.9, True),
        ("relevancy", 0.2, False),
    ],
)
async def test_metric_uses_its_own_success_direction(name, score, expected):
    low = name in {"bias", "hallucination"}
    metric = fake_metric(score, 0.3 if low else 0.7, lower_is_better=low)
    suite = LegalEvaluationSuite(metrics={name: metric})
    result = await suite.run_single_evaluation(
        SimpleNamespace(input="Pregunta ficticia")
    )
    assert result["metrics"][name]["passed"] is expected
    assert result["passed"] is expected
    metric.a_measure.assert_awaited_once()
    assert suite._analyze_metrics([result])[name]["passed_count"] == int(expected)


async def test_one_failed_metric_cannot_hide_behind_average():
    metrics = {f"metric-{i}": fake_metric(1.0, 0.7) for i in range(4)}
    metrics["hallucination"] = fake_metric(0.8, 0.3, lower_is_better=True)
    result = await LegalEvaluationSuite(metrics=metrics).run_single_evaluation(
        SimpleNamespace(input="Q")
    )
    assert result["overall_score"] == 0.8
    assert result["passed"] is False


async def test_metric_error_is_failure_and_does_not_expose_exception_message():
    metric = fake_metric(1.0, 0.7, error=RuntimeError("SECRET must not be recorded"))
    result = await LegalEvaluationSuite(
        metrics={"broken": metric}
    ).run_single_evaluation(SimpleNamespace(input="Q"))
    assert result["passed"] is False
    assert result["metrics"]["broken"]["error"] == "RuntimeError"
    assert "SECRET" not in json.dumps(result)


def test_dataset_is_nonempty_unique_and_has_controlled_context():
    cases = load_cases()
    assert len(cases) == 3
    assert len({case.id for case in cases}) == 3
    assert all(case.context and case.expected_output for case in cases)


@pytest.mark.parametrize(
    "data",
    [[], [{"id": "empty", "input": "", "expected_output": "x", "context": ["c"]}]],
)
def test_invalid_dataset_fails(tmp_path, data):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(path)


def test_live_credentials_fail_clearly_without_reading_real_env(monkeypatch):
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **kw: None)
    for name in ("COHERE_API_KEY", "OPENAI_API_KEY", "EVAL_JUDGE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(
        ValueError, match="COHERE_API_KEY, OPENAI_API_KEY, EVAL_JUDGE_MODEL"
    ):
        require_credentials()


async def test_live_pipeline_uses_generated_output_and_saves_report(tmp_path):
    case = QualityCase("control", "Consulta", "Referencia", ["Contexto de prueba"])
    generator = AsyncMock(
        return_value=(
            "Respuesta recién generada",
            {"generation_model": "fake-generator"},
        )
    )
    suite = SimpleNamespace(
        run_single_evaluation=AsyncMock(
            return_value={
                "passed": True,
                "metrics": {
                    "faithfulness": {"score": 0.9, "threshold": 0.7, "passed": True}
                },
            }
        )
    )
    result = await evaluate_case(
        case, "fake-judge", generator=generator, suite_factory=lambda model: suite
    )
    evaluated = suite.run_single_evaluation.call_args.args[0]
    assert evaluated.actual_output == "Respuesta recién generada"
    assert evaluated.context == evaluated.retrieval_context == case.context
    assert result["actual_output"] != case.expected_output
    assert result["passed"] is True
    report = save_report([result], tmp_path)
    assert json.loads(report.read_text(encoding="utf-8"))["passed"] == 1
    assert "fake-generator" in (tmp_path / "report.md").read_text(encoding="utf-8")


async def test_generation_failure_is_reported_without_fallback(tmp_path):
    generator = AsyncMock(side_effect=RuntimeError("SECRET credential in SDK error"))
    factory = AsyncMock()
    case = load_cases()[0]
    result = await evaluate_case(
        case, "fake-judge", generator=generator, suite_factory=factory
    )
    assert result["passed"] is False
    assert result["error"] == "RuntimeError"
    assert "actual_output" not in result
    factory.assert_not_called()
    path = save_report([result], tmp_path)
    assert "SECRET" not in path.read_text(encoding="utf-8")


async def test_generation_timeout_is_a_failed_evaluation():
    async def slow_generator(case):
        await asyncio.sleep(1)

    result = await evaluate_case(
        load_cases()[0], "fake-judge", timeout=0.01, generator=slow_generator
    )
    assert result["passed"] is False
    assert result["error"] == "TimeoutError"


async def test_empty_generated_response_is_a_failure():
    generator = AsyncMock(return_value=("", {}))
    result = await evaluate_case(load_cases()[0], "fake-judge", generator=generator)
    assert result["passed"] is False
    assert result["error"] == "ValueError"


def test_judge_factory_receives_explicit_model_and_key(monkeypatch):
    import deepeval.models
    import evaluation.deepeval_tests as evaluation
    from evaluation.model_quality import create_suite

    observed = {}
    judge = object()

    def fake_judge(**kwargs):
        observed.update(kwargs)
        return judge

    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-key")
    monkeypatch.setattr(deepeval.models, "GPTModel", fake_judge)
    monkeypatch.setattr(evaluation, "LegalEvaluationSuite", lambda **kwargs: kwargs)
    assert create_suite("explicit-judge") == {"judge_model": judge}
    assert observed == {"model": "explicit-judge", "api_key": "offline-test-key"}


def test_missing_deepeval_never_silently_falls_back(monkeypatch):
    import evaluation.deepeval_tests as evaluation

    monkeypatch.setattr(evaluation, "DEEPEVAL_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="juez real"):
        evaluation.LegalEvaluationSuite()


@pytest.fixture
def root_hooks():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "conftest.py"
    spec = importlib.util.spec_from_file_location("quality_root_hooks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_opt_in_marks_live_cases_skipped(root_hooks):
    markers = []
    item = SimpleNamespace(
        get_closest_marker=lambda name: True, add_marker=markers.append
    )
    config = SimpleNamespace(getoption=lambda name: False)
    root_hooks.pytest_collection_modifyitems(config, [item])
    assert markers[0].name == "skip"


@pytest.mark.parametrize("timeout", [0, -1, float("nan")])
def test_invalid_live_timeout_is_a_usage_error(root_hooks, timeout):
    options = {"--run-model-evals": True, "--model-eval-timeout": timeout}
    config = SimpleNamespace(getoption=options.__getitem__)
    with pytest.raises(pytest.UsageError, match="positivo y finito"):
        root_hooks.pytest_collection_modifyitems(config, [])


def test_opt_in_without_credentials_is_an_error_not_skip(root_hooks, monkeypatch):
    import evaluation.model_quality as quality

    def missing():
        raise ValueError("Falta configurar: OPENAI_API_KEY")

    monkeypatch.setattr(quality, "require_credentials", missing)
    item = SimpleNamespace(get_closest_marker=lambda name: True)
    options = {"--run-model-evals": True, "--model-eval-timeout": 180}
    with pytest.raises(pytest.UsageError, match="OPENAI_API_KEY"):
        root_hooks.pytest_collection_modifyitems(
            SimpleNamespace(getoption=options.__getitem__), [item]
        )
