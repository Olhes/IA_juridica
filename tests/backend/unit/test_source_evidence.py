import asyncio
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ingestion.pipeline import LegalIngestionPipeline
from ingestion.docling_processor import LegalPDFProcessor
from ingestion.source_evidence import persist_source_evidence


@pytest.mark.parametrize("replacement", ["", "\ufffd"])
def test_processing_validation_preserves_replacement_character_detection(replacement):
    """El escape Unicode conserva la detección sin rechazar español ni emojis válidos."""
    pipeline = object.__new__(LegalIngestionPipeline)
    content = "# Documento\n## 📋 Metadatos\n#### Artículo único\n" + "Contenido jurídico válido. " * 30
    result = pipeline._validate_processing(content + replacement)
    assert ("Caracteres de codificación detectados" in result["issues"]) == bool(replacement)
    assert result["confidence"] == pytest.approx(0.8 if replacement else 1.0)


def test_pipeline_source_has_valid_utf8_without_literal_replacement_character():
    """Sonar no debe confundir el detector de corrupción con un archivo mal codificado."""
    source = (Path(__file__).resolve().parents[3] / "backend" / "ingestion" / "pipeline.py").read_bytes()
    assert chr(0xfffd) not in source.decode("utf-8", errors="strict")


def test_evidence_retries_and_tampering(tmp_path):
    """Identical retries reuse evidence, while divergent or altered records fail closed."""
    pdf = tmp_path / "input.pdf"
    md = tmp_path / "input.md"
    pdf.write_bytes(b"%PDF-1.7\nsource")
    md.write_text("# Converted", encoding="utf-8")
    store = tmp_path / "evidence"
    first = persist_source_evidence(pdf, md, "# Converted", store)
    assert persist_source_evidence(pdf, md, "# Converted", store) == first
    assert dataclasses.asdict(first) == json.loads((store / f"{first.evidence_id}.json").read_text())
    assert first.provenance_state == "unverified"
    # Las clases de datos congeladas impiden reasignar atributos de esta instancia, pero no vuelven inmutables los registros en disco.
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.pdf_sha256 = "forged"
    md.write_text("# Different conversion", encoding="utf-8")
    # Una conversión diferente del mismo PDF no debe reemplazar el primer registro publicado.
    with pytest.raises(ValueError, match="collision"):
        persist_source_evidence(pdf, md, "# Different conversion", store)
    record = store / f"{first.evidence_id}.json"
    record.write_text('{"provenance_state":"verified"}')
    md.write_text("# Converted", encoding="utf-8")
    # Restaurar el Markdown coincidente para que este rechazo se deba únicamente al registro alterado deliberadamente.
    with pytest.raises(ValueError, match="tampered"):
        persist_source_evidence(pdf, md, "# Converted", store)
    assert list(store.glob(".evidence-*")) == []


def test_evidence_requires_written_matching_markdown(tmp_path):
    """Evidence is published only after matching converted Markdown exists on disk."""
    pdf = tmp_path / "input.pdf"
    md = tmp_path / "input.md"
    pdf.write_bytes(b"%PDF-1.7\nsource")
    store = tmp_path / "evidence"
    with pytest.raises(FileNotFoundError):
        persist_source_evidence(pdf, md, "# Converted", store)
    md.write_text("incomplete", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        persist_source_evidence(pdf, md, "# Converted", store)
    assert not store.exists()


def test_evidence_hashes_exact_multiline_utf8_bytes(tmp_path):
    """The Markdown digest covers its exact persisted UTF-8 bytes, including accents and newlines."""
    import hashlib

    pdf = tmp_path / "source.pdf"
    md = tmp_path / "source.md"
    content = "# Law\nArtículo único\n"
    pdf.write_bytes(b"%PDF-1.7\nsource")
    md.write_bytes(content.encode("utf-8"))
    record = persist_source_evidence(pdf, md, content, tmp_path / "evidence")
    assert record.markdown_sha256 == hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_batch_matches_upload_identity_and_keeps_legacy_result(tmp_path, monkeypatch):
    """Upload and batch ingestion share byte-based evidence identity and retain legacy RAG results."""
    from tests.backend.fixtures.uploads import configured_client, upload

    client, _ = configured_client(monkeypatch, tmp_path)
    uploaded = upload(client, filename="admin.pdf").json()
    rag = SimpleNamespace(add_document=AsyncMock(), rebuild_index=AsyncMock())
    processor = SimpleNamespace(process_pdf=AsyncMock(return_value="# Processed\nArtículo único\n"))
    pipeline = LegalIngestionPipeline(
        rag_engine=rag, pdf_processor=processor, evidence_store_dir=tmp_path / "source_evidence"
    )
    pipeline.raw_dir = tmp_path / "batch-raw"
    pipeline.processed_dir = tmp_path / "batch-processed"
    pipeline.failed_dir = tmp_path / "batch-failed"
    pdf = pipeline.raw_dir / "category" / "unrelated-name.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\nbody")
    result = asyncio.run(pipeline.process_all_pdfs())
    assert result["processed_count"] == 1 and result["failed_count"] == 0
    detail = result["details"][0]
    assert detail["evidence_id"] == uploaded["evidence_id"]
    assert detail["graph_write_state"] == "unverified"
    assert detail["status"] == "success"
    assert detail["processed_path"] == str(pipeline.processed_dir / "category" / "unrelated-name.md")
    rag.add_document.assert_awaited_once()
    rag.rebuild_index.assert_awaited_once()
    assert len(list((tmp_path / "source_evidence").glob("*.json"))) == 1


def test_batch_fails_closed_on_markdown_or_evidence_failure(tmp_path):
    """Los fallos simulados del sistema de archivos impiden escrituras en RAG y trasladan el PDF por lotes al almacenamiento de fallidos."""
    rag = SimpleNamespace(add_document=AsyncMock(), rebuild_index=AsyncMock())
    processor = SimpleNamespace(process_pdf=AsyncMock(return_value="# Processed"))
    pipeline = LegalIngestionPipeline(
        rag_engine=rag, pdf_processor=processor, evidence_store_dir=tmp_path / "evidence"
    )
    pipeline.raw_dir = tmp_path / "raw"
    pipeline.processed_dir = tmp_path / "processed"
    pipeline.failed_dir = tmp_path / "failed"
    pdf = pipeline.raw_dir / "case.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\ncase")
    # Un archivo en la ruta prevista para el directorio de procesados simula un fallo al escribir Markdown.
    pipeline.processed_dir.write_text("blocked")
    with pytest.raises(OSError):
        asyncio.run(pipeline.process_single_pdf(pdf))
    assert not (tmp_path / "evidence").exists()
    pipeline.processed_dir.unlink()
    # Tras permitir la salida Markdown, el mismo tipo de obstrucción simula un fallo al crear el almacén de evidencias.
    pipeline.evidence_store_dir.write_text("blocked")
    with pytest.raises(OSError):
        asyncio.run(pipeline.process_single_pdf(pdf))
    rag.add_document.assert_not_awaited()
    summary = asyncio.run(pipeline.process_all_pdfs())
    assert summary["processed_count"] == 0 and summary["failed_count"] == 1
    assert (pipeline.failed_dir / "case.pdf").exists()
    rag.rebuild_index.assert_not_awaited()


def test_batch_divergent_retry_preserves_existing_markdown_and_evidence(tmp_path):
    """A changed conversion on retry fails without replacing the first Markdown or evidence record."""
    rag = SimpleNamespace(add_document=AsyncMock(), rebuild_index=AsyncMock())
    processor = SimpleNamespace(process_pdf=AsyncMock(return_value="# First conversion"))
    pipeline = LegalIngestionPipeline(
        rag_engine=rag, pdf_processor=processor, evidence_store_dir=tmp_path / "evidence"
    )
    pipeline.raw_dir = tmp_path / "raw"
    pipeline.processed_dir = tmp_path / "processed"
    pipeline.failed_dir = tmp_path / "failed"
    pdf = pipeline.raw_dir / "case.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\ncase")

    first = asyncio.run(pipeline.process_all_pdfs())
    record = tmp_path / "evidence" / f"{first['details'][0]['evidence_id']}.json"
    saved_record = record.read_bytes()
    processor.process_pdf.return_value = "# Different conversion"

    retry = asyncio.run(pipeline.process_all_pdfs())

    assert retry["processed_count"] == 0 and retry["failed_count"] == 1
    assert (pipeline.failed_dir / "case.pdf").read_bytes() == b"%PDF-1.7\ncase"
    assert (pipeline.processed_dir / "case.md").read_bytes() == b"# First conversion"
    assert record.read_bytes() == saved_record
    rag.add_document.assert_awaited_once()
    rag.rebuild_index.assert_awaited_once()


def test_batch_retry_with_processor_output_alias_preserves_original(tmp_path):
    """A processor writing into the batch output directory cannot overwrite artifacts on divergent retry."""
    rag = SimpleNamespace(add_document=AsyncMock(), rebuild_index=AsyncMock())
    processor = LegalPDFProcessor.__new__(LegalPDFProcessor)
    pipeline = LegalIngestionPipeline(
        rag_engine=rag, pdf_processor=processor, evidence_store_dir=tmp_path / "evidence"
    )
    pipeline.raw_dir = tmp_path / "raw"
    pipeline.processed_dir = tmp_path / "processed"
    pipeline.failed_dir = tmp_path / "failed"
    pipeline.raw_dir.mkdir()
    pipeline.processed_dir.mkdir()
    # Probar el caso de alias: el directorio de salida del procesador también es el destino del lote.
    processor.output_dir = pipeline.processed_dir
    content = ["# Original conversion"]
    processor.converter = SimpleNamespace(
        convert=lambda _path: SimpleNamespace(
            document=SimpleNamespace(export_to_markdown=lambda: content[0])
        )
    )
    pdf = pipeline.raw_dir / "case.pdf"
    pdf.write_bytes(b"%PDF-1.7\ncase")

    first = asyncio.run(pipeline.process_all_pdfs())
    assert first["processed_count"] == 1
    markdown = pipeline.processed_dir / "case.md"
    original_bytes = markdown.read_bytes()
    record = pipeline.evidence_store_dir / f"{first['details'][0]['evidence_id']}.json"
    original_record = record.read_bytes()
    content[0] = "# Conflicting conversion"

    retry = asyncio.run(pipeline.process_all_pdfs())

    assert retry["processed_count"] == 0 and retry["failed_count"] == 1
    assert retry["details"][0]["status"] == "failed"
    assert "Existing Markdown differs" in retry["details"][0]["error"]
    assert (pipeline.failed_dir / "case.pdf").read_bytes() == b"%PDF-1.7\ncase"
    assert markdown.read_bytes() == original_bytes
    assert record.read_bytes() == original_record
    assert len(list(pipeline.evidence_store_dir.glob("*.json"))) == 1
    rag.add_document.assert_awaited_once()
    rag.rebuild_index.assert_awaited_once()


def test_standalone_processor_still_writes_output_by_default(tmp_path):
    """Direct processor use still returns converted Markdown and writes its default .md output."""
    processor = LegalPDFProcessor.__new__(LegalPDFProcessor)
    processor.output_dir = tmp_path
    processor.converter = SimpleNamespace(
        convert=lambda _path: SimpleNamespace(
            document=SimpleNamespace(export_to_markdown=lambda: "# Standalone")
        )
    )
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    assert asyncio.run(processor.process_pdf(str(pdf))) == "# Standalone"
    assert (tmp_path / "source.md").read_text(encoding="utf-8") == "# Standalone"
