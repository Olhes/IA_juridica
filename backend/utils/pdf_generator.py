"""
Generador de reportes PDF para respuestas legales
Usa ReportLab para generar PDFs bilingües (español/quechua)
"""

import uuid
import html
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

from loguru import logger


# Colores del tema
PRIMARY_COLOR = HexColor("#1a365d")
ACCENT_COLOR = HexColor("#2b6cb0")
LIGHT_BG = HexColor("#f7fafc")
BORDER_COLOR = HexColor("#cbd5e0")
CODE_BG = HexColor("#edf2f7")


_FENCE_RE = re.compile(r"^\s*```([\w+-]*)\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^(\s*)([-+*]|\d+[.)])\s+(.*)$")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")


def _normalize_markdown(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _format_inline_markdown(text: str) -> str:
    """Convierte markdown inline a etiquetas compatibles con ReportLab Paragraph."""
    raw = _normalize_markdown(text)
    if not raw:
        return ""

    escaped = html.escape(raw, quote=False)

    code_spans: List[str] = []

    def replace_code(match: re.Match[str]) -> str:
        code_spans.append(match.group(1))
        return f"@@CODETOKEN{len(code_spans) - 1}@@"

    escaped = re.sub(r"`([^`]+)`", replace_code, escaped)

    def replace_image(match: re.Match[str]) -> str:
        alt = match.group(1).strip()
        src = match.group(2).strip()
        label = alt if alt else src
        return f"[Imagen: {html.escape(label, quote=False)}]"

    escaped = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_image, escaped)

    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        url = html.escape(match.group(2).strip(), quote=True)
        return f'<link href="{url}"><u>{label}</u></link>'

    escaped = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", replace_link, escaped)

    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*(?!\*)([^*]+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"(?<!_)_(?!_)([^_]+?)(?<!_)_(?!_)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"~~(.+?)~~", r"<font color='#718096'>\1</font>", escaped)

    for index, snippet in enumerate(code_spans):
        token = f"@@CODETOKEN{index}@@"
        code_html = html.escape(snippet, quote=False)
        escaped = escaped.replace(token, f"<font face='Courier'>{code_html}</font>")

    return escaped


def _split_markdown_row(line: str) -> List[str]:
    clean = line.strip()
    if clean.startswith("|"):
        clean = clean[1:]
    if clean.endswith("|"):
        clean = clean[:-1]
    return [cell.strip() for cell in clean.split("|")]


def _is_table_separator_row(cells: List[str]) -> bool:
    if not cells:
        return False
    for cell in cells:
        compact = cell.replace(" ", "")
        if not compact:
            continue
        if not re.fullmatch(r":?-{3,}:?", compact):
            return False
    return True


def _looks_like_table_row(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and "|" in stripped


def _is_markdown_table_start(lines: List[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    if not _looks_like_table_row(lines[index]) or not _looks_like_table_row(
        lines[index + 1]
    ):
        return False
    separator_cells = _split_markdown_row(lines[index + 1])
    return _is_table_separator_row(separator_cells)


def _parse_markdown_table(
    table_lines: List[str], styles: Dict[str, ParagraphStyle]
) -> Optional[Table]:
    if len(table_lines) < 2:
        return None

    rows = [_split_markdown_row(row) for row in table_lines]
    if not _is_table_separator_row(rows[1]):
        return None

    data_rows = [rows[0]] + rows[2:]
    if not data_rows:
        return None

    num_cols = max(len(row) for row in data_rows)
    normalized_rows: List[List[Paragraph]] = []
    for row_index, row in enumerate(data_rows):
        padded = row + [""] * (num_cols - len(row))
        row_style = styles["table_header"] if row_index == 0 else styles["table_cell"]
        normalized_rows.append(
            [
                Paragraph(_format_inline_markdown(cell) or " ", row_style)
                for cell in padded
            ]
        )

    table = Table(normalized_rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), PRIMARY_COLOR),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _parse_list_item(line: str) -> Optional[Tuple[int, str, str]]:
    match = _LIST_RE.match(line)
    if not match:
        return None

    indent = len(match.group(1).replace("\t", "    "))
    marker = match.group(2)
    content = match.group(3).strip()

    if marker in {"-", "+", "*"}:
        marker = "-"
    elif marker.endswith(")"):
        marker = f"{marker[:-1]}."

    return indent, marker, content


def _is_horizontal_rule(line: str) -> bool:
    return bool(_HR_RE.match(line.strip()))


def _is_block_boundary(lines: List[str], index: int) -> bool:
    stripped = lines[index].strip()
    if not stripped:
        return True
    if _FENCE_RE.match(stripped) or _HEADING_RE.match(stripped):
        return True
    if _is_horizontal_rule(stripped) or stripped.startswith(">"):
        return True
    if _parse_list_item(lines[index]) is not None:
        return True
    return _is_markdown_table_start(lines, index)


def _markdown_to_flowables(
    markdown_text: str, styles: Dict[str, ParagraphStyle]
) -> List[Any]:
    """Convierte markdown completo a flowables de ReportLab."""
    markdown = _normalize_markdown(markdown_text)
    if not markdown:
        return []

    lines = markdown.split("\n")
    flowables: List[Any] = []
    index = 0

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()

        if not stripped:
            index += 1
            continue

        fence = _FENCE_RE.match(stripped)
        if fence:
            language = fence.group(1).strip()
            index += 1
            code_lines: List[str] = []

            while index < len(lines):
                candidate = lines[index]
                if _FENCE_RE.match(candidate.strip()):
                    index += 1
                    break
                code_lines.append(candidate.rstrip("\n"))
                index += 1

            if language:
                flowables.append(
                    Paragraph(
                        f"Codigo ({html.escape(language, quote=False)})",
                        styles["code_label"],
                    )
                )

            code_text = "\n".join(code_lines).strip("\n") or " "
            flowables.append(Preformatted(code_text, styles["code_block"]))
            flowables.append(Spacer(1, 6))
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            level = min(len(heading.group(1)), 4)
            heading_text = _format_inline_markdown(heading.group(2).strip()) or " "
            flowables.append(Paragraph(heading_text, styles[f"h{level}"]))
            index += 1
            continue

        if _is_horizontal_rule(stripped):
            flowables.append(HRFlowable(width="100%", color=BORDER_COLOR))
            flowables.append(Spacer(1, 6))
            index += 1
            continue

        if _is_markdown_table_start(lines, index):
            table_lines: List[str] = []
            while (
                index < len(lines)
                and lines[index].strip()
                and _looks_like_table_row(lines[index])
            ):
                table_lines.append(lines[index])
                index += 1

            table = _parse_markdown_table(table_lines, styles)
            if table is not None:
                flowables.append(table)
                flowables.append(Spacer(1, 8))
            continue

        if stripped.startswith(">"):
            quote_lines: List[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_line = re.sub(r"^\s*>\s?", "", lines[index]).strip()
                if quote_line:
                    quote_lines.append(quote_line)
                index += 1

            quote_text = _format_inline_markdown(" ".join(quote_lines)) or " "
            flowables.append(Paragraph(quote_text, styles["blockquote"]))
            flowables.append(Spacer(1, 4))
            continue

        list_item = _parse_list_item(raw_line)
        if list_item:
            while index < len(lines):
                current = lines[index]
                parsed = _parse_list_item(current)
                if parsed is None:
                    break

                indent, marker, content = parsed
                continuation: List[str] = []
                next_index = index + 1

                while next_index < len(lines):
                    next_line = lines[next_index]
                    next_stripped = next_line.strip()
                    if not next_stripped:
                        next_index += 1
                        break
                    if _parse_list_item(next_line) is not None:
                        break
                    if _is_block_boundary(lines, next_index):
                        break

                    next_indent = len(next_line) - len(next_line.lstrip(" "))
                    if next_indent <= indent and next_stripped:
                        break

                    continuation.append(next_stripped)
                    next_index += 1

                item_text = content
                if continuation:
                    item_text = f"{item_text} {' '.join(continuation)}"

                level = min(indent // 2, 3)
                style = styles[f"list_{level}"]
                flowables.append(
                    Paragraph(
                        _format_inline_markdown(f"{marker} {item_text}") or " ", style
                    )
                )
                index = next_index

            flowables.append(Spacer(1, 4))
            continue

        paragraph_lines = [stripped]
        index += 1
        while (
            index < len(lines)
            and lines[index].strip()
            and not _is_block_boundary(lines, index)
        ):
            paragraph_lines.append(lines[index].strip())
            index += 1

        paragraph_text = _format_inline_markdown(" ".join(paragraph_lines)) or " "
        flowables.append(Paragraph(paragraph_text, styles["body"]))
        flowables.append(Spacer(1, 3))

    if flowables and isinstance(flowables[-1], Spacer):
        flowables.pop()

    return flowables


def _normalize_response_data(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza payloads para soportar formatos planos y respuesta completa de /legal-query."""
    if not isinstance(response_data, dict):
        return {}

    normalized = response_data

    nested = normalized.get("response")
    if isinstance(nested, dict):
        normalized = nested

    if not normalized.get("tema"):
        metadata = response_data.get("metadata", {})
        enriched_context = (
            metadata.get("enriched_context", {}) if isinstance(metadata, dict) else {}
        )
        legal_topic = (
            enriched_context.get("legal_topic")
            if isinstance(enriched_context, dict)
            else None
        )
        if legal_topic:
            normalized = {**normalized, "tema": legal_topic}

    return normalized


def _build_styles() -> Dict[str, ParagraphStyle]:
    """Estilos personalizados para el reporte legal"""
    base = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "LegalTitle",
            parent=base["Title"],
            fontSize=18,
            textColor=PRIMARY_COLOR,
            spaceAfter=12,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "LegalSubtitle",
            parent=base["Normal"],
            fontSize=10,
            textColor=ACCENT_COLOR,
            alignment=TA_CENTER,
            spaceAfter=20,
        ),
        "heading": ParagraphStyle(
            "LegalHeading",
            parent=base["Heading2"],
            fontSize=13,
            textColor=PRIMARY_COLOR,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "MarkdownH1",
            parent=base["Heading1"],
            fontSize=15,
            leading=18,
            textColor=PRIMARY_COLOR,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "h2": ParagraphStyle(
            "MarkdownH2",
            parent=base["Heading2"],
            fontSize=13,
            leading=16,
            textColor=PRIMARY_COLOR,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "h3": ParagraphStyle(
            "MarkdownH3",
            parent=base["Heading3"],
            fontSize=11.5,
            leading=14,
            textColor=ACCENT_COLOR,
            spaceBefore=7,
            spaceAfter=3,
        ),
        "h4": ParagraphStyle(
            "MarkdownH4",
            parent=base["Heading4"],
            fontSize=10.5,
            leading=13,
            textColor=ACCENT_COLOR,
            spaceBefore=6,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "LegalBody",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        ),
        "disclaimer": ParagraphStyle(
            "Disclaimer",
            parent=base["Normal"],
            fontSize=8,
            textColor=HexColor("#718096"),
            alignment=TA_CENTER,
            spaceBefore=20,
        ),
        "label": ParagraphStyle(
            "Label",
            parent=base["Normal"],
            fontSize=9,
            textColor=ACCENT_COLOR,
            spaceBefore=4,
        ),
        "list_0": ParagraphStyle(
            "ListLevel0",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            leftIndent=10,
            spaceAfter=3,
        ),
        "list_1": ParagraphStyle(
            "ListLevel1",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            leftIndent=22,
            spaceAfter=3,
        ),
        "list_2": ParagraphStyle(
            "ListLevel2",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            leftIndent=34,
            spaceAfter=3,
        ),
        "list_3": ParagraphStyle(
            "ListLevel3",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            leftIndent=46,
            spaceAfter=3,
        ),
        "blockquote": ParagraphStyle(
            "Blockquote",
            parent=base["Normal"],
            fontSize=9.5,
            leading=13,
            alignment=TA_LEFT,
            leftIndent=14,
            rightIndent=8,
            textColor=HexColor("#4a5568"),
            backColor=HexColor("#f7fafc"),
            borderColor=BORDER_COLOR,
            borderWidth=0.5,
            borderPadding=6,
            spaceAfter=5,
        ),
        "code_label": ParagraphStyle(
            "CodeLabel",
            parent=base["Normal"],
            fontSize=8,
            textColor=HexColor("#4a5568"),
            spaceBefore=2,
            spaceAfter=3,
        ),
        "code_block": ParagraphStyle(
            "CodeBlock",
            parent=base["Code"],
            fontName="Courier",
            fontSize=8.5,
            leading=11,
            textColor=HexColor("#1a202c"),
            backColor=CODE_BG,
            leftIndent=6,
            rightIndent=6,
            borderColor=BORDER_COLOR,
            borderWidth=0.5,
            borderPadding=6,
            spaceAfter=6,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=PRIMARY_COLOR,
            alignment=TA_LEFT,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=HexColor("#2d3748"),
            alignment=TA_LEFT,
        ),
    }


def generate_legal_pdf(
    query: str,
    response_data: Dict[str, Any],
    output_dir: str = "./temp/pdfs",
) -> str:
    """
    Genera un PDF con la respuesta legal bilingüe.

    Args:
        query: Consulta original del usuario
        response_data: Diccionario con la respuesta (model_dump de GeneralLegalResponse)
        output_dir: Directorio de salida

    Returns:
        Ruta absoluta del PDF generado
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    filename = f"reporte_legal_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path = out / filename

    styles = _build_styles()

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    story = []
    response_data = _normalize_response_data(response_data)

    # ---- Header ----
    story.append(Paragraph("IA Jurídica — Reporte Legal", styles["title"]))
    story.append(
        Paragraph(
            f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            styles["subtitle"],
        )
    )
    story.append(HRFlowable(width="100%", color=BORDER_COLOR))
    story.append(Spacer(1, 12))

    # ---- Consulta ----
    story.append(Paragraph("Consulta del Usuario", styles["heading"]))
    query_flowables = _markdown_to_flowables(query, styles)
    if query_flowables:
        story.extend(query_flowables)
    else:
        story.append(Paragraph(_format_inline_markdown(query) or " ", styles["body"]))
    story.append(Spacer(1, 8))

    # ---- Tema detectado ----
    tema = response_data.get("tema", "general")
    story.append(Paragraph(f"<b>Tema identificado:</b> {tema}", styles["body"]))

    # ---- Respuesta en español ----
    spanish = response_data.get("respuesta_espanol", "")
    if spanish:
        story.append(Paragraph("Respuesta en Español", styles["heading"]))
        story.extend(_markdown_to_flowables(str(spanish), styles))

    # ---- Respuesta en quechua ----
    quechua = response_data.get("respuesta_quechua", "")
    if quechua:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Quechua Simipi Respuesta", styles["heading"]))
        story.extend(_markdown_to_flowables(str(quechua), styles))

    # ---- Pasos recomendados ----
    pasos = response_data.get("pasos_recomendados", [])
    if pasos:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Pasos Recomendados", styles["heading"]))
        for paso in pasos:
            if isinstance(paso, dict):
                num = paso.get("paso", "")
                desc = paso.get("descripcion", "")
                story.append(
                    Paragraph(
                        _format_inline_markdown(f"**Paso {num}:** {desc}") or " ",
                        styles["body"],
                    )
                )
                docs_req = paso.get("documentos_requeridos", [])
                if docs_req:
                    docs_str = ", ".join(docs_req)
                    story.append(
                        Paragraph(
                            _format_inline_markdown(f"Documentos: {docs_str}") or " ",
                            styles["label"],
                        )
                    )

    # ---- Recursos ----
    recursos = response_data.get("recursos", [])
    if recursos:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Recursos Disponibles", styles["heading"]))
        for rec in recursos:
            if isinstance(rec, dict):
                nombre = rec.get("nombre", "")
                contacto = rec.get("contacto", "")
                desc = rec.get("descripcion", "")
                text = f"**{nombre}**"
                if contacto:
                    text += f" — {contacto}"
                if desc:
                    text += f"\n{desc}"
                story.extend(_markdown_to_flowables(text, styles))

    # ---- Advertencias ----
    advertencias = response_data.get("advertencias", [])
    if advertencias:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Advertencias Importantes", styles["heading"]))
        for adv in advertencias:
            if isinstance(adv, dict):
                msg = adv.get("mensaje", "")
                story.append(
                    Paragraph(
                        _format_inline_markdown(f"- {msg}") or " ", styles["body"]
                    )
                )

    # ---- Fuentes legales ----
    fuentes = response_data.get("fuentes", response_data.get("fuentes_legales", []))
    if fuentes:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Fuentes Legales", styles["heading"]))
        for src in fuentes:
            if isinstance(src, dict):
                nombre = src.get("nombre", "")
                tipo = src.get("tipo", "")
                num = src.get("numero", "")
                text = f"- {nombre}"
                if tipo:
                    text += f" ({tipo})"
                if num:
                    text += f" — {num}"
                story.append(
                    Paragraph(_format_inline_markdown(text) or " ", styles["body"])
                )

    # ---- Disclaimer ----
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", color=BORDER_COLOR))
    story.append(
        Paragraph(
            "AVISO: Este documento es orientativo y no constituye asesoría legal profesional. "
            "Para situaciones específicas, consulte con un abogado.",
            styles["disclaimer"],
        )
    )
    story.append(
        Paragraph(
            "YUYAYCHAY: Kay qillqa orientativo nisqallan, manam profesional asesoría legal nisqachu. "
            "Específico situaciones nisqakunapaq, abogadowan consultay.",
            styles["disclaimer"],
        )
    )

    doc.build(story)
    logger.info(f"PDF generado: {pdf_path}")
    return str(pdf_path.resolve())
