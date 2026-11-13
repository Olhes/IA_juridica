"""Validación local del conjunto de casos de calidad."""

import json
from types import SimpleNamespace

import pytest

from evaluation.model_quality import load_cases

pytestmark = pytest.mark.quality


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


