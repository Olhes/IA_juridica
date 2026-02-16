"""
Generador de reportes PDF para respuestas legales
Usa ReportLab para generar PDFs bilingües (español/quechua)
"""

import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

from loguru import logger


# Colores del tema
PRIMARY_COLOR = HexColor("#1a365d")
ACCENT_COLOR = HexColor("#2b6cb0")
LIGHT_BG = HexColor("#f7fafc")
BORDER_COLOR = HexColor("#cbd5e0")


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
        enriched_context = metadata.get("enriched_context", {}) if isinstance(metadata, dict) else {}
        legal_topic = enriched_context.get("legal_topic") if isinstance(enriched_context, dict) else None
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
    story.append(Paragraph(query, styles["body"]))
    story.append(Spacer(1, 8))

    # ---- Tema detectado ----
    tema = response_data.get("tema", "general")
    story.append(Paragraph(f"<b>Tema identificado:</b> {tema}", styles["body"]))

    # ---- Respuesta en español ----
    spanish = response_data.get("respuesta_espanol", "")
    if spanish:
        story.append(Paragraph("Respuesta en Español", styles["heading"]))
        # Dividir por párrafos para mejor formato
        for para in spanish.split("\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(para, styles["body"]))

    # ---- Respuesta en quechua ----
    quechua = response_data.get("respuesta_quechua", "")
    if quechua:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Quechua Simipi Respuesta", styles["heading"]))
        for para in quechua.split("\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(para, styles["body"]))

    # ---- Pasos recomendados ----
    pasos = response_data.get("pasos_recomendados", [])
    if pasos:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Pasos Recomendados", styles["heading"]))
        for paso in pasos:
            if isinstance(paso, dict):
                num = paso.get("paso", "")
                desc = paso.get("descripcion", "")
                story.append(Paragraph(f"<b>Paso {num}:</b> {desc}", styles["body"]))
                docs_req = paso.get("documentos_requeridos", [])
                if docs_req:
                    docs_str = ", ".join(docs_req)
                    story.append(Paragraph(f"  Documentos: {docs_str}", styles["label"]))

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
                text = f"<b>{nombre}</b>"
                if contacto:
                    text += f" — {contacto}"
                if desc:
                    text += f"<br/>{desc}"
                story.append(Paragraph(text, styles["body"]))

    # ---- Advertencias ----
    advertencias = response_data.get("advertencias", [])
    if advertencias:
        story.append(Spacer(1, 6))
        story.append(Paragraph("⚠ Advertencias Importantes", styles["heading"]))
        for adv in advertencias:
            if isinstance(adv, dict):
                msg = adv.get("mensaje", "")
                story.append(Paragraph(f"• {msg}", styles["body"]))

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
                text = f"• {nombre}"
                if tipo:
                    text += f" ({tipo})"
                if num:
                    text += f" — {num}"
                story.append(Paragraph(text, styles["body"]))

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
