"""Cliente y carga PDF simulados, compartidos por seguridad y evidencia."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import main
from config.settings import settings


def configured_client(monkeypatch, tmp_path):
    monkeypatch.setattr(main.limiter, "enabled", False)
    monkeypatch.setattr(settings, "ADMIN_ENDPOINTS_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key-with-enough-entropy")
    # Estas pruebas existentes cubren compatibilidad explícita con el legado.
    monkeypatch.setattr(settings, "SAT_INGESTION_LEGACY_RAG", True)
    monkeypatch.setattr(main, "RAW_PDFS_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    processor = SimpleNamespace(process_pdf=AsyncMock(return_value="# Processed\nArtículo único\n"))
    monkeypatch.setattr(main.app.state, "pdf_processor", processor, raising=False)
    monkeypatch.setattr(
        main.app.state,
        "rag_engine",
        SimpleNamespace(add_document=AsyncMock()),
        raising=False,
    )
    client = TestClient(main.app)
    client.post("/session/bootstrap")
    return client, processor


def upload(client, content=b"%PDF-1.7\nbody", filename="document.pdf", content_type="application/pdf", key="test-admin-key-with-enough-entropy"):
    return client.post(
        "/upload-pdf",
        headers={"X-API-Key": key},
        files={"file": (filename, content, content_type)},
    )
