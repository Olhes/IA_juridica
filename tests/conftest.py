"""Hooks comunes y opt-in; las fixtures HTTP viven en tests/backend/."""

import math
from pathlib import Path
from uuid import uuid4

import pytest

pytest_plugins = ["tests.backend.fixtures.validation"]


def pytest_configure(config):
    # Directorio único por ejecución: no reutiliza ni borra temporales de otra sesión.
    if config.option.basetemp is None:
        root = Path(__file__).resolve().parents[1]
        parent = root / "temp" / "pytest-runs"
        parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(parent / uuid4().hex)


def pytest_addoption(parser):
    group = parser.getgroup("model-quality")
    group.addoption(
        "--run-model-evals",
        action="store_true",
        default=False,
        help="Genera respuestas con Cohere y usa juez DeepEval (red/coste)",
    )
    group.addoption(
        "--quality-report-dir",
        default="temp/model-quality",
        help="Directorio de informes locales JSON/Markdown",
    )
    group.addoption(
        "--model-eval-timeout",
        type=float,
        default=180,
        help="Máximo de segundos por caso (generación y evaluación)",
    )


def pytest_collection_modifyitems(config, items):
    # La carpeta es la fuente de verdad del tipo; no depender de decoradores
    # olvidados al añadir un caso nuevo. Calidad mantiene sus marcas explícitas.
    for item in items:
        if getattr(item, "path", None) is None:
            continue
        parts = Path(item.path).relative_to(config.rootpath / "tests").parts
        if len(parts) > 1 and parts[1] in {"unit", "integration", "security", "http", "contract", "bdd", "benchmark", "harness"}:
            item.add_marker(getattr(pytest.mark, parts[1]))
    live = [item for item in items if item.get_closest_marker("model_quality")]
    if not config.getoption("--run-model-evals"):
        for item in live:
            item.add_marker(
                pytest.mark.skip(
                    reason="Evaluación real: requiere --run-model-evals (red/coste)"
                )
            )
        return
    timeout = config.getoption("--model-eval-timeout")
    if not math.isfinite(timeout) or timeout <= 0:
        raise pytest.UsageError("--model-eval-timeout debe ser positivo y finito")
    if live:
        from evaluation.model_quality import require_credentials

        try:
            require_credentials()
        except ValueError as error:
            raise pytest.UsageError(str(error)) from None


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    directory = getattr(config, "_model_quality_report_directory", None)
    if directory is not None:
        terminalreporter.write_sep("=", f"Informe de calidad: {directory}")
