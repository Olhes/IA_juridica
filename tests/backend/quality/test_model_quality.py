"""Generación real: no se ejecuta sin --run-model-evals."""

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from evaluation.model_quality import evaluate_case, load_cases, save_report

pytestmark = pytest.mark.model_quality


@pytest.fixture(scope="session")
def quality_results(request):
    results = []
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    )
    directory = Path(request.config.getoption("--quality-report-dir")) / run_id
    request.config._model_quality_report_directory = directory.resolve()
    yield results, directory
    if results:
        save_report(results, directory)
        print(f"\nInforme de calidad: {directory.resolve()}")


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case.id)
async def test_live_model_quality(case, request, quality_results):
    results, directory = quality_results
    result = await evaluate_case(
        case,
        os.environ["EVAL_JUDGE_MODEL"],
        timeout=request.config.getoption("--model-eval-timeout"),
    )
    results.append(result)
    # Persistir también antes del assert: el informe existe aunque una métrica falle.
    save_report(results, directory)
    assert result[
        "passed"
    ], f"Calidad insuficiente o error de evaluación; ver {directory.resolve()}"
