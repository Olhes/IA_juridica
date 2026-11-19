"""Instrucciones únicas del asistente jurídico y composición de datos del turno."""

import os


DEFAULT_LEGAL_ROLE = (
    "Eres un asistente legal peruano especializado en derecho familiar. "
    "Da orientación jurídica precisa y comprensible para personas no especialistas."
)

LEGAL_RULES = """- Mantente dentro de la orientación jurídica. Empieza por la respuesta, sin saludo.
  Sé claro, directo y empático. Usa Markdown si ayuda; no devuelvas JSON.
- Usa el idioma de redacción indicado por la aplicación. Entrega una sola versión,
  sin añadir una traducción. El tema o idioma detectado en la consulta no cambia
  esa instrucción.
- Basa las afirmaciones jurídicas en la evidencia pertinente. Si falta respaldo,
  dilo y pide solo los datos mínimos necesarios. No inventes normas, artículos,
  porcentajes, plazos, requisitos, prácticas, entidades ni recursos.
- Usa el tema, la urgencia, la ubicación y la información cultural como contexto
  del turno, no como hechos comprobados ni como fuentes jurídicas. No deduzcas
  la ocupación o ubicación de una persona a partir de ese contexto.
- Cita la norma y la sección del mismo bloque de evidencia. Distingue la ley
  modificatoria de la norma modificada. Si hay una referencia exacta recuperada,
  respeta su nivel sin sustituirla por secciones hermanas o por el artículo general.
- Conserva las condiciones, excepciones, punto de partida de los plazos y verbos
  de facultad u obligación. Si se pide una enumeración, conserva todos los
  numerales o literales pertinentes disponibles, con su orden y sentido; si la
  fuente está incompleta, indícalo. Omite marcas de conversión y corrige solo
  cortes de palabras inequívocos.
- Si se describe peligro inmediato o violencia, prioriza la seguridad sin
  culpabilizar. Ante peligro inmediato, orienta a contactar a los servicios
  locales de emergencia. Incluye pasos, medidas de protección o contactos
  específicos solo cuando sean pertinentes y estén respaldados.
"""

CULTURAL_TERMS = {
    "ayllu": "Comunidad organizada tradicionalmente",
    "ayni": "Sistema de reciprocidad y ayuda mutua",
    "minga": "Trabajo comunal para el bien común",
    "varayoc": "Autoridad tradicional del pueblo",
    "pachamama": "Madre Tierra, divinidad andina",
    "despacho": "Ofrenda o pago a la tierra",
    "tejido social": "Red de relaciones comunitarias",
    "buen vivir": "Filosofía de vida en armonía",
    "saber local": "Conocimiento tradicional de la comunidad",
    "autoridad tradicional": "Líderes reconocidos por la comunidad",
}


def get_legal_system_prompt() -> str:
    """Permite personalizar el rol sin reemplazar las reglas de evidencia y seguridad."""
    role = os.getenv("SYSTEM_PROMPT") or os.getenv("LEGAL_SYSTEM_PROMPT") or DEFAULT_LEGAL_ROLE
    return f"{role.strip()}\n\n{LEGAL_RULES.strip()}"


def format_legal_context(query, documents, *, context=None, include_documents=True) -> str:
    """Serializa datos del turno. El preámbulo se envía por separado."""
    context = context or {}
    parts = [f"=== CONSULTA DEL USUARIO ===\n{query}"]
    fields = (
        ("legal_topic", "Tema legal detectado"),
        ("urgency_level", "Urgencia detectada"),
        ("detected_location", "Ubicación mencionada"),
    )
    notes = [f"- {label}: {context[key]}" for key, label in fields if context.get(key)]
    cultural = (context.get("location_info") or {}).get("cultural_notes")
    if cultural:
        notes.append(f"- Contexto cultural: {cultural}")
    if notes:
        parts.append("=== CONTEXTO DEL TURNO ===\n" + "\n".join(notes))
    if include_documents and documents:
        excerpts = []
        for i, doc in enumerate(documents, 1):
            source = (doc.get("metadata") or {}).get("title") or "Fuente no especificada"
            excerpts.append(f"--- Documento {i} ---\nFuente: {source}\n{doc.get('content', '')[:600]}")
        parts.append("=== CONTEXTO LEGAL RELEVANTE ===\n" + "\n\n".join(excerpts))
    return "\n\n".join(parts)
