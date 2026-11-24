"""PDFs reales sobre contenido sintético, sin proveedores ni datos jurídicos reales."""

import io

import pytest
from pypdf import PdfReader
from reportlab.platypus import HRFlowable, Paragraph, Preformatted, Table

from utils import pdf_generator as pdf


def extract(data):
    reader = PdfReader(io.BytesIO(data))
    assert reader.pages
    return "\n".join(page.extract_text() for page in reader.pages)


@pytest.mark.parametrize("nested", [False, True])
def test_real_pdf_preserves_bilingual_content_and_report_sections(nested):
    response = {
        "respuesta_espanol": "Respuesta sintética **validada**.",
        "respuesta_quechua": "Texto quechua sintético.",
        "pasos_recomendados": [
            {
                "paso": 1,
                "descripcion": "Paso de prueba",
                "documentos_requeridos": ["Ficha sintética"],
            },
            "ignorado",
        ],
        "recursos": [
            {
                "nombre": "Recurso sintético",
                "contacto": "Contacto de prueba",
                "descripcion": "Descripción del recurso",
            },
            {},
        ],
        "advertencias": [{"mensaje": "Advertencia sintética"}, None],
        "fuentes_legales": [
            {"nombre": "Fuente sintética", "tipo": "Documento", "numero": "TEST-1"},
            {},
        ],
    }
    payload = (
        {
            "response": response,
            "metadata": {"enriched_context": {"legal_topic": "prueba"}},
        }
        if nested
        else response
    )
    data = pdf.generate_legal_pdf_bytes("Consulta sintética", payload)
    assert data.startswith(b"%PDF-")
    output = extract(data)
    for expected in (
        "Consulta sintética",
        "Respuesta sintética validada",
        "Texto quechua sintético",
        "Paso de prueba",
        "Ficha sintética",
        "Recurso sintético",
        "Advertencia sintética",
        "Fuente sintética",
        "TEST-1",
        "AVISO",
    ):
        assert expected in output
    if nested:
        assert "Tema identificado: prueba" in output
    assert "**" not in output
    assert response.get("tema") is None  # La normalización no modifica el payload.


def test_pdf_markdown_renders_structural_blocks_and_escapes_markup():
    markdown = """# Título sintético

Texto **fuerte**, *énfasis*, ~~tachado~~ y `x < y`.

> Cita sintética
> Segunda línea

1) Elemento
  continuación
  - Sublista

---

| Campo | Valor |
| :--- | ---: |
| A | B | extra |

```python
print('sintético')
```

[Enlace](https://example.invalid) ![Imagen](https://example.invalid/image)
"""
    flowables = pdf._markdown_to_flowables(markdown, pdf._build_styles())
    assert any(isinstance(item, Table) for item in flowables)
    assert any(isinstance(item, Preformatted) for item in flowables)
    assert any(isinstance(item, HRFlowable) for item in flowables)
    assert any(
        isinstance(item, Paragraph) and item.getPlainText() == "Título sintético"
        for item in flowables
    )
    output = extract(
        pdf.generate_legal_pdf_bytes("Sintético", {"respuesta_espanol": markdown})
    )
    for expected in (
        "Título sintético",
        "Cita sintética",
        "continuación",
        "Campo",
        "print('sintético')",
        "x < y",
        "Imagen",
    ):
        assert expected in output
    assert "&lt;script&gt;" in pdf._format_inline_markdown("<script>prueba</script>")
    assert pdf._format_inline_markdown("") == ""


def test_pdf_inline_markdown_preserves_nesting_escaping_and_urls():
    markup = pdf._format_inline_markdown(r"**fuerte con *énfasis*** y \*literal\*")
    assert markup == "<b>fuerte con <i>énfasis</i></b> y *literal*"
    assert Paragraph(markup, pdf._build_styles()["body"]).getPlainText() == "fuerte con énfasis y *literal*"
    link = pdf._format_inline_markdown("[fuente](https://example.org/a_(b))")
    assert 'href="https://example.org/a_(b)"' in link
    assert "<link" not in pdf._format_inline_markdown("[x](javascript:alert(1))")
    assert pdf._format_inline_markdown("[documento](../guia.pdf)") == "[documento](../guia.pdf)"
    assert "<script>" not in pdf._format_inline_markdown("<script>alert(1)</script>")
    text = extract(pdf.generate_legal_pdf_bytes("Consulta", {"respuesta_espanol": r"**fuerte con *énfasis*** y \*literal\*"}))
    assert "fuerte con énfasis y *literal*" in text
    data = pdf.generate_legal_pdf_bytes("Consulta", {"respuesta_espanol": "[fuente](https://example.org/a_(b))"})
    reader = PdfReader(io.BytesIO(data))
    urls = [a.get_object().get("/A", {}).get("/URI") for page in reader.pages for a in page.get("/Annots", [])]
    assert "https://example.org/a_(b)" in urls


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"metadata": None},
        {"response": {}, "metadata": {"enriched_context": None}},
        None,
    ],
)
def test_pdf_accepts_empty_or_legacy_payload_without_crashing(payload):
    output = extract(pdf.generate_legal_pdf_bytes("", payload))
    assert "Consulta del Usuario" in output
    assert "Tema identificado: general" in output
    assert "Respuesta en Español" not in output


def test_pdf_file_output_is_unique_and_confined_to_requested_directory(tmp_path):
    directory = tmp_path / "reports"
    from pathlib import Path

    first = Path(pdf.generate_legal_pdf("Primera", {}, str(directory)))
    second = Path(pdf.generate_legal_pdf("Segunda", {}, str(directory)))
    assert first.parent == second.parent == directory
    assert first != second
    assert "Primera" in extract(first.read_bytes())
    assert "Segunda" in extract(second.read_bytes())


@pytest.mark.parametrize("rows", [[], ["| A |"], ["| A |", "| inválido |"]])
def test_invalid_markdown_table_is_not_rendered_as_table(rows):
    assert pdf._parse_markdown_table(rows, pdf._build_styles()) is None


def test_pdf_table_preserves_escaped_pipe_and_extra_cells():
    assert pdf._split_markdown_row(r"| a\|b | c |") == ["a|b", "c"]
    assert pdf._split_markdown_row(r"a | b\|") == ["a", "b|"]
    markdown = "| A | B |\n| --- | --- |\n" + r"| a\|b | c | extra |"
    table = next(x for x in pdf._markdown_to_flowables(markdown, pdf._build_styles()) if isinstance(x, Table))
    assert [[cell.getPlainText() for cell in row] for row in table._cellvalues] == [["A", "B", ""], ["a|b", "c", "extra"]]
    output = extract(pdf.generate_legal_pdf_bytes("Consulta", {"respuesta_espanol": markdown}))
    assert "a|b" in output and "extra" in output
