"""El launcher local usa loopback sin cambiar el entrypoint del contenedor."""

import json
from pathlib import Path
import runpy
import sys
from types import ModuleType
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend" / "scripts" / "run_dev_server.py"


@pytest.mark.parametrize("run_name", ["__main__", "dev_server_import"])
def test_local_launcher_binding_and_import_guard(monkeypatch, run_name):
    uvicorn = ModuleType("uvicorn")
    uvicorn.run = Mock()
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = Mock()
    monkeypatch.delenv("DEV_BACKEND_RELOAD", raising=False)
    monkeypatch.delenv("DEV_BACKEND_PORT", raising=False)
    monkeypatch.setitem(sys.modules, "uvicorn", uvicorn)
    monkeypatch.setitem(sys.modules, "dotenv", dotenv)
    monkeypatch.setattr(sys, "path", sys.path.copy())

    runpy.run_path(str(SCRIPT), run_name=run_name)

    dotenv.load_dotenv.assert_called_once_with(ROOT / "backend" / ".env")
    if run_name == "__main__":
        uvicorn.run.assert_called_once()
        args, kwargs = uvicorn.run.call_args
        assert args == ("main:app",)
        assert kwargs["app_dir"] == str(ROOT / "backend")
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8000
        assert kwargs["reload"] is True
        assert kwargs["reload_dirs"] == [str(ROOT / "backend")]
        assert kwargs["reload_includes"] == ["*.py"]
        assert "logs/*" in kwargs["reload_excludes"]
        assert kwargs["log_level"] == "info"
    else:
        uvicorn.run.assert_not_called()


def test_local_launcher_allows_disabling_reload(monkeypatch):
    uvicorn = ModuleType("uvicorn")
    uvicorn.run = Mock()
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = Mock()
    monkeypatch.setenv("DEV_BACKEND_RELOAD", "0")
    monkeypatch.delenv("DEV_BACKEND_PORT", raising=False)
    monkeypatch.setitem(sys.modules, "uvicorn", uvicorn)
    monkeypatch.setitem(sys.modules, "dotenv", dotenv)
    monkeypatch.setattr(sys, "path", sys.path.copy())

    runpy.run_path(str(SCRIPT), run_name="__main__")

    uvicorn.run.assert_called_once_with(
        "main:app",
        app_dir=str(ROOT / "backend"),
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )


def test_container_entrypoint_keeps_container_network_binding():
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    command = next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD "))
    args = json.loads(command)

    assert args[args.index("--host") + 1] == "0.0.0.0"
    assert args[args.index("--port") + 1] == "8000"
