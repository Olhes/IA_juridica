import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import main
from config.settings import settings


def configured_client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADMIN_ENDPOINTS_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key-with-enough-entropy")
    monkeypatch.setattr(main, "RAW_PDFS_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    processor = SimpleNamespace(process_pdf=AsyncMock(return_value="# Processed"))
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


def test_admin_endpoints_disabled_without_key(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADMIN_ENDPOINTS_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", None)
    client = TestClient(main.app)
    client.post("/session/bootstrap")
    assert upload(client).status_code == 404


def test_upload_generates_confined_name_and_preserves_sanitized_metadata(monkeypatch, tmp_path):
    client, _ = configured_client(monkeypatch, tmp_path)
    response = upload(client, filename="../../private.pdf")
    assert response.status_code == 200
    payload = response.json()
    assert payload["original_filename"] == "private.pdf"
    assert payload["filename"] != "private.pdf"
    assert Path(payload["filename"]).suffix == ".pdf"
    assert len(list((tmp_path / "raw").glob("*.pdf"))) == 1
    assert not (tmp_path / "private.pdf").exists()


def test_upload_rejects_size_mime_magic_and_wrong_admin_key(monkeypatch, tmp_path):
    client, _ = configured_client(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 8)
    assert upload(client, content=b"%PDF-123456").status_code == 413
    assert upload(client, content_type="text/plain").status_code == 400
    assert upload(client, content=b"not-pdf").status_code == 400
    assert upload(client, key="wrong").status_code == 403
    assert list((tmp_path / "raw").glob("*")) == []


def test_upload_cleans_up_when_processing_fails(monkeypatch, tmp_path):
    client, processor = configured_client(monkeypatch, tmp_path)
    processor.process_pdf.side_effect = RuntimeError("processor internals")
    response = upload(client)
    assert response.status_code == 500
    assert "processor internals" not in response.text
    assert list((tmp_path / "raw").glob("*")) == []
