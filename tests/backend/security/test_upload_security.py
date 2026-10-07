import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import main
from config.settings import settings
from ingestion.docling_processor import LegalPDFProcessor
from ingestion.source_evidence import persist_source_evidence
from tests.backend.fixtures.uploads import configured_client, upload


def test_admin_endpoints_disabled_without_key(monkeypatch, tmp_path):
    """Disabled admin configuration keeps upload unavailable when no API key is configured."""
    monkeypatch.setattr(settings, "ADMIN_ENDPOINTS_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", None)
    client = TestClient(main.app)
    client.post("/session/bootstrap")
    assert upload(client).status_code == 404


def test_upload_generates_confined_name_and_preserves_sanitized_metadata(monkeypatch, tmp_path):
    """Uploads use a confined generated disk name while returning only a sanitized client filename."""
    client, _ = configured_client(monkeypatch, tmp_path)
    response = upload(client, filename="../../private.pdf")
    assert response.status_code == 200
    payload = response.json()
    assert payload["original_filename"] == "private.pdf"
    assert payload["filename"] != "private.pdf"
    assert Path(payload["filename"]).suffix == ".pdf"
    assert len(list((tmp_path / "raw").glob("*.pdf"))) == 1
    assert not (tmp_path / "private.pdf").exists()
    assert payload["graph_write_state"] == "unverified"
    assert len(list((tmp_path / "source_evidence").glob("*.json"))) == 1


def test_upload_rejects_size_mime_magic_and_wrong_admin_key(monkeypatch, tmp_path):
    """Size, media type, PDF signature, and admin-key checks reject uploads before evidence is stored."""
    client, _ = configured_client(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 8)
    assert upload(client, content=b"%PDF-123456").status_code == 413
    assert upload(client, content_type="text/plain").status_code == 400
    assert upload(client, content=b"not-pdf").status_code == 400
    assert upload(client, key="wrong").status_code == 403
    assert list((tmp_path / "raw").glob("*")) == []
    assert list((tmp_path / "source_evidence").glob("*.json")) == []


def test_upload_cleans_up_when_processing_fails(monkeypatch, tmp_path):
    """A simulated processor exception returns a safe error and removes uncommitted upload artifacts."""
    client, processor = configured_client(monkeypatch, tmp_path)
    processor.process_pdf.side_effect = RuntimeError("processor internals")
    response = upload(client)
    assert response.status_code == 500
    assert "processor internals" not in response.text
    assert list((tmp_path / "raw").glob("*")) == []
    assert list((tmp_path / "source_evidence").glob("*.json")) == []


def test_upload_reuses_evidence_by_pdf_bytes_not_filename(monkeypatch, tmp_path):
    """Evidence identity follows PDF bytes rather than the user-supplied filename."""
    client, _ = configured_client(monkeypatch, tmp_path)
    first = upload(client, filename="first.pdf").json()
    second = upload(client, filename="second.pdf").json()
    changed = upload(client, content=b"%PDF-1.7\nchanged").json()
    assert first["evidence_id"] == second["evidence_id"]
    assert changed["evidence_id"] != first["evidence_id"]
    assert len(list((tmp_path / "source_evidence").glob("*.json"))) == 2


def test_upload_fails_closed_when_evidence_store_is_unwritable(monkeypatch, tmp_path):
    """An unusable evidence-store path prevents both retained artifacts and the RAG write."""
    client, _ = configured_client(monkeypatch, tmp_path)
    (tmp_path / "source_evidence").write_text("not a directory")
    response = upload(client)
    assert response.status_code == 500
    assert list((tmp_path / "raw").glob("*")) == []
    assert list((tmp_path / "processed").glob("*")) == []
    main.app.state.rag_engine.add_document.assert_not_awaited()


def test_upload_collision_preserves_existing_markdown_and_evidence(monkeypatch, tmp_path):
    """A forced output-name collision with different conversion preserves the earlier artifacts."""
    client, _ = configured_client(monkeypatch, tmp_path)
    # Hacer que la nueva carga apunte de forma determinista a la ruta Markdown existente.
    monkeypatch.setattr(main.uuid, "uuid4", lambda: SimpleNamespace(hex="collision"))
    processed = tmp_path / "processed"
    processed.mkdir()
    existing = processed / "collision.md"
    existing.write_text("# Existing conversion", encoding="utf-8")
    prior_pdf = tmp_path / "prior.pdf"
    prior_pdf.write_bytes(b"%PDF-1.7\nbody")
    evidence = persist_source_evidence(
        prior_pdf, existing, "# Existing conversion", tmp_path / "source_evidence"
    )
    record = tmp_path / "source_evidence" / f"{evidence.evidence_id}.json"
    saved_record = record.read_bytes()

    processor = LegalPDFProcessor.__new__(LegalPDFProcessor)
    processor.output_dir = processed
    # Este convertidor en memoria devuelve texto en conflicto sin invocar Docling real.
    processor.converter = SimpleNamespace(
        convert=lambda _path: SimpleNamespace(
            document=SimpleNamespace(export_to_markdown=lambda: "# Different conversion")
        )
    )
    monkeypatch.setattr(main.app.state, "pdf_processor", processor)

    response = upload(client)

    assert response.status_code == 500
    assert response.json()["detail"] == "PDF processing failed"
    assert existing.read_text(encoding="utf-8") == "# Existing conversion"
    assert record.read_bytes() == saved_record
    assert list((tmp_path / "raw").glob("*")) == []
    main.app.state.rag_engine.add_document.assert_not_awaited()
