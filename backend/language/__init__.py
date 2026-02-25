"""
Módulo de Language Handling - Sistema bilingüe español/quechua
Coordina detección de idioma y traducción para contexto legal rural
"""

from .language_config import LanguageConfig, language_config, LanguageCode
from .language_detector import LanguageDetector, LANGDETECT_AVAILABLE
from typing import Optional, Dict, Any

__all__ = [
    "LanguageConfig",
    "LanguageDetector",
    "TranslationService",
    "language_config",
    "LanguageCode",
    "LanguageHandler",
    "get_language_handler",
]


def __getattr__(name):
    if name == "TranslationService":
        from .translation_service import TranslationService

        return TranslationService
    raise AttributeError(f"module 'language' has no attribute {name!r}")


class LanguageHandler:
    """Clase principal que coordina todos los servicios de lenguaje"""

    def __init__(self):
        self.config = language_config
        self.detector = LanguageDetector()
        from .translation_service import TranslationService

        self.translator = TranslationService()

    async def process_query(
        self, query: str, target_language: Optional[str] = None
    ) -> dict:
        """
        Procesa consulta completa: detección + traducción si es necesario

        Args:
            query: Consulta del usuario
            target_language: Idioma deseado para la respuesta (opcional)

        Returns:
            Diccionario con información procesada
        """
        try:
            # Detectar idioma de la consulta
            detected_lang, confidence = self.detector.detect_with_confidence(query)

            # Obtener perfil lingüístico completo
            language_profile = self.detector.get_language_profile(query)

            result = {
                "original_query": query,
                "detected_language": detected_lang,
                "confidence": confidence,
                "language_profile": language_profile,
                "needs_translation": False,
                "processed_query": query,
            }

            # Si se especificó idioma destino y es diferente al detectado
            if target_language and target_language != detected_lang:
                # Traducir consulta para procesamiento interno
                translation_result = await self.translator.translate(
                    query, detected_lang, target_language
                )

                if translation_result.get("success", False):
                    result["processed_query"] = translation_result["translated_text"]
                    result["needs_translation"] = True
                    result["translation_info"] = {
                        "source": detected_lang,
                        "target": target_language,
                        "confidence": translation_result.get("confidence", 0.0),
                    }

            return result

        except Exception as e:
            return {
                "original_query": query,
                "error": str(e),
                "detected_language": "es",  # Fallback
                "confidence": 0.0,
            }

    async def process_response(
        self,
        response: str,
        source_language: str = "es",
        target_language: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """
        Procesa respuesta para el usuario: traducción si es necesario

        Args:
            response: Respuesta generada
            source_language: Idioma de la respuesta
            target_language: Idioma deseado para el usuario
            context: Contexto adicional para traducción

        Returns:
            Diccionario con respuesta procesada
        """
        try:
            # Si no se especificó idioma destino, usar español por defecto
            if not target_language:
                target_language = self.config.get_primary_language()

            # Si ya está en el idioma destino, retornar original
            if source_language == target_language:
                return {
                    "response": response,
                    "source_language": source_language,
                    "target_language": target_language,
                    "translated": False,
                    "confidence": 1.0,
                }

            # Traducir respuesta
            translation_result = await self.translator.translate_with_context(
                response, source_language, target_language, context
            )

            return {
                "response": translation_result.get("translated_text", response),
                "source_language": source_language,
                "target_language": target_language,
                "translated": translation_result.get("success", False),
                "confidence": translation_result.get("confidence", 0.0),
                "translation_method": translation_result.get("method", "unknown"),
                "context_applied": translation_result.get("context_applied", False),
            }

        except Exception as e:
            return {
                "response": response,
                "source_language": source_language,
                "target_language": target_language,
                "translated": False,
                "error": str(e),
                "confidence": 0.0,
            }

    def get_supported_languages(self) -> dict:
        """Obtiene información de idiomas soportados"""
        return {
            "supported": list(self.config.SUPPORTED_LANGUAGES.keys()),
            "primary": self.config.get_primary_language(),
            "legal_documents": self.config.get_legal_document_languages(),
            "translation_pairs": self.config.get_translation_pairs(),
            "details": {
                code: info for code, info in self.config.SUPPORTED_LANGUAGES.items()
            },
        }

    def get_language_stats(self) -> dict:
        """Obtiene estadísticas de los servicios de lenguaje"""
        return {
            "detector": {
                "method": "automatic" if LANGDETECT_AVAILABLE else "rule_based",
                "supported_languages": len(self.config.SUPPORTED_LANGUAGES),
            },
            "translator": self.translator.get_translation_stats(),
            "config": self.config.get_config_summary(),
        }


_language_handler = None


def get_language_handler() -> LanguageHandler:
    global _language_handler
    if _language_handler is None:
        _language_handler = LanguageHandler()
    return _language_handler
