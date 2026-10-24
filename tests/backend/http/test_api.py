from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import json
import sys
import pytest


def test_api_version_metadata_uses_single_configured_identity(api):
    client, main, _ = api
    version = main.settings.APP_VERSION
    assert f"API {version} -" in client.get("/").json()["message"]
    assert client.get("/health").json()["version"] == version
    assert main.app.openapi()["info"]["version"] == version


def test_bootstrap_and_protected_query_gate(api):
    client, main, _ = api
    assert client.post("/legal-query", json={"query": "licencia"}).status_code == 401
    response = client.post("/session/bootstrap")
    assert response.status_code == 200
    assert response.json()["principal_id"]
    assert "httponly" in response.headers["set-cookie"].lower()


def test_cached_query_does_not_call_external_dependencies(api):
    client, main, optimizer = api
    optimizer.get_cached.return_value = {
        "response": {"respuesta_espanol": "Respuesta local"},
        "sources": ["licencia.md"],
        "validation": {"is_reliable": True},
    }
    client.post("/session/bootstrap")
    response = client.post("/legal-query", json={"query": "  licencia  "})
    assert response.status_code == 200
    assert response.json()["cached"] is True
    assert response.json()["query"] == "licencia"
    main.app.state.rag_engine.query_with_rerank.assert_not_awaited()


@pytest.mark.parametrize(
    "unavailable, status_code, detail",
    [
        (False, 500, "PDF generation failed"),
        (True, 503, "PDF generation unavailable"),
    ],
)
def test_pdf_report_preserves_documented_errors(
    api, monkeypatch, unavailable, status_code, detail
):
    client, _, _ = api
    generator = Mock(side_effect=RuntimeError("internal generator error"))
    monkeypatch.setitem(
        sys.modules,
        "utils.pdf_generator",
        None if unavailable else SimpleNamespace(generate_legal_pdf_bytes=generator),
    )
    client.post("/session/bootstrap")
    response = client.post(
        "/generate-pdf-report", json={"query": "licencia", "response": {}}
    )
    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def test_pdf_report_preserves_successful_download(api, monkeypatch):
    client, _, _ = api
    pdf_bytes = b"%PDF-1.4\nsynthetic-report"
    generator = Mock(return_value=pdf_bytes)
    monkeypatch.setitem(
        sys.modules,
        "utils.pdf_generator",
        SimpleNamespace(generate_legal_pdf_bytes=generator),
    )
    client.post("/session/bootstrap")
    response = client.post(
        "/generate-pdf-report", json={"query": "licencia", "response": {}}
    )
    assert response.status_code == 200
    assert response.content == pdf_bytes
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="reporte_legal.pdf"'
    )
    assert response.headers["cache-control"] == "no-store"
    generator.assert_called_once_with(query="licencia", response_data={})


def test_admin_gate_precedes_document_access(api):
    client, main, _ = api
    main.app.state.rag_engine.list_documents = AsyncMock(return_value=[])
    assert client.get("/documents").status_code == 403
    assert client.get("/documents", headers={"X-API-Key": "wrong"}).status_code == 403
    assert client.get(
        "/documents", headers={"X-API-Key": "offline-admin-key"}
    ).json() == {"success": True, "documents": []}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"query": ""},
        {"query": "a" * 8001},
        {"query": "licencia", "effective_date": "2024-01-01"},
    ],
)
def test_legal_query_rejects_invalid_input_before_retrieval(api, payload):
    client, main, optimizer = api
    client.post("/session/bootstrap")
    assert client.post("/legal-query", json=payload).status_code == 422
    optimizer.get_cached.assert_not_called()
    main.app.state.rag_engine.query_with_rerank.assert_not_awaited()


def test_cached_stream_emits_chunk_then_final_without_external_calls(api, monkeypatch):
    from modules.language.services.language_detector import LanguageDetector

    client, main, optimizer = api
    # Evitar las integraciones de detección y traducción de idioma: probar solo la rama en español con caché.
    monkeypatch.setattr(LanguageDetector, "detect_language", lambda self, text: "es")
    optimizer.get_cached.return_value = {
        "response": {"respuesta_espanol": "Artículo local"},
        "sources": ["licencia.md"],
        "validation": {"is_reliable": True},
    }
    client.post("/session/bootstrap")
    response = client.post(
        "/legal-query-stream", json={"query": "licencia", "language": "spanish"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [e["type"] for e in events] == ["meta", "chunk", "final", "done"]
    assert [e["seq"] for e in events] == [0, 1, 2, 3]
    assert {e["v"] for e in events} == {1}
    assert len({e["request_id"] for e in events}) == 1
    assert events[1]["delta"] == "Artículo local"
    final = events[2]["data"]
    assert final["metadata"]["timings"]["cache_hit"] is True
    del final["metadata"]
    assert final == {
        "success": True,
        "query": "licencia",
        "language": "spanish",
        "cached": True,
        "response": {"respuesta_espanol": "Artículo local"},
        "sources": ["licencia.md"],
        "validation": {"is_reliable": True},
    }
    main.app.state.rag_engine.query_with_rerank.assert_not_awaited()
