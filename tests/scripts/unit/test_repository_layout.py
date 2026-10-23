"""La carpeta única y su catálogo no deben volver a dispersarse."""

import ast
import configparser
import os
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[3]
TESTS = ROOT / "tests"


def test_test_suites_are_confined_to_single_tree():
    """No permitir suites Python/Node/Playwright en código de producto o scripts."""
    misplaced = []
    for folder in (ROOT / "backend", ROOT / "frontend", ROOT / "scripts"):
        for directory, dirs, files in os.walk(folder):
            dirs[:] = [name for name in dirs if name not in {
                "node_modules", ".next", "__pycache__", ".pytest_cache", "docs",
                ".venv", "dist", "build",
            } and not name.startswith("docs_backup")]
            for name in files:
                if (name.startswith("test_") and name.endswith(".py")) or re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", name):
                    misplaced.append(str(Path(directory, name).relative_to(ROOT)))
    assert misplaced == [], misplaced
    # La separación primaria es el componente; el tipo viene después.
    for glob in ("test_*.py", "*.test.mjs", "*.test.mts", "*.test.ts", "*.test.tsx", "*.spec.js", "*.spec.ts"):
        for path in TESTS.rglob(glob):
            parts = path.relative_to(TESTS).parts
            assert len(parts) >= 3, path
            component, kind = parts[:2]
            assert component in {"backend", "frontend", "scripts"}, path
            assert kind in {"unit", "component", "integration", "security", "http", "contract", "bdd", "benchmark", "quality", "harness", "e2e"}, path
            if path.name.endswith(".test.mts"):
                assert component == "frontend", path
            if path.name.endswith(".test.mjs"):
                assert component == "scripts", path


def test_every_automated_case_is_catalogued_in_test_guide():
    """Cada archivo y nombre de caso debe constar en el documento dedicado."""
    guide = (TESTS / "README.md").read_text(encoding="utf-8")
    for path in sorted(TESTS.rglob("test_*.py")):
        assert path.relative_to(TESTS).as_posix() in guide
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                assert f"`{node.name}`" in guide, (path, node.name)
    for glob in ("*.test.mjs", "*.test.mts", "*.test.ts", "*.test.tsx", "*.spec.js", "*.spec.ts"):
        for path in sorted(TESTS.rglob(glob)):
            assert path.relative_to(TESTS).as_posix() in guide
            for match in re.finditer(r"^test\((['\"])(.*?)\1,", path.read_text(encoding="utf-8"), re.MULTILINE):
                assert match[2] in guide, (path, match[2])


def test_pytest_and_sonar_share_the_same_test_root():
    """Pytest y Sonar reconocen tests y no conservan una segunda configuración."""
    config = configparser.ConfigParser()
    config.read(ROOT / "pytest.ini", encoding="utf-8")
    assert config["pytest"]["testpaths"].split() == ["tests"]
    assert config["pytest"]["python_files"] == "test_*.py"
    assert not (ROOT / "backend/pytest.ini").exists()
    assert not (ROOT / "conftest.py").exists()
    sonar = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["sonar"]
    assert sonar["tests"] == "tests"
    assert sonar["sources"] == "backend,frontend/src,frontend/app"
    assert sonar["javascript"]["lcov"]["reportPaths"] == "temp/sonar-reports/frontend-coverage/lcov.info"
    assert "tests/backend/manual/**" in sonar["test"]["exclusions"]


def test_manual_diagnostics_and_quality_dataset_are_documented():
    """Inventariar scripts manuales y mantener datos sintéticos dentro de tests."""
    from evaluation.model_quality import DATASET, load_cases

    guide = (TESTS / "README.md").read_text(encoding="utf-8")
    for path in sorted((TESTS / "backend/manual").glob("*.py")):
        assert path.relative_to(TESTS).as_posix() in guide
        assert not path.name.startswith("test_")
    assert DATASET == TESTS / "backend/fixtures/quality_cases.json"
    assert load_cases()
