"""
Configuración de soporte para idiomas del sistema legal bilingüe
"""

from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path
import json
from loguru import logger

class LanguageCode(Enum):
    """Códigos de idioma soportados"""
    SPANISH = "es"
    QUECHUA = "qu"
    AYMARA = "ay"
    AUTO_DETECT = "auto"

class LanguageConfig:
    """Configuración de idiomas del sistema"""
    
    # Idiomas soportados
    SUPPORTED_LANGUAGES = {
        LanguageCode.SPANISH: {
            "name": "Spanish",
            "native_name": "Español",
            "is_primary": True,
            "legal_documents": True,
            "translation_available": True,
            "models": ["gpt-5-mini", "claude-3"]
        },
        LanguageCode.QUECHUA: {
            "name": "Quechua",
            "native_name": "Quechua (Chanka/Collao)",
            "is_primary": False,
            "legal_documents": False,
            "translation_available": True,
            "models": ["gpt-5-mini", "custom-quechua-model"],
            "variants": ["chanka", "collao", "cusco", "ayacucho", "puno"]
        },
        LanguageCode.AYMARA: {
            "name": "Aymara",
            "native_name": "Aymara Aru",
            "is_primary": False,
            "legal_documents": False,
            "translation_available": True,
            "models": ["gpt-5-mini", "custom-aymara-model"],
            "variants": ["puno", "tacna", "moquegua"]
        }
    }
    
    # Configuración por defecto
    DEFAULT_LANGUAGE = LanguageCode.SPANISH
    FALLBACK_LANGUAGE = LanguageCode.SPANISH
    
    # Configuración de detección
    DETECTION_CONFIDENCE_THRESHOLD = 0.7
    MIN_TEXT_LENGTH_FOR_DETECTION = 10
    
    # Configuración de traducción
    TRANSLATION_MODELS = {
        "nllb": "facebook/nllb-200-distilled-600M",
        "opus": "Helsinki-NLP/opus-mt-es-qu",
        "custom": "models/quechua-translation-v1"
    }
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.custom_config = self._load_custom_config()
        logger.info("LanguageConfig inicializado")
    
    def _load_custom_config(self) -> Dict[str, Any]:
        """Carga configuración personalizada si existe"""
        if self.config_path and Path(self.config_path).exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error cargando configuración personalizada: {e}")
        return {}
    
    def get_language_info(self, language_code: str) -> Optional[Dict[str, Any]]:
        """Obtiene información de un idioma"""
        try:
            lang_enum = LanguageCode(language_code)
            return self.SUPPORTED_LANGUAGES.get(lang_enum)
        except ValueError:
            return None
    
    def is_supported(self, language_code: str) -> bool:
        """Verifica si un idioma está soportado"""
        try:
            LanguageCode(language_code)
            return True
        except ValueError:
            return False
    
    def get_primary_language(self) -> str:
        """Obtiene el idioma primario del sistema"""
        return self.DEFAULT_LANGUAGE.value
    
    def get_translation_pairs(self) -> List[tuple]:
        """Obtiene pares de traducción disponibles"""
        pairs = []
        primary = self.DEFAULT_LANGUAGE
        
        for lang_code, lang_info in self.SUPPORTED_LANGUAGES.items():
            if lang_code != primary and lang_info.get("translation_available", False):
                pairs.append((primary.value, lang_code.value))
                pairs.append((lang_code.value, primary.value))
        
        return pairs
    
    def get_legal_document_languages(self) -> List[str]:
        """Obtiene idiomas con documentos legales disponibles"""
        return [
            lang_code.value 
            for lang_code, lang_info in self.SUPPORTED_LANGUAGES.items()
            if lang_info.get("legal_documents", False)
        ]
    
    def get_variant_info(self, language_code: str, variant: str) -> Optional[Dict[str, Any]]:
        """Obtiene información de una variante de idioma"""
        lang_info = self.get_language_info(language_code)
        if not lang_info:
            return None
        
        variants = lang_info.get("variants", [])
        if variant in variants:
            return {
                "variant": variant,
                "language": language_code,
                "is_supported": True,
                "region": self._get_variant_region(variant)
            }
        
        return None
    
    def _get_variant_region(self, variant: str) -> str:
        """Obtiene región de una variante"""
        region_mapping = {
            "chanka": "Ayacucho, Huancavelica",
            "collao": "Puno, Moquegua, Tacna",
            "cusco": "Cusco, Apurímac",
            "ayacucho": "Ayacucho",
            "puno": "Puno"
        }
        return region_mapping.get(variant, "Región no especificada")
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Obtiene resumen de configuración"""
        return {
            "supported_languages": list(self.SUPPORTED_LANGUAGES.keys()),
            "primary_language": self.DEFAULT_LANGUAGE.value,
            "fallback_language": self.FALLBACK_LANGUAGE.value,
            "translation_pairs": self.get_translation_pairs(),
            "legal_document_languages": self.get_legal_document_languages(),
            "detection_threshold": self.DETECTION_CONFIDENCE_THRESHOLD,
            "custom_config_loaded": bool(self.custom_config)
        }

# Instancia global de configuración
language_config = LanguageConfig()
