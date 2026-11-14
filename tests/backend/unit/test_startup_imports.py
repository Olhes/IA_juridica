"""Keep optional ML providers off the backend import path."""
from pathlib import Path
import os
import subprocess
import sys


def test_importing_backend_does_not_load_optional_ml_packages():
    backend = Path(__file__).resolve().parents[3] / "backend"
    subprocess.run(
        [sys.executable, "-c",
         "import main, sys; "
         "assert not set(('torch', 'transformers', 'lightrag', 'pydantic_ai', "
         "'googletrans', 'deep_translator', 'docling')) & sys.modules.keys()"],
        env={**os.environ, "PYTHONPATH": str(backend), "RAG_ENGINE": "sat"},
        check=True, timeout=60,
    )
