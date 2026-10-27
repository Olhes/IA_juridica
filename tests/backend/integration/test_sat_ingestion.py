"""El camino HTTP/batch publica SAT sin invocar APIs de pago por defecto."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import main
from config.settings import Settings, settings
from ingestion.pipeline import LegalIngestionPipeline
from ingestion.sat_graph.store import SATGraphStore
from ingestion.conversion import ConversionArtifact
from tests.backend.fixtures.uploads import configured_client, upload


def test_non_pdf_upload_stays_outside_sat_and_pdf_endpoint_rejects_it(monkeypatch, tmp_path):
    client, _ = configured_client(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SAT_INGESTION_LEGACY_RAG", False)
    processor = SimpleNamespace(process_document=AsyncMock(return_value="# Ficticio"))
    monkeypatch.setattr(main.app.state, "document_processor", processor, raising=False)
    header = {"X-API-Key": "test-admin-key-with-enough-entropy"}
    payload = {"file": ("ficticio.txt", b"texto ficticio", "text/plain")}
    result = client.post("/upload-document", headers=header, files=payload)
    assert result.status_code == 200
    assert result.json()["evidence_id"] is None and result.json()["sat_graph"] is None
    assert not (tmp_path / "sat_graph.sqlite3").exists()
    main.app.state.rag_engine.add_document.assert_awaited_once()
    assert client.post("/upload-pdf", headers=header, files=payload).status_code == 400


def test_sat_upload_and_batch_share_commit_and_skip_legacy_llm(monkeypatch, tmp_path):
    client, processor = configured_client(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SAT_INGESTION_LEGACY_RAG", False)
    uploaded = upload(client).json()
    assert uploaded["sat_graph"]["write_state"] == "committed"
    assert uploaded["graph_write_state"] == "pending_review"
    main.app.state.rag_engine.add_document.assert_not_awaited()
    rag = SimpleNamespace(add_document=AsyncMock(), rebuild_index=AsyncMock())
    pipeline = LegalIngestionPipeline(
        rag_engine=rag,
        pdf_processor=processor,
        evidence_store_dir=tmp_path / "source_evidence",
        docs_root=tmp_path / "batch",
    )
    pdf = pipeline.raw_dir / "same.pdf"
    pdf.write_bytes(b"%PDF-1.7\nbody")
    result = asyncio.run(pipeline.process_all_pdfs())
    assert result["failed_count"] == 0
    assert result["details"][0]["sat_graph"] == uploaded["sat_graph"]
    rag.add_document.assert_not_awaited()
    rag.rebuild_index.assert_not_awaited()
    graph = SATGraphStore(tmp_path / "sat_graph.sqlite3").export()
    assert len(graph["documents"]) == 1
    assert graph["reviewed_version_count"] == 0
    assert Settings.model_fields["SAT_INGESTION_LEGACY_RAG"].default is False


def test_sat_upload_failure_keeps_published_evidence_for_recovery(
    monkeypatch, tmp_path
):
    client, _ = configured_client(monkeypatch, tmp_path)

    def fail(*_):
        raise OSError("database unavailable; private details")

    monkeypatch.setattr(main, "stage_document", fail)
    response = upload(client)
    assert response.status_code == 500
    assert "private details" not in response.text
    assert len(list((tmp_path / "raw").glob("*.pdf"))) == 1
    assert len(list((tmp_path / "processed").glob("*.md"))) == 1
    assert len(list((tmp_path / "source_evidence").glob("*.json"))) == 1
    main.app.state.rag_engine.add_document.assert_not_awaited()


def test_sat_admin_graph_export_and_temporal_abstention(monkeypatch, tmp_path):
    client, _ = configured_client(monkeypatch, tmp_path)
    header = {"X-API-Key": "test-admin-key-with-enough-entropy"}
    assert client.get("/knowledge-graph?engine=sat").status_code == 403
    graph = client.get("/knowledge-graph?engine=sat", headers=header)
    assert graph.status_code == 200
    assert graph.json()["graph"]["resource_count"] >= 21
    query = {"resource_id": "pe:ley:30364", "component": "art-1", "as_of": "2026-10-07"}
    assert client.get("/sat-graph/resolve", params=query).status_code == 403
    assert (
        client.get("/sat-graph/resolve", params=query, headers=header).json()["state"]
        == "abstain"
    )
    query["as_of"] = "bad-date"
    assert (
        client.get("/sat-graph/resolve", params=query, headers=header).status_code
        == 422
    )
    assert (
        client.get("/knowledge-graph?engine=unknown", headers=header).status_code == 422
    )


def test_sat_batch_storage_failure_never_acknowledges_success(monkeypatch, tmp_path):
    rag = SimpleNamespace(add_document=AsyncMock(), rebuild_index=AsyncMock())
    processor = SimpleNamespace(
        process_pdf=AsyncMock(return_value="Artículo único. Ficticio")
    )
    pipeline = LegalIngestionPipeline(
        rag_engine=rag,
        pdf_processor=processor,
        evidence_store_dir=tmp_path / "source_evidence",
        docs_root=tmp_path / "batch",
        legacy_rag_write=False,
    )
    pdf = pipeline.raw_dir / "case.pdf"
    pdf.write_bytes(b"%PDF-1.7\nbody")
    pipeline.sat_graph_path.mkdir()
    result = asyncio.run(pipeline.process_all_pdfs())
    assert result["processed_count"] == 0 and result["failed_count"] == 1
    assert (pipeline.failed_dir / "case.pdf").exists()
    assert (pipeline.processed_dir / "case.md").exists()
    rag.add_document.assert_not_awaited()
    rag.rebuild_index.assert_not_awaited()


def test_sat_upload_and_batch_preserve_same_docling_artifact(monkeypatch, tmp_path):
    client, _ = configured_client(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SAT_INGESTION_LEGACY_RAG", False)
    layout = {
        "texts": [{"text": "Ficticio", "prov": [{"page_no": 1, "charspan": [0, 8]}]}]
    }

    class ArtifactProcessor:
        async def process_pdf_artifact(self, _):
            return ConversionArtifact("Artículo 1.- Ficticio", layout)

        async def process_pdf(self, *_args, **_kwargs):
            raise AssertionError("No debe haber segunda conversión")

    processor = ArtifactProcessor()
    monkeypatch.setattr(main.app.state, "pdf_processor", processor)
    response = upload(client)
    assert response.status_code == 200
    uploaded = response.json()
    store = SATGraphStore(tmp_path / "sat_graph.sqlite3")
    saved = store.structure(uploaded["evidence_id"])
    assert saved["docling_document"] == layout
    pipeline = LegalIngestionPipeline(
        rag_engine=SimpleNamespace(add_document=AsyncMock(), rebuild_index=AsyncMock()),
        pdf_processor=processor,
        evidence_store_dir=tmp_path / "source_evidence",
        docs_root=tmp_path / "batch",
        legacy_rag_write=False,
    )
    pdf = pipeline.raw_dir / "same.pdf"
    pdf.write_bytes(b"%PDF-1.7\nbody")
    result = asyncio.run(pipeline.process_single_pdf(pdf))
    assert result["sat_graph"]["parse_id"] == uploaded["sat_graph"]["parse_id"]
    assert store.structure(uploaded["evidence_id"]) == saved
    main.app.state.rag_engine.add_document.assert_not_awaited()
    pipeline.rag_engine.add_document.assert_not_awaited()


def test_sat_structure_http_requires_admin_and_explicit_ambiguous_parse(
    monkeypatch, tmp_path
):
    client, _ = configured_client(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SAT_INGESTION_LEGACY_RAG", False)
    uploaded = upload(client).json()
    query = {"evidence_id": uploaded["evidence_id"]}
    header = {"X-API-Key": "test-admin-key-with-enough-entropy"}
    assert client.get("/sat-graph/structure", params=query).status_code == 403
    response = client.get("/sat-graph/structure", params=query, headers=header)
    assert (
        response.status_code == 200 and response.json()["structure"]["review_required"]
    )
    store = SATGraphStore(tmp_path / "sat_graph.sqlite3")
    # Un parse nuevo sin modificar evidencia original requiere elección explícita.
    from ingestion.source_evidence import persist_source_evidence

    pdf = next((tmp_path / "raw").glob("*.pdf"))
    md = next((tmp_path / "processed").glob("*.md"))
    text = md.read_text(encoding="utf-8")
    evidence = persist_source_evidence(pdf, md, text, tmp_path / "source_evidence")
    other = store.stage(evidence, text, {"texts": []})
    assert (
        client.get("/sat-graph/structure", params=query, headers=header).status_code
        == 422
    )
    query["parse_id"] = other["parse_id"]
    assert (
        client.get("/sat-graph/structure", params=query, headers=header).status_code
        == 200
    )
    query["parse_id"] = "wrong"
    assert (
        client.get("/sat-graph/structure", params=query, headers=header).status_code
        == 422
    )
    monkeypatch.setattr(settings, "ADMIN_ENDPOINTS_ENABLED", False)
    assert (
        client.get("/sat-graph/structure", params=query, headers=header).status_code
        == 404
    )
