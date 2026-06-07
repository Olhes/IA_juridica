from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, AsyncGenerator
from enum import Enum
from datetime import datetime
import asyncio
from loguru import logger

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from config.settings import settings

try:
    from pydantic_ai import Agent, RunContext

    PYDANTIC_AI_AVAILABLE = True
except ImportError as import_error:
    Agent = None
    RunContext = None
    logger.warning(
        f"Pydantic AI no disponible ({import_error}). Usando implementacion simulada."
    )
    PYDANTIC_AI_AVAILABLE = False

try:
    import cohere

    COHERE_SDK_AVAILABLE = True
except ImportError:
    cohere = None
    COHERE_SDK_AVAILABLE = False

COHERE_MODEL_NAME = settings.COHERE_LLM_MODEL
GLOBAL_SYSTEM_PROMPT = (
    os.getenv("SYSTEM_PROMPT")
    or os.getenv("LEGAL_SYSTEM_PROMPT")
    or (
        "Eres un asistente legal peruano especializado en derecho familiar. "
        "Tu prioridad es brindar orientacion juridica precisa, clara y accionable, "
        "con rigor tecnico y lenguaje comprensible para personas no especialistas."
    )
)

SYSTEM_PROMPT_GUARDRAILS = (
    "Reglas obligatorias: "
    "1) Nunca digas ni sugieras que eres un modelo de lenguaje, un LLM o una IA. "
    "2) No te salgas de tu rol de asistente legal; evita temas ajenos a orientacion juridica. "
    "3) No inventes leyes, articulos, jurisprudencia, plazos ni entidades. "
    "4) Si falta informacion, indicalo y pide solo los datos minimos necesarios. "
    "5) Prioriza precision, consistencia y pasos concretos de accion en Perú."
)

SYSTEM_PROMPT_VARIANTS = {
    "violence": (
        "Enfoque de atencion: violencia familiar en Peru. "
        "Prioriza la seguridad, entrega pasos inmediatos, recursos locales y fuentes legales. "
        "Responde con la estructura Pydantic solicitada."
    ),
    "pension": (
        "Enfoque de atencion: pension de alimentos en Peru. "
        "Explica proceso, documentos, plazos y recursos aplicables. "
        "Responde con la estructura Pydantic solicitada."
    ),
    "general": (
        "Enfoque de atencion: orientacion legal bilingue (espanol y quechua). "
        "Usa lenguaje simple, pasos accionables, advertencias y fuentes. "
        "Responde con la estructura Pydantic solicitada. "
        "IMPORTANTE: Mantén las respuestas CORTAS y DIRECTAS (máximo 300-400 caracteres). "
        "Evita explicaciones extensas, ve al grano."
    ),
    "stream": (
        "Formato de salida: solo texto plano, sin JSON ni markdown. "
        "Si falta informacion para precision legal, dilo explicitamente. "
        "IMPORTANTE: Mantén la respuesta CORTA y CONCISA (máximo 300 caracteres). "
        "Ve directo al punto sin explicaciones innecesarias."
    ),
}


def get_system_prompt(variant: str) -> str:
    variant_prompt = SYSTEM_PROMPT_VARIANTS.get(variant, "")
    base_prompt = f"{GLOBAL_SYSTEM_PROMPT}\n\n{SYSTEM_PROMPT_GUARDRAILS}"
    if not variant_prompt:
        return base_prompt
    return f"{base_prompt}\n\n{variant_prompt}"


# Enumeraciones para respuestas estructuradas
class UrgencyLevel(str, Enum):
    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"
    CRITICO = "critico"


class ViolenceType(str, Enum):
    FISICA = "fisica"
    PSICOLOGICA = "psicologica"
    SEXUAL = "sexual"
    ECONOMICA = "economica"
    PATRIMONIAL = "patrimonial"


class LegalTopic(str, Enum):
    VIOLENCIA_FAMILIAR = "violencia_familiar"
    PENSION_ALIMENTOS = "pension_alimentos"
    MEDIDAS_PROTECCION = "medidas_proteccion"
    REGIMEN_VISITAS = "regimen_visitas"
    DENUNCIAS_PROCESOS = "denuncias_procesos"


# Modelos de respuesta Pydantic
class LegalResource(BaseModel):
    """Recurso legal o institucional"""

    nombre: str = Field(..., description="Nombre del recurso")
    tipo: str = Field(
        ..., description="Tipo de recurso (comisaría, juzgado, línea de ayuda)"
    )
    contacto: Optional[str] = Field(None, description="Teléfono, dirección o contacto")
    horario: Optional[str] = Field(None, description="Horario de atención")
    descripcion: str = Field(..., description="Descripción breve del recurso")


class LegalStep(BaseModel):
    """Paso en un procedimiento legal"""

    paso: int = Field(..., description="Número del paso")
    descripcion: str = Field(..., description="Descripción del paso")
    documentos_requeridos: List[str] = Field(
        default_factory=list, description="Documentos necesarios"
    )
    plazo: Optional[str] = Field(None, description="Plazo para completar el paso")
    lugar: Optional[str] = Field(None, description="Dónde realizar el paso")


class LegalWarning(BaseModel):
    """Advertencia legal importante"""

    tipo: str = Field(..., description="Tipo de advertencia")
    mensaje: str = Field(..., description="Mensaje de advertencia")
    urgencia: UrgencyLevel = Field(..., description="Nivel de urgencia")


class LegalSource(BaseModel):
    """Fuente legal citada"""

    nombre: str = Field(..., description="Nombre de la fuente")
    tipo: str = Field(..., description="Tipo (ley, código, artículo)")
    numero: Optional[str] = Field(None, description="Número o identificación")
    enlace: Optional[str] = Field(None, description="Enlace a la fuente")


class ViolenceResponse(BaseModel):
    """Respuesta estructurada para casos de violencia"""

    tipo_violencia: List[ViolenceType] = Field(
        ..., description="Tipos de violencia detectados"
    )
    nivel_urgencia: UrgencyLevel = Field(..., description="Nivel de urgencia")
    medidas_inmediatas: List[str] = Field(
        ..., description="Acciones inmediatas a tomar"
    )
    pasos_denuncia: List[LegalStep] = Field(..., description="Pasos para denunciar")
    recursos_disponibles: List[LegalResource] = Field(
        ..., description="Recursos de ayuda"
    )
    advertencias: List[LegalWarning] = Field(
        ..., description="Advertencias importantes"
    )
    fuentes_legales: List[LegalSource] = Field(
        ..., description="Fuentes legales aplicables"
    )
    confianza_respuesta: float = Field(
        ..., ge=0.0, le=1.0, description="Confianza en la respuesta"
    )


class PensionResponse(BaseModel):
    """Respuesta estructurada para pensión de alimentos"""

    tipo_pension: str = Field(..., description="Tipo de pensión")
    obligados: List[str] = Field(..., description="Quiénes están obligados")
    calculo_basico: Optional[str] = Field(
        None, description="Cálculo básico de la pensión"
    )
    pasos_proceso: List[LegalStep] = Field(..., description="Pasos del proceso")
    documentos_necesarios: List[str] = Field(..., description="Documentos requeridos")
    plazos: List[str] = Field(..., description="Plazos importantes")
    recursos: List[LegalResource] = Field(..., description="Recursos útiles")
    advertencias: List[LegalWarning] = Field(..., description="Advertencias")
    fuentes_legales: List[LegalSource] = Field(..., description="Fuentes legales")
    confianza_respuesta: float = Field(..., ge=0.0, le=1.0)


class GeneralLegalResponse(BaseModel):
    """Respuesta legal general"""

    tema: LegalTopic = Field(..., description="Tema legal identificado")
    respuesta_espanol: str = Field(..., description="Respuesta en español")
    respuesta_quechua: str = Field(..., description="Respuesta en quechua")
    pasos_recomendados: List[LegalStep] = Field(..., description="Pasos recomendados")
    recursos: List[LegalResource] = Field(..., description="Recursos disponibles")
    advertencias: List[LegalWarning] = Field(
        ..., description="Advertencias importantes"
    )
    fuentes: List[LegalSource] = Field(..., description="Fuentes legales")
    confianza: float = Field(
        ..., ge=0.0, le=1.0, description="Confianza de la respuesta"
    )
    fecha_respuesta: datetime = Field(default_factory=datetime.now)


class LegalAgent:
    """Agente legal con validación Pydantic"""

    def __init__(self):
        self.model_name = COHERE_MODEL_NAME
        self.violence_agent = None
        self.pension_agent = None
        self.general_agent = None
        self.cohere_client = None

        if COHERE_SDK_AVAILABLE and settings.COHERE_API_KEY:
            self.cohere_client = cohere.AsyncClient(api_key=settings.COHERE_API_KEY)

        # Nota: se mantiene el path de Pydantic AI como opcional/legacy.
        if PYDANTIC_AI_AVAILABLE and self.cohere_client:
            self._initialize_pydantic_agent()
        else:
            self.agent = None
            logger.warning(
                "Agente Pydantic no inicializado - usando Cohere directo/fallback"
            )

    def _initialize_pydantic_agent(self):
        """Inicializa el agente con Pydantic AI (deshabilitado en modo Cohere directo)."""
        if not Agent:
            logger.warning(
                "Pydantic AI no disponible en runtime. Se usara modo Cohere directo."
            )
            return

        # Se deja desactivado para evitar dependencias cruzadas entre versiones
        # de pydantic-ai y cohere. El flujo principal usa self.cohere_client.
        logger.info(
            "Pydantic AI omitido: usando Cohere directo como proveedor principal"
        )

    def _build_user_prompt(
        self, query: str, context: Dict[str, Any], language: str
    ) -> str:
        normalized_language = "quechua" if language == "quechua" else "spanish"
        context_answer = str(context.get("answer", "")).strip()
        context_sources = context.get("sources", [])
        sources_text = (
            ", ".join(str(source) for source in context_sources)
            if context_sources
            else "Sin fuentes"
        )

        return (
            f"Idioma de salida: {normalized_language}.\n"
            f"Consulta del usuario:\n{query}\n\n"
            f"Contexto recuperado por RAG:\n{context_answer}\n\n"
            f"Fuentes detectadas: {sources_text}\n\n"
            "Instrucciones:\n"
            "1) Da una orientacion legal clara y accionable.\n"
            "2) Si falta informacion para precision legal, dilo explicitamente.\n"
            "3) No incluyas JSON ni markdown; devuelve solo texto plano."
        )

    async def _generate_text_with_cohere(
        self,
        query: str,
        context: Dict[str, Any],
        language: str,
        prompt_variant: str,
        enriched_prompt: Optional[str] = None,
    ) -> str:
        if not self.cohere_client:
            raise RuntimeError("COHERE_API_KEY no configurada en backend.")

        user_query = enriched_prompt if enriched_prompt else query
        user_prompt = self._build_user_prompt(user_query, context, language)

        response = await self.cohere_client.chat(
            message=user_prompt,
            model=self.model_name,
            preamble=get_system_prompt(prompt_variant),
            temperature=settings.COHERE_TEMPERATURE,
            max_tokens=settings.COHERE_MAX_TOKENS,
        )

        response_text = getattr(response, "text", "")
        if not isinstance(response_text, str) or not response_text.strip():
            raise RuntimeError("Cohere devolvio una respuesta vacia.")

        return response_text

    async def respond_to_violence(
        self, query: str, context: Dict[str, Any]
    ) -> ViolenceResponse:
        """Responde a consultas sobre violencia familiar"""
        try:
            if self.cohere_client:
                text_response = await self._generate_text_with_cohere(
                    query, context, "spanish", "violence"
                )
                return self._build_violence_response(text_response, query)

            return await self._fallback_violence_response(query, context)
        except Exception as e:
            logger.error(f"Error en respuesta de violencia: {str(e)}")
            raise

    async def respond_to_pension(
        self, query: str, context: Dict[str, Any]
    ) -> PensionResponse:
        """Responde a consultas sobre pensión de alimentos"""
        try:
            if self.cohere_client:
                text_response = await self._generate_text_with_cohere(
                    query, context, "spanish", "pension"
                )
                return self._build_pension_response(text_response)

            return await self._fallback_pension_response(query, context)
        except Exception as e:
            logger.error(f"Error en respuesta de pensión: {str(e)}")
            raise

    async def respond_general(
        self,
        query: str,
        context: Dict[str, Any],
        language: str = "spanish",
        enriched_prompt: Optional[str] = None,
    ) -> GeneralLegalResponse:
        """Responde a consultas legales generales"""
        try:
            if self.cohere_client:
                text_response = await self._generate_text_with_cohere(
                    query,
                    context,
                    language,
                    "general",
                    enriched_prompt=enriched_prompt,
                )
                return self._build_general_response(text_response, query)

            return await self._fallback_general_response(query, context, language)
        except Exception as e:
            logger.error(f"Error en respuesta general: {str(e)}")
            raise

    async def stream_general_text(
        self,
        query: str,
        context: Dict[str, Any],
        language: str = "spanish",
        enriched_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Transmite respuesta legal en texto usando Cohere streaming."""
        if not self.cohere_client:
            raise RuntimeError(
                "COHERE_API_KEY no configurada en backend para streaming."
            )

        user_query = enriched_prompt if enriched_prompt else query
        user_prompt = self._build_user_prompt(user_query, context, language)

        try:
            stream = self.cohere_client.chat_stream(
                message=user_prompt,
                model=self.model_name,
                preamble=get_system_prompt("stream"),
                temperature=settings.COHERE_TEMPERATURE,
                max_tokens=settings.COHERE_MAX_TOKENS,
            )

            async for event in stream:
                text_chunk = getattr(event, "text", None)
                if isinstance(text_chunk, str) and text_chunk:
                    yield text_chunk
        except Exception as e:
            logger.error(f"Error en streaming general (Cohere): {str(e)}")
            raise RuntimeError(
                f"Fallo Cohere streaming ({self.model_name}): {str(e)}"
            ) from e

    def build_general_response_from_text(
        self, text: str, query: str
    ) -> GeneralLegalResponse:
        """Construye una respuesta legal estructurada a partir de texto."""
        return self._build_general_response(text, query)

    # ── Builders: texto plano → modelo Pydantic ──────────────────────

    def _detect_urgency(self, text: str) -> UrgencyLevel:
        """Detecta urgencia a partir del texto."""
        t = text.lower()
        if any(
            w in t for w in ["peligro", "emergencia", "urgente", "inmediato", "crítico"]
        ):
            return UrgencyLevel.CRITICO
        if any(w in t for w in ["alto riesgo", "amenaza", "grave"]):
            return UrgencyLevel.ALTO
        if any(w in t for w in ["medio", "moderado"]):
            return UrgencyLevel.MEDIO
        return UrgencyLevel.BAJO

    def _detect_violence_types(self, text: str) -> List[ViolenceType]:
        """Detecta tipos de violencia mencionados en el texto."""
        t = text.lower()
        types = []
        if any(w in t for w in ["física", "golpe", "lesión"]):
            types.append(ViolenceType.FISICA)
        if any(w in t for w in ["psicológica", "emocional", "insulto", "humilla"]):
            types.append(ViolenceType.PSICOLOGICA)
        if any(w in t for w in ["sexual", "acoso sexual", "violación"]):
            types.append(ViolenceType.SEXUAL)
        if any(w in t for w in ["económica", "patrimoni"]):
            types.append(ViolenceType.ECONOMICA)
        return types or [ViolenceType.FISICA]

    def _detect_topic(self, text: str) -> LegalTopic:
        """Detecta tema legal del texto."""
        t = text.lower()
        if "violencia" in t or "golpe" in t or "agresión" in t:
            return LegalTopic.VIOLENCIA_FAMILIAR
        if "pensión" in t or "alimento" in t:
            return LegalTopic.PENSION_ALIMENTOS
        if "protección" in t or "medida" in t:
            return LegalTopic.MEDIDAS_PROTECCION
        if "visita" in t or "régimen" in t:
            return LegalTopic.REGIMEN_VISITAS
        return LegalTopic.DENUNCIAS_PROCESOS

    def _extract_section(
        self, text: str, header: str, next_headers: List[str] | None = None
    ) -> str:
        """Extrae una sección del texto por encabezado."""
        import re

        # Buscar el header (case-insensitive)
        pattern = re.compile(
            re.escape(header) + r"[:\s]*(.*)", re.IGNORECASE | re.DOTALL
        )
        match = pattern.search(text)
        if not match:
            return ""
        content = match.group(1)
        # Cortar en el siguiente header si existe
        if next_headers:
            for nh in next_headers:
                idx = content.lower().find(nh.lower())
                if idx > 0:
                    content = content[:idx]
                    break
        return content.strip()

    def _build_violence_response(self, text: str, query: str) -> ViolenceResponse:
        """Construye ViolenceResponse a partir de texto plano de Cohere."""
        return ViolenceResponse(
            tipo_violencia=self._detect_violence_types(query + " " + text),
            nivel_urgencia=self._detect_urgency(query + " " + text),
            medidas_inmediatas=[text],  # Todo el texto como medida
            pasos_denuncia=[
                LegalStep(paso=1, descripcion=text[:500] if len(text) > 500 else text)
            ],
            recursos_disponibles=[
                LegalResource(
                    nombre="Línea 113",
                    tipo="Línea de ayuda",
                    contacto="113",
                    horario="24/7",
                    descripcion="Atención gratuita para mujeres",
                )
            ],
            advertencias=[
                LegalWarning(
                    tipo="Seguridad",
                    mensaje="Tu seguridad es lo primero",
                    urgencia=UrgencyLevel.CRITICO,
                )
            ],
            fuentes_legales=[LegalSource(nombre="Ley 30364", tipo="Ley")],
            confianza_respuesta=0.85,
        )

    def _build_pension_response(self, text: str) -> PensionResponse:
        """Construye PensionResponse a partir de texto plano de Cohere."""
        return PensionResponse(
            tipo_pension="Alimentos",
            obligados=["Padres", "Abuelos (subsidiariamente)"],
            calculo_basico=None,
            pasos_proceso=[
                LegalStep(paso=1, descripcion=text[:500] if len(text) > 500 else text)
            ],
            documentos_necesarios=[
                "DNI",
                "Partida de nacimiento",
                "Pruebas de ingresos",
            ],
            plazos=["Proceso dura aprox. 6-12 meses"],
            recursos=[
                LegalResource(
                    nombre="Juzgado de Familia",
                    tipo="Institución judicial",
                    descripcion="Competente en casos de alimentos",
                )
            ],
            advertencias=[
                LegalWarning(
                    tipo="Proceso",
                    mensaje="El proceso requiere paciencia",
                    urgencia=UrgencyLevel.BAJO,
                )
            ],
            fuentes_legales=[
                LegalSource(
                    nombre="Código Civil", tipo="Código", numero="Arts. 472-485"
                )
            ],
            confianza_respuesta=0.85,
        )

    def _build_general_response(self, text: str, query: str) -> GeneralLegalResponse:
        """Construye GeneralLegalResponse a partir de texto plano de Cohere."""
        # Intentar extraer secciones si el modelo las incluyó
        spanish = (
            self._extract_section(
                text,
                "RESPUESTA EN ESPAÑOL",
                ["RESPUESTA EN QUECHUA", "PASOS RECOMENDADOS", "RECURSOS", "FUENTES"],
            )
            or text
        )
        quechua = (
            self._extract_section(
                text,
                "RESPUESTA EN QUECHUA",
                ["PASOS RECOMENDADOS", "RECURSOS", "FUENTES"],
            )
            or "(Traducción quechua no disponible)"
        )

        return GeneralLegalResponse(
            tema=self._detect_topic(query + " " + text),
            respuesta_espanol=spanish,
            respuesta_quechua=quechua,
            pasos_recomendados=[
                LegalStep(
                    paso=1,
                    descripcion="Consulta con un abogado para tu caso específico",
                )
            ],
            recursos=[
                LegalResource(
                    nombre="Línea 113",
                    tipo="Línea de ayuda",
                    descripcion="Atención gratuita 24/7",
                ),
                LegalResource(
                    nombre="CEM",
                    tipo="Centro de Emergencia Mujer",
                    descripcion="Asesoría legal gratuita",
                ),
            ],
            advertencias=[
                LegalWarning(
                    tipo="Información",
                    mensaje="Esta orientación no reemplaza asesoría legal profesional",
                    urgencia=UrgencyLevel.BAJO,
                )
            ],
            fuentes=[LegalSource(nombre="Legislación peruana", tipo="Referencia")],
            confianza=0.85,
        )

    # ── Fallbacks (sin Pydantic AI) ───────────────────────────────

    async def _fallback_violence_response(
        self, query: str, context: Dict[str, Any]
    ) -> ViolenceResponse:
        """Implementación fallback para violencia"""

        # Detectar palabras clave
        query_lower = query.lower()
        urgency = UrgencyLevel.MEDIO

        if any(
            word in query_lower for word in ["golpe", "agresión", "arma", "peligro"]
        ):
            urgency = UrgencyLevel.CRITICO
        elif any(word in query_lower for word in ["amenaza", "miedo", "acoso"]):
            urgency = UrgencyLevel.ALTO

        # Respuesta básica estructurada
        return ViolenceResponse(
            tipo_violencia=[ViolenceType.FISICA, ViolenceType.PSICOLOGICA],
            nivel_urgencia=urgency,
            medidas_inmediatas=[
                "Busca un lugar seguro",
                "Llama a la línea 113 (gratuita, 24/7)",
                "Acude a la comisaría más cercana",
            ],
            pasos_denuncia=[
                LegalStep(
                    paso=1,
                    descripcion="Acude a la comisaría de Mujeres o fiscalía",
                    documentos_requeridos=["DNI", "pruebas si tienes"],
                    lugar="Comisaría de Mujeres",
                ),
                LegalStep(
                    paso=2,
                    descripcion="Presenta denuncia formal",
                    documentos_requeridos=["Denuncia escrita", "testigos"],
                    plazo="Inmediato",
                ),
            ],
            recursos_disponibles=[
                LegalResource(
                    nombre="Línea 113",
                    tipo="Línea de ayuda",
                    contacto="113",
                    horario="24/7 gratuito",
                    descripcion="Atención de emergencia para mujeres",
                )
            ],
            advertencias=[
                LegalWarning(
                    tipo="Seguridad",
                    mensaje="Tu seguridad es lo primero, no arriesgues tu vida",
                    urgencia=UrgencyLevel.CRITICO,
                )
            ],
            fuentes_legales=[
                LegalSource(
                    nombre="Ley 30364",
                    tipo="Ley",
                )
            ],
            confianza_respuesta=0.7,
        )

    async def _fallback_pension_response(
        self, query: str, context: Dict[str, Any]
    ) -> PensionResponse:
        """Implementación fallback para pensión"""

        return PensionResponse(
            tipo_pension="Alimentos para menores",
            obligados=["Padres", "Abuelos"],
            calculo_basico="Generalmente 25% del ingreso del obligado",
            pasos_proceso=[
                LegalStep(
                    paso=1,
                    descripcion="Reúne documentos",
                    documentos_requeridos=[
                        "DNI",
                        "partidas de nacimiento",
                        "pruebas de ingresos",
                    ],
                ),
                LegalStep(
                    paso=2,
                    descripcion="Presenta demanda en Juzgado de Familia",
                    documentos_requeridos=["Demanda", "documentos"],
                    lugar="Juzgado de Familia",
                ),
            ],
            documentos_necesarios=["DNI", "partidas", "comprobantes de ingresos"],
            plazos=["No hay plazo para solicitar", "Proceso dura 6-12 meses"],
            recursos=[
                LegalResource(
                    nombre="Juzgado de Familia",
                    tipo="Institución judicial",
                    descripcion="Competente en casos de alimentos",
                )
            ],
            advertencias=[
                LegalWarning(
                    tipo="Proceso",
                    mensaje="El proceso puede ser largo, requiere paciencia",
                    urgencia=UrgencyLevel.BAJO,
                )
            ],
            fuentes_legales=[
                LegalSource(
                    nombre="Código Civil",
                    tipo="Código",
                    numero="Artículos 472-485",
                )
            ],
            confianza_respuesta=0.6,
        )

    async def _fallback_general_response(
        self, query: str, context: Dict[str, Any], language: str
    ) -> GeneralLegalResponse:
        """Implementación fallback general"""

        # Detectar tema
        query_lower = query.lower()
        if "violencia" in query_lower or "golpe" in query_lower:
            topic = LegalTopic.VIOLENCIA_FAMILIAR
        elif "pensión" in query_lower or "alimentos" in query_lower:
            topic = LegalTopic.PENSION_ALIMENTOS
        elif "protección" in query_lower or "medida" in query_lower:
            topic = LegalTopic.MEDIDAS_PROTECCION
        else:
            topic = LegalTopic.DENUNCIAS_PROCESOS

        # Respuesta básica bilingüe
        spanish_response = (
            "Esta es una respuesta básica en español sobre tu consulta legal."
        )
        quechua_response = (
            "Kay basic respuesta español simipi consulta legal tuyki about."
        )

        return GeneralLegalResponse(
            tema=topic,
            respuesta_espanol=spanish_response,
            respuesta_quechua=quechua_response,
            pasos_recomendados=[
                LegalStep(
                    paso=1,
                    descripcion="Consulta con un abogado",
                    documentos_requeridos=["Documentos relevantes"],
                )
            ],
            recursos=[
                LegalResource(
                    nombre="Servicio Legal",
                    tipo="Asesoría",
                    descripcion="Consulta profesional",
                )
            ],
            advertencias=[
                LegalWarning(
                    tipo="General",
                    mensaje="Esto no reemplaza asesoría legal profesional",
                    urgencia=UrgencyLevel.BAJO,
                )
            ],
            fuentes=[
                LegalSource(
                    nombre="Código Legal",
                    tipo="Referencia",
                )
            ],
            confianza=0.5,
        )

    def get_agent_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas de los agentes"""

        return {
            "pydantic_ai_available": PYDANTIC_AI_AVAILABLE,
            "cohere_streaming_available": self.cohere_client is not None,
            "model": self.model_name,
            "agents_configured": 3 if PYDANTIC_AI_AVAILABLE else 0,
            "response_types": [
                "violencia_familiar",
                "pension_alimentos",
                "general_legal",
            ],
            "supported_languages": ["spanish", "quechua"],
            "validation_enabled": True,
        }
