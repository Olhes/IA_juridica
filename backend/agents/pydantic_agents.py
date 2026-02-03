from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import asyncio
from loguru import logger
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

try:
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider
    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    logger.warning("Pydantic AI no disponible. Usando implementación simulada.")
    PYDANTIC_AI_AVAILABLE = False

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
    tipo: str = Field(..., description="Tipo de recurso (comisaría, juzgado, línea de ayuda)")
    contacto: Optional[str] = Field(None, description="Teléfono, dirección o contacto")
    horario: Optional[str] = Field(None, description="Horario de atención")
    descripcion: str = Field(..., description="Descripción breve del recurso")

class LegalStep(BaseModel):
    """Paso en un procedimiento legal"""
    paso: int = Field(..., description="Número del paso")
    descripcion: str = Field(..., description="Descripción del paso")
    documentos_requeridos: List[str] = Field(default_factory=list, description="Documentos necesarios")
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
    tipo_violencia: List[ViolenceType] = Field(..., description="Tipos de violencia detectados")
    nivel_urgencia: UrgencyLevel = Field(..., description="Nivel de urgencia")
    medidas_inmediatas: List[str] = Field(..., description="Acciones inmediatas a tomar")
    pasos_denuncia: List[LegalStep] = Field(..., description="Pasos para denunciar")
    recursos_disponibles: List[LegalResource] = Field(..., description="Recursos de ayuda")
    advertencias: List[LegalWarning] = Field(..., description="Advertencias importantes")
    fuentes_legales: List[LegalSource] = Field(..., description="Fuentes legales aplicables")
    confianza_respuesta: float = Field(..., ge=0.0, le=1.0, description="Confianza en la respuesta")

class PensionResponse(BaseModel):
    """Respuesta estructurada para pensión de alimentos"""
    tipo_pension: str = Field(..., description="Tipo de pensión")
    obligados: List[str] = Field(..., description="Quiénes están obligados")
    calculo_basico: Optional[str] = Field(None, description="Cálculo básico de la pensión")
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
    advertencias: List[LegalWarning] = Field(..., description="Advertencias importantes")
    fuentes: List[LegalSource] = Field(..., description="Fuentes legales")
    confianza: float = Field(..., ge=0.0, le=1.0, description="Confianza de la respuesta")
    fecha_respuesta: datetime = Field(default_factory=datetime.now)

class LegalAgent:
    """Agente legal con validación Pydantic"""
    
    def __init__(self):
        if PYDANTIC_AI_AVAILABLE:
            self._initialize_pydantic_agent()
        else:
            self.agent = None
            logger.warning("Agente Pydantic no inicializado - usando fallback")
    
    def _initialize_pydantic_agent(self):
        """Inicializa el agente con Pydantic AI"""
        
        # Configurar modelo OpenAI
        model = OpenAIModel('gpt-4',provider= OpenAIProvider(api_key=os.getenv('OPENAI_API_KEY')))
        
        # Definir dependencias
        deps_type = type('Deps', (), {
            'translation_service': None,  # Inyectar servicio de traducción
            'rag_engine': None,           # Inyectar motor RAG
        })()
        
        # Crear agente para violencia familiar
        self.violence_agent = Agent(
            model,
            result_type=ViolenceResponse,
            system_prompt="""Eres un asistente legal especializado en violencia familiar en Perú.
            
            Tu objetivo es proporcionar ayuda inmediata y orientación legal clara.
            
            IMPORTANTE:
            1. Prioriza la seguridad de la persona
            2. Proporciona recursos concretos y locales
            3. Incluye advertencias sobre seguridad
            4. Cita fuentes legales específicas
            5. Sé claro y directo
            
            Responde siempre con la estructura definida por el modelo Pydantic."""
        )
        
        # Crear agente para pensión de alimentos
        self.pension_agent = Agent(
            model,
            result_type=PensionResponse,
            system_prompt="""Eres un asistente legal especializado en pensión de alimentos en Perú.
            
            Tu objetivo es guiar en el proceso de solicitud de pensión.
            
            IMPORTANTE:
            1. Explica el proceso paso a paso
            2. Detalla los documentos necesarios
            3. Menciona los plazos importantes
            4. Proporciona recursos útiles
            5. Cita la legislación aplicable
            
            Responde siempre con la estructura definida por el modelo Pydantic."""
        )
        
        # Crear agente general
        self.general_agent = Agent(
            model,
            result_type=GeneralLegalResponse,
            system_prompt="""Eres un asistente legal bilingüe especializado en derecho familiar peruano.
            
            Tu objetivo es proporcionar orientación legal clara en español y quechua.
            
            IMPORTANTE:
            1. Responde en ambos idiomas
            2. Usa lenguaje sencillo y comprensible
            3. Proporciona pasos concretos
            4. Incluye recursos locales
            5. Añade advertencias importantes
            6. Cita fuentes legales
            
            Responde siempre con la estructura definida por el modelo Pydantic."""
        )
        
        logger.info("Agentes Pydantic AI inicializados correctamente")
    
    async def respond_to_violence(self, query: str, context: Dict[str, Any]) -> ViolenceResponse:
        """Responde a consultas sobre violencia familiar"""
        
        try:
            if PYDANTIC_AI_AVAILABLE and self.violence_agent:
                # Usar Pydantic AI
                result = await self.violence_agent.run(query, deps=context)
                return result.data
            else:
                # Implementación fallback
                return await self._fallback_violence_response(query, context)
                
        except Exception as e:
            logger.error(f"Error en respuesta de violencia: {str(e)}")
            raise
    
    async def respond_to_pension(self, query: str, context: Dict[str, Any]) -> PensionResponse:
        """Responde a consultas sobre pensión de alimentos"""
        
        try:
            if PYDANTIC_AI_AVAILABLE and self.pension_agent:
                result = await self.pension_agent.run(query, deps=context)
                return result.data
            else:
                return await self._fallback_pension_response(query, context)
                
        except Exception as e:
            logger.error(f"Error en respuesta de pensión: {str(e)}")
            raise
    
    async def respond_general(self, query: str, context: Dict[str, Any], language: str = "spanish") -> GeneralLegalResponse:
        """Responde a consultas legales generales"""
        
        try:
            if PYDANTIC_AI_AVAILABLE and self.general_agent:
                result = await self.general_agent.run(query, deps=context)
                return result.data
            else:
                return await self._fallback_general_response(query, context, language)
                
        except Exception as e:
            logger.error(f"Error en respuesta general: {str(e)}")
            raise
    
    async def _fallback_violence_response(self, query: str, context: Dict[str, Any]) -> ViolenceResponse:
        """Implementación fallback para violencia"""
        
        # Detectar palabras clave
        query_lower = query.lower()
        urgency = UrgencyLevel.MEDIO
        
        if any(word in query_lower for word in ["golpe", "agresión", "arma", "peligro"]):
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
                "Acude a la comisaría más cercana"
            ],
            pasos_denuncia=[
                LegalStep(
                    paso=1,
                    descripcion="Acude a la comisaría de Mujeres o fiscalía",
                    documentos_requeridos=["DNI", "pruebas si tienes"],
                    lugar="Comisaría de Mujeres"
                ),
                LegalStep(
                    paso=2,
                    descripcion="Presenta denuncia formal",
                    documentos_requeridos=["Denuncia escrita", "testigos"],
                    plazo="Inmediato"
                )
            ],
            recursos_disponibles=[
                LegalResource(
                    nombre="Línea 113",
                    tipo="Línea de ayuda",
                    contacto="113",
                    horario="24/7 gratuito",
                    descripcion="Atención de emergencia para mujeres"
                )
            ],
            advertencias=[
                LegalWarning(
                    tipo="Seguridad",
                    mensaje="Tu seguridad es lo primero, no arriesgues tu vida",
                    urgencia=UrgencyLevel.CRITICO
                )
            ],
            fuentes_legales=[
                LegalSource(
                    nombre="Ley 30364",
                    tipo="Ley",
                    descripcion="Ley para prevenir, sancionar y erradicar la violencia"
                )
            ],
            confianza_respuesta=0.7
        )
    
    async def _fallback_pension_response(self, query: str, context: Dict[str, Any]) -> PensionResponse:
        """Implementación fallback para pensión"""
        
        return PensionResponse(
            tipo_pension="Alimentos para menores",
            obligados=["Padres", "Abuelos"],
            calculo_basico="Generalmente 25% del ingreso del obligado",
            pasos_proceso=[
                LegalStep(
                    paso=1,
                    descripcion="Reúne documentos",
                    documentos_requeridos=["DNI", "partidas de nacimiento", "pruebas de ingresos"]
                ),
                LegalStep(
                    paso=2,
                    descripcion="Presenta demanda en Juzgado de Familia",
                    documentos_requeridos=["Demanda", "documentos"],
                    lugar="Juzgado de Familia"
                )
            ],
            documentos_necesarios=["DNI", "partidas", "comprobantes de ingresos"],
            plazos=["No hay plazo para solicitar", "Proceso dura 6-12 meses"],
            recursos=[
                LegalResource(
                    nombre="Juzgado de Familia",
                    tipo="Institución judicial",
                    descripcion="Competente en casos de alimentos"
                )
            ],
            advertencias=[
                LegalWarning(
                    tipo="Proceso",
                    mensaje="El proceso puede ser largo, requiere paciencia",
                    urgencia=UrgencyLevel.BAJO
                )
            ],
            fuentes_legales=[
                LegalSource(
                    nombre="Código Civil",
                    tipo="Código",
                    numero="Artículos 472-485",
                    descripcion="Obligación de alimentos"
                )
            ],
            confianza_respuesta=0.6
        )
    
    async def _fallback_general_response(self, query: str, context: Dict[str, Any], language: str) -> GeneralLegalResponse:
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
        spanish_response = "Esta es una respuesta básica en español sobre tu consulta legal."
        quechua_response = "Kay basic respuesta español simipi consulta legal tuyki about."
        
        return GeneralLegalResponse(
            tema=topic,
            respuesta_espanol=spanish_response,
            respuesta_quechua=quechua_response,
            pasos_recomendados=[
                LegalStep(
                    paso=1,
                    descripcion="Consulta con un abogado",
                    documentos_requeridos=["Documentos relevantes"]
                )
            ],
            recursos=[
                LegalResource(
                    nombre="Servicio Legal",
                    tipo="Asesoría",
                    descripcion="Consulta profesional"
                )
            ],
            advertencias=[
                LegalWarning(
                    tipo="General",
                    mensaje="Esto no reemplaza asesoría legal profesional",
                    urgencia=UrgencyLevel.BAJO
                )
            ],
            fuentes=[
                LegalSource(
                    nombre="Código Legal",
                    tipo="Referencia",
                    descripcion="Legislación aplicable"
                )
            ],
            confianza=0.5
        )
    
    def get_agent_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas de los agentes"""
        
        return {
            "pydantic_ai_available": PYDANTIC_AI_AVAILABLE,
            "agents_configured": 3 if PYDANTIC_AI_AVAILABLE else 0,
            "response_types": [
                "violencia_familiar",
                "pension_alimentos", 
                "general_legal"
            ],
            "supported_languages": ["spanish", "quechua"],
            "validation_enabled": True
        }
