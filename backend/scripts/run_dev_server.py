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

# concurrently conecta estos streams a pipes, que en Windows pueden heredar
# una codificación local. El lanzador de Node lee los logs como UTF-8.
if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

from main import app


if __name__ == "__main__":
    # Desarrollo local: no exponer la API a otras interfaces de red.
    # El contenedor conserva su propio bind en backend/Dockerfile.
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("DEV_BACKEND_PORT", "8000")),
                reload=False, log_level="info")
