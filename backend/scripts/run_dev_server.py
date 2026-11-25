#!/usr/bin/env python
from pathlib import Path
import os
import sys

import uvicorn
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

RELOAD_EXCLUDES = [
    "logs/*",
    "temp/*",
    "rag_storage/*",
    "data/*",
    "cache/*",
    ".pytest_cache/*",
    ".deepeval/*",
]


def _reload_enabled() -> bool:
    raw = os.environ.get("DEV_BACKEND_RELOAD", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def main() -> None:
    # concurrently conecta estos streams a pipes, que en Windows pueden heredar
    # una codificación local. El lanzador de Node lee los logs como UTF-8.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

    reload_enabled = _reload_enabled()
    options = {
        "app_dir": str(BACKEND_DIR),
        "host": "127.0.0.1",
        "port": int(os.environ.get("DEV_BACKEND_PORT", "8000")),
        "reload": reload_enabled,
        "log_level": "info",
    }
    if reload_enabled:
        options.update(
            reload_dirs=[str(BACKEND_DIR)],
            reload_includes=["*.py"],
            reload_excludes=RELOAD_EXCLUDES,
        )

    # Desarrollo local: no exponer la API a otras interfaces de red.
    # El contenedor conserva su propio bind en backend/Dockerfile.
    uvicorn.run("main:app", **options)


if __name__ == "__main__":
    main()
