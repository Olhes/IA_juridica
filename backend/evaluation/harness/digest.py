"""Huella del código de prompts y pipeline, idéntica a la de ``optimization.query_cache.pipeline_digest``.

El harness la calcula por su cuenta para poder medir commits antiguos que aún no tienen esa función:
si ambas divergen, ``test_digest_matches_the_cache_key_digest`` falla.
"""

import hashlib
from pathlib import Path

DIRECTORIES = ("services", "context", "agents", "modules/validation", "modules/language", "modules/rag")


def pipeline_digest(backend_root=None) -> str:
    root = Path(backend_root) if backend_root else Path(__file__).resolve().parents[2]
    files = sorted(p for directory in DIRECTORIES for p in (root / directory).rglob("*.py"))
    return hashlib.sha256(b"".join(p.read_bytes() for p in files)).hexdigest()
