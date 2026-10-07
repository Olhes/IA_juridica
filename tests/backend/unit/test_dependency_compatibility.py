"""Real synthetic PDF parser smoke test: no model downloads or remote APIs."""

from pathlib import Path


def test_updated_pdf_stack_extracts_synthetic_source(tmp_path):
    from reportlab.pdfgen.canvas import Canvas
    from pypdf import PdfReader
    from docling.datamodel.base_models import InputFormat, BoundingBox
    from docling.datamodel.document import InputDocument
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling_core.types.doc import DoclingDocument

    pdf = tmp_path / "synthetic.pdf"
    canvas = Canvas(str(pdf))
    canvas.drawString(
        40, 750, "SYNTHETIC SOURCE: municipal license fee is twenty units."
    )
    canvas.save()
    assert "SYNTHETIC SOURCE" in PdfReader(pdf).pages[0].extract_text()
    document = InputDocument(
        path_or_stream=pdf, format=InputFormat.PDF, backend=PyPdfiumDocumentBackend
    )
    backend = document._backend
    assert backend.is_valid() and backend.page_count() == 1
    page = backend.load_page(0)
    size = page.get_size()
    text = page.get_text_in_rect(BoundingBox(l=0, t=0, r=size.width, b=size.height))
    assert "SYNTHETIC SOURCE" in text
    exported = DoclingDocument(name="synthetic")
    exported.add_text(label="text", text=text)
    assert "municipal license" in exported.export_to_markdown()
    page.unload()
    backend.unload()
