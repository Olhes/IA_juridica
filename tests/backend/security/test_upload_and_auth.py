import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _upload(
    client,
    name="legal.pdf",
    content=b"%PDF-1.7\nmock",
    mime="application/pdf",
    key="offline-admin-key",
):
    return client.post(
        "/upload-pdf", headers={"X-API-Key": key}, files={"file": (name, content, mime)}
    )


def test_upload_requires_admin_even_with_session(api):
    client, _, _ = api
    client.post("/session/bootstrap")
    assert _upload(client, key="wrong").status_code == 403


@pytest.mark.parametrize(
    "name,content,mime,expected",
    [
        ("legal.txt", b"%PDF-1.7\nmock", "application/pdf", 400),
        ("legal.pdf", b"not pdf", "application/pdf", 400),
        ("legal.pdf", b"%PDF-1.7\nmock", "text/plain", 400),
        ("legal.pdf", b"", "application/pdf", 400),
    ],
)
def test_invalid_upload_is_rejected_and_cleaned(
    api, monkeypatch, tmp_path, name, content, mime, expected
):
    client, main, _ = api
    monkeypatch.setattr(main, "RAW_PDFS_DIR", tmp_path / "raw")
    assert _upload(client, name, content, mime).status_code == expected
    assert list((tmp_path / "raw").glob("*")) == []


def test_upload_is_confined_and_passes_sanitized_metadata(api, monkeypatch, tmp_path):
    from config.settings import settings

    monkeypatch.setattr(settings, "SAT_INGESTION_LEGACY_RAG", True)
    client, main, _ = api
    monkeypatch.setattr(main, "RAW_PDFS_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(
        main.app.state,
        "pdf_processor",
        SimpleNamespace(process_pdf=AsyncMock(return_value="# Legal")),
        raising=False,
    )
    main.app.state.rag_engine.add_document = AsyncMock()
    response = _upload(client, name="../../private.pdf")
    assert response.status_code == 200
    data = response.json()
    assert data["original_filename"] == "private.pdf"
    assert re.fullmatch(r"[0-9a-f]{32}\.pdf", data["filename"])
    assert list((tmp_path / "raw").glob("*.pdf"))
    assert not (tmp_path / "private.pdf").exists()
    assert (
        main.app.state.rag_engine.add_document.await_args.args[1]["original_filename"]
        == "private.pdf"
    )


def test_oversized_upload_is_rejected_without_retaining_bytes(
    api, monkeypatch, tmp_path
):
    from config.settings import settings

    client, main, _ = api
    monkeypatch.setattr(main, "RAW_PDFS_DIR", tmp_path / "raw")
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 8)
    assert _upload(client, content=b"%PDF-1.7\nbody").status_code == 413
    assert list((tmp_path / "raw").glob("*")) == []


def test_pdf_size_exact_boundary_is_accepted_but_one_byte_more_is_not(
    api, monkeypatch, tmp_path
):
    from config.settings import settings

    monkeypatch.setattr(settings, "SAT_INGESTION_LEGACY_RAG", True)
    client, main, _ = api
    monkeypatch.setattr(main, "RAW_PDFS_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(
        main.app.state,
        "pdf_processor",
        SimpleNamespace(process_pdf=AsyncMock(return_value="# Legal")),
        raising=False,
    )
    main.app.state.rag_engine.add_document = AsyncMock()
    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 10)
    assert _upload(client, content=b"%PDF-1.7\nX").status_code == 200
    assert _upload(client, content=b"%PDF-1.7\nXY").status_code == 413
    assert len(list((tmp_path / "raw").glob("*.pdf"))) == 1
    main.app.state.rag_engine.add_document.assert_awaited_once()


def test_tampered_session_cookie_cannot_access_protected_query(api):
    from config.settings import settings

    client, _, optimizer = api
    client.post("/session/bootstrap")
    original = client.cookies.get(settings.ANONYMOUS_SESSION_COOKIE_NAME)
    assert original
    client.cookies.set(
        settings.ANONYMOUS_SESSION_COOKIE_NAME,
        ("A" if original[0] != "A" else "B") + original[1:],
    )
    assert client.post("/legal-query", json={"query": "licencia"}).status_code == 401
    optimizer.get_cached.assert_not_called()


def test_anonymous_chat_history_must_require_session(api):
    client, _, _ = api
    assert client.get("/chat/conversations/arbitrary-id").status_code == 401


def test_anonymous_stream_must_require_session(api):
    client, _, optimizer = api
    optimizer.get_cached.return_value = {
        "response": {"respuesta_espanol": "Respuesta local"}
    }
    assert (
        client.post(
            "/legal-query-stream", json={"query": "licencia municipal"}
        ).status_code
        == 401
    )
