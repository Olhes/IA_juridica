"""Identidad compartida de la implementación de respuestas y su evaluación."""

from hashlib import sha256
from pathlib import Path


_DIRECTORIES = (
    "services", "context", "agents", "retrieval", "ingestion", "utils",
    "models", "config", "database", "optimization",
    "modules/chat", "modules/validation", "modules/language", "modules/rag",
)


def pipeline_digest(backend_root=None) -> str:
    """Identifica rutas y bytes del código, sin depender del path del checkout."""
    root = Path(backend_root) if backend_root else Path(__file__).resolve().parents[1]
    files = [p for directory in _DIRECTORIES for p in (root / directory).rglob("*.py")]
    if (root / "main.py").is_file():
        files.append(root / "main.py")
    fingerprint = sha256()
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        fingerprint.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        fingerprint.update(sha256(path.read_bytes()).digest())
    return fingerprint.hexdigest()
