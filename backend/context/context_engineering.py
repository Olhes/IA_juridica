"""
Orquestador principal de Context Engineering
Coordina chunking, prompts y metadatos culturales para el sistema legal
"""

from typing import Dict, List, Any, Optional, Tuple
import json
from pathlib import Path
from loguru import logger

from .chunking_strategies import ContextualChunker
from .prompt_templates import PromptManager, PromptType
from modules.language.services.language_detector import LanguageDetector

# Mapeo de tipos de consulta a PromptType
_QUERY_TYPE_TO_PROMPT: Dict[str, PromptType] = {
    "violencia_familiar": PromptType.VIOLENCE_FAMILY,
    "pensión_alimentos": PromptType.PENSION_FOOD,
    "identidad": PromptType.IDENTITY_RIGHTS,
    "demanda": PromptType.GENERAL_LEGAL,
    "general": PromptType.GENERAL_LEGAL,
}


class ContextEngineer:
    """Orquestador principal de Context Engineering"""

    def __init__(self, cultural_db_path: Optional[str] = None):
        self.chunker = ContextualChunker()
        self.prompt_manager = PromptManager()
        self.language_detector = LanguageDetector()

        # Base de datos cultural local
        self.cultural_db = self._load_cultural_database(cultural_db_path)

        # Cache de contextos procesados
        self.context_cache = {}

        logger.info("ContextEngineer inicializado")

    def _load_cultural_database(self, db_path: Optional[str]) -> Dict[str, Any]:
        """Carga base de datos cultural local"""
        default_db = {
            "communities": {
                "cusco": {
                    "juzgado": "Juzgado de Paz Letrado del Cusco",
                    "comisaria": "Comisaría de la Mujer del Cusco",
                    "mimp": "Centro de Emergencia Mujer Cusco",
                    "reniec": "Oficina RENIEC Cusco",
                    "cultural_notes": "Alta presencia quechua, tradiciones fuertes",
                },
                "puno": {
                    "juzgado": "Juzgado de Paz Letrado de Puno",
                    "comisaria": "Comisaría de la Mujer de Puno",
                    "mimp": "CEM Puno",
                    "reniec": "Oficina RENIEC Puno",
                    "cultural_notes": "Zona altiplánica, idioma aymara también presente",
                },
                "ayacucho": {
                    "juzgado": "Juzgado de Paz Letrado de Ayacucho",
                    "comisaria": "Comisaría de la Mujer Ayacucho",
                    "mimp": "CEM Ayacucho",
                    "reniec": "Oficina RENIEC Ayacucho",
                    "cultural_notes": "Quechua ayacuchano, fuerte identidad campesina",
                },
                "huancavelica": {
                    "juzgado": "Juzgado de Paz Letrado de Huancavelica",
                    "comisaria": "Comisaría de la Mujer Huancavelica",
                    "mimp": "CEM Huancavelica",
                    "reniec": "Oficina RENIEC Huancavelica",
                    "cultural_notes": "Zona rural alta, difícil acceso a servicios",
                },
            },
            "cultural_protocols": {
                "violencia": {
                    "approach": "Seguridad primero, luego comunidad",
                    "considerations": [
                        "Miedo a romper unidad familiar",
                        "Dependencia económica del agresor",
                        "Barreras geográficas para denunciar",
                    ],
                },
                "documentos": {
                    "approach": "Autoridades locales como facilitadoras",
                    "considerations": [
                        "Dificultad para conseguir documentos básicos",
                        "Desconfianza de instituciones estatales",
                        "Falta de transporte a oficinas lejanas",
                    ],
                },
            },
            "legal_resources": {
                "free_services": [
                    "Defensoría Pública del Pueblo",
                    "Consultorios Jurídicos Gratuitos de universidades",
                    "Servicios del MIMP",
                    "Oficinas de la Defensoría Municipal",
                ],
                "emergency_contacts": {
                    "nacional_police": "113",
                    "women_emergency": "113",
                    "legal_aid": "0800-12345",
                },
            },
        }

        if db_path and Path(db_path).exists():
            try:
                with open(db_path, "r", encoding="utf-8") as f:
                    custom_db = json.load(f)
                    # Combinar con base por defecto
                    default_db.update(custom_db)
                    logger.info(f"Base de datos cultural cargada desde {db_path}")
            except Exception as e:
                logger.warning(f"Error cargando base cultural personalizada: {e}")

        return default_db

    def process_document_with_context(
        self, content: str, metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Procesa documento con chunking contextual y metadatos culturales

        Args:
            content: Contenido del documento
            metadata: Metadatos del documento

        Returns:
            Lista de chunks enriquecidos con contexto
        """
        try:
            # Detectar idioma del documento
            doc_language = self.language_detector.detect_language(content)

            # Agregar información de idioma a metadatos
            metadata["detected_language"] = doc_language

            # Procesar con chunking contextual
            chunks = self.chunker.process_document(content, metadata)

            # Enriquecer cada chunk con contexto cultural
            for chunk in chunks:
                chunk = self._enrich_chunk_with_cultural_context(chunk)
                chunk = self._add_legal_context_to_chunk(chunk)

            logger.info(
                f"Documento procesado: {len(chunks)} chunks con contexto cultural"
            )
            return chunks

        except Exception as e:
            logger.error(f"Error procesando documento con contexto: {str(e)}")
            raise

    def _enrich_chunk_with_cultural_context(
        self, chunk: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enriquece chunk con contexto cultural"""

        content = chunk.get("content", "").lower()
        cultural_context = {
            "rural_relevance": self._assess_rural_relevance(content),
            "cultural_sensitivity": self._assess_cultural_sensitivity(content),
            "community_resources": self._identify_community_resources(content),
            "barriers": self._identify_access_barriers(content),
        }

        chunk["cultural_context"] = cultural_context
        return chunk

    def _assess_rural_relevance(self, content: str) -> Dict[str, Any]:
        """Evalúa relevancia rural del contenido"""

        rural_indicators = {
            "agricultura": ["agricultura", "siembra", "cosecha", "ganado", "tierra"],
            "comunidad": ["comunidad", "ayllu", "pueblo", "vecinos", "autoridad local"],
            "acceso": ["distancia", "camino", "transporte", "acceso", "lejos"],
            "servicios": ["puesto de salud", "escuela", "comisaría", "juzgado"],
        }

        relevance_scores = {}
        for category, keywords in rural_indicators.items():
            score = sum(1 for keyword in keywords if keyword in content)
            relevance_scores[category] = {
                "score": score,
                "max_possible": len(keywords),
                "percentage": (score / len(keywords)) * 100,
            }

        return relevance_scores

    def _assess_cultural_sensitivity(self, content: str) -> Dict[str, Any]:
        """Evalúa sensibilidad cultural requerida"""

        sensitive_topics = {
            "familia": ["familia", "hijos", "esposo", "esposa", "matrimonio"],
            "autoridad": ["autoridad", "gobierno", "policía", "juez"],
            "tradicion": ["tradición", "costumbre", "usos", "prácticas"],
            "religión": ["dios", "iglesia", "fe", "oración", "pachamama"],
        }

        sensitivity_level = "low"
        found_topics = []

        for topic, keywords in sensitive_topics.items():
            if any(keyword in content for keyword in keywords):
                found_topics.append(topic)

        if len(found_topics) >= 3:
            sensitivity_level = "high"
        elif len(found_topics) >= 2:
            sensitivity_level = "medium"

        return {
            "level": sensitivity_level,
            "topics": found_topics,
            "requires_cultural_adaptation": sensitivity_level != "low",
        }

    def _identify_community_resources(self, content: str) -> List[str]:
        """Identifica recursos comunitarios mencionados"""

        resource_patterns = {
            "autoridad_local": [
                "gobernador",
                "teniente gobernador",
                "alcalde",
                "varayoc",
            ],
            "servicio_social": [
                "puesto de salud",
                "centro de salud",
                "comedor popular",
            ],
            "educativo": ["escuela", "colegio", "instituto", "universidad"],
            "religioso": ["iglesia", "templo", "pastor", "cura"],
        }

        found_resources = []
        for resource_type, patterns in resource_patterns.items():
            for pattern in patterns:
                if pattern in content:
                    found_resources.append(f"{resource_type}: {pattern}")

        return found_resources

    def _identify_access_barriers(self, content: str) -> List[str]:
        """Identifica barreras de acceso mencionadas"""

        barrier_indicators = {
            "geográficas": ["lejos", "distante", "camino difícil", "sin transporte"],
            "económicas": ["caro", "no tengo dinero", "pobreza", "no puedo pagar"],
            "idioma": ["no entiendo", "idioma", "traducción", "quechua"],
            "educativas": [
                "no sé leer",
                "no sé escribir",
                "analfabeto",
                "sin estudios",
            ],
        }

        identified_barriers = []
        for barrier_type, indicators in barrier_indicators.items():
            for indicator in indicators:
                if indicator in content:
                    identified_barriers.append(f"{barrier_type}: {indicator}")

        return identified_barriers

    def _add_legal_context_to_chunk(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Agrega contexto legal específico"""

        content = chunk.get("content", "").lower()

        # Detectar tipo legal
        legal_type = self._detect_legal_type(content)

        # Extraer entidades legales
        legal_entities = self._extract_legal_entities(content)

        # Identificar plazos y procedimientos
        procedures = self._identify_procedures(content)

        chunk["legal_context"] = {
            "type": legal_type,
            "entities": legal_entities,
            "procedures": procedures,
            "urgency": self._assess_urgency(content),
        }

        return chunk

    def _detect_legal_type(self, content: str) -> str:
        """Detecta tipo de procedimiento legal"""

        type_patterns = {
            "violencia_familiar": [
                "violencia",
                "maltrato",
                "agresión",
                "protección",
                "medida",
            ],
            "pensión_alimentos": ["pensión", "alimentos", "hijos", "obligado", "pago"],
            "identidad": ["dni", "nacimiento", "inscripción", "reniec", "nombre"],
            "demanda": ["demanda", "proceso", "juicio", "juzgado", "demandante"],
        }

        for legal_type, patterns in type_patterns.items():
            if any(pattern in content for pattern in patterns):
                return legal_type

        return "general"

    def _extract_legal_entities(self, content: str) -> List[str]:
        """Extrae entidades legales del contenido"""

        entity_patterns = {
            "instituciones": [
                "juzgado",
                "comisaría",
                "mimp",
                "reniec",
                "municipalidad",
            ],
            "documentos": ["dni", "partida", "certificado", "demanda", "testimonio"],
            "autoridades": ["juez", "fiscal", "abogado", "gobernador", "alcalde"],
        }

        found_entities = []
        for entity_type, patterns in entity_patterns.items():
            for pattern in patterns:
                if pattern in content:
                    found_entities.append(f"{entity_type}: {pattern}")

        return found_entities

    def _identify_procedures(self, content: str) -> List[str]:
        """Identifica procedimientos legales mencionados"""

        procedure_keywords = [
            "denunciar",
            "demandar",
            "solicitar",
            "presentar",
            "inscribir",
            "tramitar",
            "pedir",
            "reclamar",
            "apelar",
            "interponer",
        ]

        found_procedures = []
        for keyword in procedure_keywords:
            if keyword in content:
                found_procedures.append(keyword)

        return found_procedures

    def _assess_urgency(self, content: str) -> str:
        """Evalúa nivel de urgencia del contenido"""

        high_urgency = [
            "urgente",
            "inmediato",
            "emergencia",
            "peligro",
            "violencia",
            "agresión",
        ]
        medium_urgency = ["importante", "necesario", "pronto", "rápido", "debería"]

        if any(word in content for word in high_urgency):
            return "high"
        elif any(word in content for word in medium_urgency):
            return "medium"
        else:
            return "low"

    def get_contextualized_prompt(
        self, query: str, agent_type: str, user_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Genera prompt contextualizado para un agente

        Args:
            query: Consulta del usuario
            agent_type: Tipo de agente
            user_context: Contexto del usuario

        Returns:
            Tuple con prompt y contexto enriquecido
        """
        try:
            # Detectar idioma de la consulta
            query_language = self.language_detector.detect_language(query)

            # Detectar ubicación si se menciona
            detected_location = self._detect_location(query)

            # Construir contexto enriquecido
            enriched_context = {
                "query_language": query_language,
                "detected_location": detected_location,
                "legal_topic": self._detect_legal_type(query.lower()),
                "urgency_level": self._assess_urgency(query.lower()),
                "cultural_context": self._assess_cultural_sensitivity(query.lower()),
            }

            # Agregar contexto del usuario si se proporciona
            if user_context:
                enriched_context.update(user_context)

            # Agregar información cultural de la ubicación
            if (
                detected_location
                and detected_location in self.cultural_db["communities"]
            ):
                enriched_context["location_info"] = self.cultural_db["communities"][
                    detected_location
                ]

            # Obtener prompt apropiado
            language_for_prompt = (
                "quechua" if query_language == "qu" else query_language
            )
            prompt = self.prompt_manager.get_system_prompt(
                agent_type=agent_type,
                language=language_for_prompt,
                context=enriched_context,
            )

            return prompt, enriched_context

        except Exception as e:
            logger.error(f"Error generando prompt contextualizado: {str(e)}")
            # Fallback a prompt básico
            return self.prompt_manager.get_system_prompt(agent_type), {}

    def build_legal_prompt(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        language: str = "spanish",
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Construye prompt legal optimizado para Cohere con contexto cultural.

        Integra: clasificación de consulta → detección de ubicación →
        enriquecimiento cultural → PromptManager.build_prompt_for_cohere()

        Args:
            query: Consulta del usuario
            documents: Documentos rerankeados desde query_with_rerank()
            language: Idioma de respuesta

        Returns:
            Tuple (prompt_completo, contexto_enriquecido)
        """
        try:
            # 1. Detectar idioma de la consulta
            query_language = self.language_detector.detect_language(query)
            if query_language == "qu":
                language = "quechua"

            # 2. Clasificar tipo de consulta
            query_lower = query.lower()
            legal_type = self._detect_legal_type(query_lower)
            prompt_type = _QUERY_TYPE_TO_PROMPT.get(
                legal_type, PromptType.GENERAL_LEGAL
            )

            # 3. Detectar ubicación
            detected_location = self._detect_location(query)

            # 4. Evaluar urgencia y sensibilidad cultural
            urgency = self._assess_urgency(query_lower)
            cultural_sensitivity = self._assess_cultural_sensitivity(query_lower)

            # 5. Construir contexto enriquecido
            enriched_context = {
                "query_language": query_language,
                "detected_location": detected_location,
                "legal_topic": legal_type,
                "urgency_level": urgency,
                "cultural_context": cultural_sensitivity,
            }

            # Agregar info cultural de la ubicación
            if (
                detected_location
                and detected_location in self.cultural_db["communities"]
            ):
                enriched_context["location_info"] = self.cultural_db["communities"][
                    detected_location
                ]

            # 6. Construir prompt con PromptManager
            prompt = self.prompt_manager.build_prompt_for_cohere(
                prompt_type=prompt_type,
                query=query,
                documents=documents,
                language=language,
                user_location=detected_location,
                enriched_context=enriched_context,
            )

            logger.info(
                f"Prompt construido: tipo={legal_type}, ubicación={detected_location}, "
                f"urgencia={urgency}, docs={len(documents)}"
            )

            return prompt, enriched_context

        except Exception as e:
            logger.error(f"Error construyendo prompt legal: {e}")
            # Fallback: prompt básico sin enriquecimiento
            basic_prompt = self.prompt_manager.get_system_prompt("general", language)
            return f"{basic_prompt}\n\nConsulta: {query}", {}

    def _detect_location(self, text: str) -> Optional[str]:
        """Detecta mención de ubicaciones conocidas"""

        locations = {
            "cusco": ["cusco", "cusco", "qosqo"],
            "puno": ["puno", "lago titicaca", "juliaca"],
            "ayacucho": ["ayacucho", "huamanga"],
            "huancavelica": ["huancavelica", "huancavélica"],
            "ancash": ["ancash", "huaraz", "chimbote"],
            "apurimac": ["apurímac", "abancay"],
            "arequipa": ["arequipa", "cañón del colca"],
        }

        text_lower = text.lower()
        for location, variants in locations.items():
            if any(variant in text_lower for variant in variants):
                return location

        return None

    def get_cultural_recommendations(self, context: Dict[str, Any]) -> List[str]:
        """
        Obtiene recomendaciones culturales basadas en el contexto

        Args:
            context: Contexto de la consulta

        Returns:
            Lista de recomendaciones culturales
        """
        recommendations = []

        # Recomendaciones por ubicación
        location = context.get("detected_location")
        if location and location in self.cultural_db["communities"]:
            location_info = self.cultural_db["communities"][location]
            recommendations.append(
                f"Considerar contexto cultural: {location_info.get('cultural_notes', '')}"
            )

        # Recomendaciones por sensibilidad cultural
        cultural_sensitivity = context.get("cultural_context", {})
        if cultural_sensitivity.get("requires_cultural_adaptation"):
            recommendations.append("Usar adaptador cultural para esta respuesta")

        # Recomendaciones por urgencia
        urgency = context.get("urgency_level", "low")
        if urgency == "high":
            recommendations.append("Priorizar seguridad y acción inmediata")

        # Recomendaciones por idioma
        if context.get("query_language") == "quechua":
            recommendations.append("Responder en quechua y español")
            recommendations.append("Usar términos culturales apropiados")

        return recommendations

    def validate_response_cultural_appropriateness(
        self, response: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Valida que una respuesta sea culturalmente apropiada

        Args:
            response: Respuesta generada
            context: Contexto original

        Returns:
            Resultado de validación cultural
        """
        validation_result = {
            "is_appropriate": True,
            "issues": [],
            "recommendations": [],
            "cultural_score": 0.0,
        }

        # Evaluar sensibilidad cultural
        if context.get("cultural_context", {}).get("requires_cultural_adaptation"):
            cultural_terms = ["ayllu", "comunidad", "tradición", "costumbre"]
            if not any(term in response.lower() for term in cultural_terms):
                validation_result["issues"].append("Falta sensibilidad cultural")
                validation_result["recommendations"].append(
                    "Incluir términos culturales"
                )
                validation_result["cultural_score"] -= 0.3

        # Evaluar idioma apropiado
        if context.get("query_language") == "quechua":
            if not self._has_quechua_content(response):
                validation_result["issues"].append("Respuesta no incluye quechua")
                validation_result["recommendations"].append(
                    "Agregar traducción al quechua"
                )
                validation_result["cultural_score"] -= 0.4

        # Evaluar complejidad del lenguaje
        if self._is_too_complex(response):
            validation_result["issues"].append("Lenguaje demasiado complejo")
            validation_result["recommendations"].append("Simplificar el lenguaje")
            validation_result["cultural_score"] -= 0.2

        # Calcular score final
        validation_result["cultural_score"] = max(
            0.0, validation_result["cultural_score"] + 0.7
        )

        return validation_result

    def _has_quechua_content(self, text: str) -> bool:
        """Verifica si el texto tiene contenido en quechua"""
        quechua_indicators = [
            "ñuqa",
            "qam",
            "pay",
            "ñuqanchik",
            "qamkuna",
            "paykuna",
            "kani",
            "kanki",
            "kanku",
        ]
        return any(indicator in text.lower() for indicator in quechua_indicators)

    def _is_too_complex(self, text: str) -> bool:
        """Evalúa si el texto es demasiado complejo para contexto rural"""

        # Indicadores de complejidad
        complex_words = [
            "constitucional",
            "jurisdicción",
            "competencia",
            "imperativo",
            "inherente",
        ]
        long_sentences = len([s for s in text.split(".") if len(s.split()) > 20])

        complexity_score = sum(1 for word in complex_words if word in text.lower())

        return complexity_score > 2 or long_sentences > 3

    def get_context_engineering_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del sistema de Context Engineering"""
        return {
            "cultural_database_size": len(self.cultural_db["communities"]),
            "supported_locations": list(self.cultural_db["communities"].keys()),
            "available_prompts": self.prompt_manager.get_all_templates_info(),
            "cache_size": len(self.context_cache),
            "cultural_protocols": list(self.cultural_db["cultural_protocols"].keys()),
        }
