"""Adaptador de googletrans que conserva la estructura y las referencias legales."""

import hashlib
import re
from importlib.util import find_spec
from typing import Any

from loguru import logger

from config.settings import settings
from .language_config import LanguageConfig

GOOGLE_TRANSLATE_AVAILABLE = find_spec("googletrans") is not None


# Estructura (saltos de línea, viñetas) y referencias (URL, [n], artículo/ley/decreto, números) que la
# traducción protege con marcadores ZXQREF y restituye tal cual. El harness reutiliza REFERENCE_PATTERN.
STRUCTURE_PATTERN = r"\r?\n[ \t]*(?:\r?\n)*|^[ \t]*(?:[-*]|\d+[.)])[ \t]+"
REFERENCE_PATTERN = (
    r"https?://[^\s]+|\[\d+(?:[,–-]\d+)*\]|(?:artículo|art\.|ley|decreto)\s+[\w.°º-]*\d[\w.°º-]*|\d+(?:[./:-]\d+)*"
)
PROTECTED_PATTERN = STRUCTURE_PATTERN + "|" + REFERENCE_PATTERN


class TranslationService:
    """Servicio de traducción bilingüe especializado (Singleton)"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TranslationService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if TranslationService._initialized:
            return

        self.config = LanguageConfig()
        self.translation_cache = {}
        self.google_translate_available = GOOGLE_TRANSLATE_AVAILABLE
        self.google_translator = None

        TranslationService._initialized = True
        logger.info("✅ TranslationService inicializado (Singleton)")

    async def translate(
        self, text: str, source_lang: str, target_lang: str, model: str = "google_translate"
    ) -> dict[str, Any]:
        """Translate every segment or explicitly fail; never return a truncated success.

        Paragraph whitespace and legal references are protected verbatim. Coverage
        checks do not certify semantic accuracy: specialist review remains necessary.
        Los segmentos sin texto traducible se conservan sin llamar al proveedor.
        """
        failure = {
            "success": False,
            "complete": False,
            "original_text": text,
            "warning": "Traducción no disponible o incompleta; se conserva el texto original.",
        }

        if not self._is_translation_supported(source_lang, target_lang):
            return {**failure, "error": "Unsupported translation pair"}
        if not settings.TRANSLATION_ENABLED:
            return {**failure, "error": "Translation disabled", "method": "none"}
        if not self.google_translate_available:
            return {
                **failure,
                "error": "Translation provider unavailable",
                "method": "none",
            }
        # Conservamos el argumento histórico sin permitir que seleccione un backend inexistente.
        key = (source_lang, target_lang, hashlib.sha256(text.encode()).hexdigest())
        if key in self.translation_cache:
            return dict(self.translation_cache[key])
        protected = []

        def protect(match):
            # Usa marcadores para que el proveedor no reescriba citas ni enlaces.
            protected.append(match.group())
            return f"ZXQREF{len(protected)-1}QXZ"

        prepared = re.sub(
            PROTECTED_PATTERN,
            protect,
            text,
            flags=re.I | re.M,
        )
        parts = re.split(r"(\n[ \t]*\n+)", prepared)
        translated_parts = []
        segment_count = 0
        try:
            for part in parts:
                if not part.strip():
                    translated_parts.append(part)
                    continue
                while part:
                    end = min(4000, len(part))
                    if end < len(part):
                        boundary = max(
                            part.rfind(" ", 0, end), part.rfind("\n", 0, end)
                        )
                        if boundary > 0:
                            end = boundary
                        # Never bisect a protected legal reference.
                        for token in re.finditer(r"ZXQREF\d+QXZ", part):
                            if token.start() < end < token.end():
                                end = token.start() or token.end()
                                break
                    segment, part = part[:end], part[end:]
                    prefix = segment[: len(segment) - len(segment.lstrip())]
                    suffix = segment[len(segment.rstrip()) :]
                    body = segment.strip()
                    if not body:
                        translated_parts.append(segment)
                        continue
                    unprotected = re.sub(r"ZXQREF\d+QXZ", "", body)
                    if not any(char.isalpha() for char in unprotected):
                        translated_parts.append(segment)
                        continue
                    result = await self._translate_with_google(
                        body, source_lang, target_lang
                    )
                    output = result.get("translated_text", "")
                    if (
                        not result.get("success")
                        or not output.strip()
                    ):
                        raise ValueError("Incomplete translation segment")
                    if len(output.strip()) < len(body) * 0.2:
                        raise ValueError("Suspicious translation coverage")
                    for token in re.findall(r"ZXQREF\d+QXZ", body):
                        if output.count(token) != body.count(token):
                            raise ValueError("Lost legal reference")
                    translated_parts.append(prefix + output.strip() + suffix)
                    segment_count += 1
            output = "".join(translated_parts)
            if re.findall(r"ZXQREF\d+QXZ", output) != re.findall(
                r"ZXQREF\d+QXZ", prepared
            ):
                raise ValueError("Legal structure or reference order changed")
            for i, reference in enumerate(protected):
                token = f"ZXQREF{i}QXZ"
                if output.count(token) != 1:
                    raise ValueError("Invalid legal reference coverage")
                output = output.replace(token, reference)
            result = {
                "success": True,
                "complete": True,
                "translated_text": output,
                "source_language": source_lang,
                "target_language": target_lang,
                "method": "google_translate",
                "segments_translated": segment_count,
                "original_length": len(text),
                "review_required": True,
                "warning": "Traducción automática: requiere revisión lingüística y jurídica.",
            }
            # Bounded successful-only cache; failed segments are never cached.
            if len(self.translation_cache) >= 100:
                self.translation_cache.pop(next(iter(self.translation_cache)))
            self.translation_cache[key] = result
            return dict(result)
        except Exception as error:
            logger.error("translation_failed error_type={}", type(error).__name__)
            return {
                **failure,
                "error": "Translation failed",
                "segments_translated": segment_count,
            }

    def _is_translation_supported(self, source_lang: str, target_lang: str) -> bool:
        """Verifica si el par de traducción es soportado"""
        supported_pairs = self.config.get_translation_pairs()
        return (source_lang, target_lang) in supported_pairs

    async def _translate_with_google(
        self, text: str, source_lang: str, target_lang: str
    ) -> dict[str, Any]:
        """Usa Google Translate API para traducción"""
        try:
            if not self.google_translator:
                from googletrans import Translator

                self.google_translator = Translator()

            # Mapeo de códigos de idioma para Google Translate
            google_lang_mapping = {
                "es": "es",
                "qu": "qu",  # Google Translate usa "qu" para quechua
                "quy": "qu",
                "quz": "qu",
                "qul": "qu",
                "ay": "ay",
            }

            src_lang = google_lang_mapping.get(source_lang, source_lang)
            tgt_lang = google_lang_mapping.get(target_lang, target_lang)

            # googletrans 4.0.2 tiene método asíncrono
            result = await self.google_translator.translate(text, src=src_lang, dest=tgt_lang)

            if not result.text or not result.text.strip():
                return {"success": False, "error": "Translation provider returned empty output"}
            # Unchanged text may be valid for names or loanwords, but cannot be
            # certified as a translation; fail closed rather than cache it as one.
            if src_lang != tgt_lang and result.text.strip() == text.strip():
                return {"success": False, "error": "Translation provider returned unchanged text"}

            return {
                "success": True,
                "translated_text": result.text,
                "source_language": source_lang,
                "target_language": target_lang,
                "model_used": "google_translate",
                "method": "google_translate",
            }

        except Exception as e:
            logger.error("translation_provider_failed error_type={}", type(e).__name__)
            return {"success": False, "error": "Translation provider failed"}

    def get_translation_stats(self) -> dict[str, Any]:
        """Obtiene estadísticas del servicio de traducción"""
        return {
            "models_loaded": [],
            "pipelines_available": [],
            "cache_size": len(self.translation_cache),
            "supported_pairs": self.config.get_translation_pairs(),
            "default_model": "google_translate",
            "google_translate_available": self.google_translate_available,
        }

    def clear_cache(self):
        """Limpia el cache de traducciones"""
        self.translation_cache.clear()
        logger.info("Cache de traducciones limpiado")
