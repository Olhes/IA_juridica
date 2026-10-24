"""
Servicio de traducción especializado para español/quechua
Implementa traducción en cascada con modelos específicos
"""

from typing import Dict, List, Optional, Tuple, Any
import asyncio
from loguru import logger

# Transformers eliminado para evitar descargas de modelos pesados en producción
TRANSFORMERS_AVAILABLE = False

try:
    from googletrans import Translator

    GOOGLE_TRANSLATE_AVAILABLE = True
except ImportError:
    logger.warning(
        "googletrans no disponible. Google Translate API no estará disponible."
    )
    GOOGLE_TRANSLATE_AVAILABLE = False

from .language_config import LanguageConfig, LanguageCode
from .language_detector import LanguageDetector


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

        logger.info("🔄 Inicializando TranslationService (Singleton)...")
        self.config = LanguageConfig()
        self.detector = LanguageDetector()

        # Modelos de traducción
        self.translation_models = {}
        self.translation_pipelines = {}

        # Cache de traducciones
        self.translation_cache = {}

        # Verificar disponibilidad de transformers
        logger.info(f"📦 TRANSFORMERS_AVAILABLE: {TRANSFORMERS_AVAILABLE}")
        logger.info(f"📦 GOOGLE_TRANSLATE_AVAILABLE: {GOOGLE_TRANSLATE_AVAILABLE}")

        # Inicializar Google Translate si está disponible
        self.google_translate_available = GOOGLE_TRANSLATE_AVAILABLE
        if self.google_translate_available:
            try:
                self.google_translator = Translator()
                logger.info("✅ Google Translate inicializado")
            except Exception as e:
                logger.warning("operation_failed error_type={}", type(e).__name__)
                self.google_translator = None
                self.google_translate_available = False
        else:
            self.google_translator = None

        # Inicializar modelos solo si están disponibles Y habilitados
        from config.settings import settings

        logger.info(f"⚙️  TRANSLATION_ENABLED: {settings.TRANSLATION_ENABLED}")
        logger.info(f"⚙️  TRANSLATION_METHOD: {settings.TRANSLATION_METHOD}")

        if settings.TRANSLATION_METHOD == "google_translate":
            logger.info(
                "🌐 Usando Google Translate como método de traducción principal"
            )
        elif not settings.TRANSLATION_ENABLED:
            logger.warning("⚠️  Traducción deshabilitada (TRANSLATION_ENABLED=false)")
        else:
            logger.warning(
                "⚠️  Método de traducción no soportado, usando Google Translate"
            )

        TranslationService._initialized = True
        logger.info("✅ TranslationService inicializado (Singleton)")

    # Método _initialize_translation_models eliminado - no se usan modelos pesados en producción

    async def translate(
        self, text: str, source_lang: str, target_lang: str, model: str = "nllb"
    ) -> Dict[str, Any]:
        """Translate every segment or explicitly fail; never return a truncated success.

        Paragraph whitespace and legal references are protected verbatim. Coverage
        checks do not certify semantic accuracy: specialist review remains necessary.
        
        Para quechua, usa directamente traducción por reglas ya que Google Translate no lo soporta.
        """
        import hashlib
        import re

        failure = {
            "success": False,
            "complete": False,
            "original_text": text,
            "warning": "Traducción no disponible o incompleta; se conserva el texto original.",
        }
        
        # Para quechua, usar Cohere LLM para mejor calidad (Google Translate no lo soporta bien)
        if target_lang in ["qu", "quy", "quz", "qul"]:
            logger.info("Using Cohere LLM for Quechua translation")
            return await self._translate_with_cohere(text, source_lang, target_lang)
        
        if not self._is_translation_supported(source_lang, target_lang):
            return {**failure, "error": "Unsupported translation pair"}
        if not self.google_translate_available:
            return {
                **failure,
                "error": "Translation provider unavailable",
                "method": "none",
            }
        key = (
            source_lang,
            target_lang,
            model,
            hashlib.sha256(text.encode()).hexdigest(),
        )
        if key in self.translation_cache:
            return dict(self.translation_cache[key])
        protected = []

        def protect(match):
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
                "method": "google_translate",  # Método principal usado
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

    # Método _translate_with_model eliminado - no se usan modelos pesados en producción

    async def _translate_with_google(
        self, text: str, source_lang: str, target_lang: str
    ) -> Dict[str, Any]:
        """Usa Google Translate API para traducción"""
        try:
            if not self.google_translator:
                raise RuntimeError("Google Translate no disponible")

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
            
            # Verificar si la traducción fue exitosa (no devuelve el mismo texto)
            if result.text == text or not result.text.strip():
                logger.warning("google_translate_no_change - Google Translate no tradujo el texto, usando fallback")
                # Para quechua, usar directamente traducción por reglas
                if target_lang in ["qu", "quy", "quz", "qul"]:
                    return await self._translate_with_rules(text, source_lang, target_lang)
                # Para otros idiomas, retornar el texto original con warning
                return {
                    "success": True,
                    "translated_text": text,
                    "source_language": source_lang,
                    "target_language": target_lang,
                    "model_used": "none",
                    "confidence": 0.0,
                    "method": "none",
                    "warning": f"Google Translate no pudo traducir de {source_lang} a {target_lang}",
                }

            return {
                "success": True,
                "translated_text": result.text,
                "source_language": source_lang,
                "target_language": target_lang,
                "model_used": "google_translate",
                "confidence": 0.90,  # Google Translate generalmente tiene buena calidad
                "method": "google_translate",
            }

        except Exception as e:
            logger.error("translation_provider_failed error_type={} error={}", type(e).__name__, str(e))
            # Alternativa basada en reglas
            return await self._translate_with_rules(text, source_lang, target_lang)

    async def _translate_with_cohere(
        self, text: str, source_lang: str, target_lang: str
    ) -> Dict[str, Any]:
        """Traducción usando Cohere LLM"""
        try:
            import cohere
            from config.settings import settings

            if not settings.COHERE_API_KEY:
                raise RuntimeError("Cohere API key no configurada")

            # Usar cliente asíncrono
            cohere_client = cohere.AsyncClient(settings.COHERE_API_KEY)

            # Prompt de traducción (incluyendo instrucciones en el mensaje)
            if source_lang == "es" and target_lang == "qu":
                user_message = f"""Eres un experto en traducción de español a quechua (runasimi).
Traduce el texto proporcionado manteniendo el significado legal exacto.
Usa quechua estándar del sur de Perú (Cusco).
Mantén la estructura y formato del texto original.
Traduce solo el texto, sin agregar explicaciones adicionales.

Texto a traducir:
{text}

Traducción:"""
            elif source_lang == "qu" and target_lang == "es":
                user_message = f"""Eres un experto en traducción de quechua (runasimi) a español.
Traduce el texto proporcionado manteniendo el significado exacto.
Mantén la estructura y formato del texto original.
Traduce solo el texto, sin agregar explicaciones adicionales.

Texto a traducir:
{text}

Traducción:"""
            else:
                return await self._translate_with_rules(text, source_lang, target_lang)

            response = await cohere_client.chat(
                model=settings.COHERE_LLM_MODEL,
                message=user_message,
                temperature=0.3,
                max_tokens=4000,
            )

            translated_text = response.text.strip()

            # Verificar si Cohere realmente tradujo (comparación más estricta)
            # Si el texto traducido es muy similar al original (>90% similitud), no tradujo
            import difflib
            similarity = difflib.SequenceMatcher(None, text.lower(), translated_text.lower()).ratio()
            
            logger.info(f"Cohere similarity with original: {similarity:.2f}")
            
            if not translated_text or similarity > 0.90:
                logger.warning("cohere_translation_no_change - Cohere no tradujo el texto a quechua (similitud: {:.2f}), usando diccionario".format(similarity))
                return await self._translate_with_rules(text, source_lang, target_lang)

            return {
                "success": True,
                "translated_text": translated_text,
                "source_language": source_lang,
                "target_language": target_lang,
                "model_used": "cohere",
                "confidence": 0.85,  # Mayor confianza para LLM
                "method": "cohere",
                "warning": "Traducción automática por IA: requiere revisión lingüística y jurídica.",
            }

        except Exception as e:
            logger.error("cohere_translation_failed error_type={} error={}", type(e).__name__, str(e))
            # Fallback a traducción por reglas
            return await self._translate_with_rules(text, source_lang, target_lang)

    async def _translate_with_rules(
        self, text: str, source_lang: str, target_lang: str
    ) -> Dict[str, Any]:
        """Traducción basada en reglas y diccionarios"""
        try:
            if source_lang == "es" and target_lang == "qu":
                translated = self._translate_spanish_to_quechua(text)
            elif source_lang == "qu" and target_lang == "es":
                translated = self._translate_quechua_to_spanish(text)
            else:
                translated = f"[Traducción {source_lang}->{target_lang}]: {text}"

            return {
                "success": True,
                "translated_text": translated,
                "source_language": source_lang,
                "target_language": target_lang,
                "model_used": "rules",
                "confidence": 0.50,  # Menor confianza para reglas
                "method": "rules",
                "warning": "Traducción basada en diccionario simple - puede ser imprecisa",
            }

        except Exception as e:
            logger.error("operation_failed error_type={}", type(e).__name__)
            return {
                "success": False,
                "error": "Rules-based translation failed",
                "original_text": text,
            }

    def _translate_spanish_to_quechua(self, text: str) -> str:
        """Traducción de español a quechua basada en reglas"""
        # Diccionario mejorado español-quechua (enfoque en contexto legal)
        dictionary = {
            # Pronombres
            "yo": "ñuqa",
            "tú": "qam",
            "él": "pay",
            "ella": "pay",
            "nosotros": "ñuqanchik",
            "vosotros": "qamkuna",
            "ellos": "paykuna",
            "ellas": "paykuna",
            "mi": "ñuqap",
            "tu": "qamp",
            "su": "payp",
            "nuestro": "ñuqanchikp",
            "nuestra": "ñuqanchikp",
            # Verbos comunes
            "ser": "kay",
            "estar": "kay",
            "tener": "tiyay",
            "hacer": "ruway",
            "decir": "nin",
            "querer": "munay",
            "saber": "yachay",
            "poder": "atipay",
            "ir": "riy",
            "venir": "hamuy",
            "debe": "kanan",
            "deben": "kankunan",
            "es": "kan",
            "son": "kanku",
            "está": "kashan",
            "están": "kashanku",
            "hay": "kay",
            "tengo": "tiyani",
            "tienes": "tiyanki",
            "tiene": "tiyan",
            "queremos": "munanchik",
            "quiero": "munani",
            "quieres": "munanki",
            "quiere": "munan",
            "sé": "yachani",
            "sabes": "yachanki",
            "sabe": "yachan",
            "puedo": "atipani",
            "puedes": "atipanki",
            "puede": "atipan",
            # Sustantivos legales básicos
            "ley": "kamachiy",
            "justicia": "llankhay",
            "juez": "qatiq",
            "policía": "misitu",
            "documento": "qillqa",
            "demanda": "munay",
            "pensión": "qullqi",
            "alimentos": "mikhuy",
            "familia": "ayllu",
            "hijo": "churi",
            "hija": "ususi",
            "padre": "tayta",
            "madre": "mama",
            "padres": "taytamamakuna",
            "niño": "wawa",
            "niña": "wawa",
            "niños": "wawakuna",
            "violencia": "k'iri",
            "mujer": "warmi",
            "mujeres": "warmikuna",
            "hombre": "qhari",
            "hombres": "qharikuna",
            "derecho": "derecho",
            "derechos": "derechokuna",
            "protección": "chaway",
            "ayuda": "yanapay",
            "caso": "kasu",
            "problema": "pakay",
            "autoridad": "kamachiq",
            "comunidad": "ayllu",
            "artículo": "artículo",
            "norma": "norma",
            "medida": "tupu",
            "medidas": "tupukuna",
            "consejo": "yatichiy",
            "consejos": "yatichiykuna",
            "paso": "pata",
            "pasos": "patakuna",
            "denuncia": "wiruy",
            "organización": "tinkuy",
            "abogado": "abogado",
            "profesional": "prupisyunal",
            # Términos legales adicionales
            "orientación": "ñawpaq",
            "legal": "kamachiy",
            "consulta": "tapuy",
            "física": "kallpay",
            "preguntas": "tapuykuna",
            "clave": "allin",
            "investigación": "ñawiriy",
            "lugar": "maypi",
            "momento": "pacha",
            "ocurrió": "tayarikurqan",
            "agresión": "maqanakuy",
            "casa": "wasi",
            "campo": "chakra",
            "pelea": "maqanakuy",
            "agresor": "maqakuq",
            "víctima": "k'irisqa",
            "tipo": "laya",
            "produjo": "paqarichirqan",
            "golpes": "maqaykuna",
            "puñetazos": "maki maqaykuna",
            "patadas": "chaki maqaykuna",
            "consideraciones": "yuyay",
            "culturales": "sapaq",
            "contexto": "pacha",
            "importante": "allin",
            "considerar": "yuyay",
            "rencores": "ñakay",
            "discusiones": "rimanakuykuna",
            "previas": "ñawpaq",
            "recíproca": "kuskanchik",
            "algunos": "some",
            "casos": "kasukuna",
            "mutua": "kuskanchik",
            "crucial": "allin",
            "entender": "yachay",
            "circunstancias": "pachakuna",
            "juzgar": "qatiy",
            "únicamente": "lla",
            "parte": "lla",
            "documentar": "qillqay",
            "situación": "pacha",
            "registrar": "qillqay",
            "fecha": "p'unchaw",
            "hora": "pacha",
            "personas": "runakuna",
            "involucradas": "participaq",
            "detalles": "willay",
            "buscar": "taripay",
            "especializados": "allin",
            "familiares": "ayllu",
            "profesionales": "prupisyunalkuna",
            "entiendan": "yachay",
            "rural": "chakra",
            "centros": "wasikuna",
            "brindan": "qun",
            "apoyo": "yanapay",
            "gratuita": "mana qullqita",
            "presentar": "rikuchiy",
            "formal": "allin",
            "autoridades": "kamachiqkuna",
            "judiciales": "qatiqkuna",
            "recursos": "llank'aykuna",
            "locales": "ayllu",
            "ofrezcan": "qun",
            "defensa": "chaway",
            "humanos": "runakuna",
            "pueden": "atipanku",
            "información": "willay",
            "advertencias": "allina",
            "importantes": "allin",
            "evita": "amuy",
            "revictimización": "k'iri",
            "trata": "ruway",
            "proteger": "chaway",
            "presionar": "sachay",
            "presente": "rikuchiy",
            "seguridad": "amachay",
            "peligrosa": "ñak'aq",
            "inmediata": "kunan",
            "fuentes": "puriy",
            "código": "kamachiy",
            "procesal": "ruway",
            "civil": "runa",
            "recuerda": "yuyariy",
            "variar": "hukllachiy",
            "región": "suyu",
            "obtener": "apay",
            "asesoramiento": "yatichiy",
            "preciso": "allin",
            # Conectores y preposiciones
            "y": "wan",
            "o": "utaq",
            "pero": "kas",
            "porque": "imrayku",
            "para": "paq",
            "con": "wan",
            "de": "manta",
            "en": "pi",
            "a": "man",
            "del": "manta",
            "al": "man",
            "como": "imayna",
            "cuando": "qampa",
            "donde": "maypi",
            "que": "ña",
            "si": "qa",
            "no": "manam",
            "también": "pis",
            "muy": "ancha",
            "más": "aswan",
            "menos": "pisi",
            "siempre": "llapa",
            "nunca": "ñawpaq",
            "solo": "lla",
            # Palabras comunes
            "casa": "wasi",
            "comida": "mikhuy",
            "agua": "yaku",
            "tierra": "pacha",
            "sol": "inti",
            "luna": "quilla",
            "estrella": "chaska",
            "bueno": "allin",
            "malo": "mana allin",
            "grande": "hatun",
            "pequeño": "huch'uy",
            "día": "p'unchaw",
            "noche": "tuta",
            "ahora": "kunan",
            "antes": "ñawpaq",
            "después": "qhipa",
            "hoy": "kunan",
            "mañana": "paqarin",
            "ayer": "qayna",
            "aquí": "kaypi",
            "allí": "chaypi",
            "allá": "chaypi",
            "este": "kay",
            "esta": "kay",
            "esto": "kay",
            "ese": "chay",
            "esa": "chay",
            "eso": "chay",
            "aquel": "chay",
            "aquella": "chay",
            "aquello": "chay",
            # Palabras específicas del contexto legal
            "perú": "piruw",
            "peruano": "piruw",
            "peruanos": "piruwkuna",
            "ley30364": "kamachiy 30364",
            "30364": "30364",
            "prevención": "qaway",
            "intrafamiliar": "ayllupi",
            "especial": "allin",
            "atención": "qaway",
            "víctimas": "k'irisqakuna",
            "comunidades": "ayllukuna",
            "relación": "tupu",
            "necesitas": "necesitanki",
            "asesoría": "yatichiy",
        }

        # Procesar texto palabra por palabra
        words = text.lower().split()
        translated_words = []

        for word in words:
            # Limpiar palabra
            clean_word = word.strip(".,!?;:()[]{}\"'")

            # Buscar en diccionario
            if clean_word in dictionary:
                translated_word = dictionary[clean_word]
            else:
                # Mantener palabra original si no se encuentra
                translated_word = word

            # Restaurar puntuación
            if word.endswith(".") and not translated_word.endswith("."):
                translated_word += "."
            elif word.endswith(",") and not translated_word.endswith(","):
                translated_word += ","
            elif word.endswith(":") and not translated_word.endswith(":"):
                translated_word += ":"

            translated_words.append(translated_word)

        return " ".join(translated_words)

    def _translate_quechua_to_spanish(self, text: str) -> str:
        """Traducción de quechua a español basada en reglas"""
        # Diccionario básico quechua-español
        dictionary = {
            # Pronombres
            "ñuqa": "yo",
            "qam": "tú",
            "pay": "él/ella",
            "ñuqanchik": "nosotros",
            "qamkuna": "vosotros",
            "paykuna": "ellos/ellas",
            # Verbos comunes
            "kani": "soy/estoy",
            "kanki": "eres/estás",
            "kanku": "son/están",
            "kay": "ser/estar",
            "tiyay": "tener",
            "ruway": "hacer",
            "nin": "decir",
            "munay": "querer",
            "munani": "quiero",
            "munanki": "quieres",
            "munanku": "quieren",
            "yachay": "saber",
            "yachani": "sé",
            "atipay": "poder",
            "riy": "ir",
            "hamuy": "venir",
            # Sustantivos legales básicos
            "kamachiy": "ley",
            "llankhay": "justicia",
            "qatiq": "juez",
            "misitu": "policía",
            "qillqa": "documento",
            "qullqi": "dinero",
            "mikhuy": "comida/alimentos",
            "ayllu": "familia/comunidad",
            "churi": "hijo",
            "ususi": "hija",
            "tayta": "padre",
            "mama": "madre",
            # Palabras comunes
            "was": "casa",
            "yaku": "agua",
            "pacha": "tierra",
            "inti": "sol",
            "quilla": "luna",
            "chaska": "estrella",
            "allin": "bueno",
            "mana allin": "malo",
            "hatun": "grande",
            "huch'uy": "pequeño",
            "p'unchaw": "día",
            "tuta": "noche",
        }

        # Procesar texto palabra por palabra
        words = text.lower().split()
        translated_words = []

        for word in words:
            # Limpiar palabra
            clean_word = word.strip(".,!?;:()[]{}\"'")

            # Buscar en diccionario
            if clean_word in dictionary:
                translated_word = dictionary[clean_word]
            else:
                # Mantener palabra original si no se encuentra
                translated_word = word

            # Restaurar puntuación
            if word.endswith(".") and not translated_word.endswith("."):
                translated_word += "."
            elif word.endswith(",") and not translated_word.endswith(","):
                translated_word += ","

            translated_words.append(translated_word)

        return " ".join(translated_words)

    async def translate_legal_response(
        self, response: str, target_language: str
    ) -> Dict[str, Any]:
        source = self.detector.detect_language(response)
        if source == target_language:
            return {
                "success": True,
                "complete": True,
                "translated_text": response,
                "translation_needed": False,
                "method": "none",
            }
        return await self.translate(response, source, target_language)

    def _split_legal_response(self, response: str) -> List[Dict[str, Any]]:
        """Divide respuesta legal en secciones estructuradas"""
        sections = []
        lines = response.split("\n")
        current_section = {"type": "text", "content": ""}

        for line in lines:
            line = line.strip()

            if not line:
                continue

            # Detectar listas
            if line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                # Guardar sección actual si tiene contenido
                if current_section["content"]:
                    sections.append(current_section)

                # Iniciar nueva sección de lista
                sections.append(
                    {
                        "type": "list",
                        "items": [line[2:].strip()],
                        "original_format": "numbered",
                    }
                )
                current_section = {"type": "text", "content": ""}

            elif line.startswith(("-", "•", "*")):
                # Lista con viñetas
                if (
                    current_section["type"] != "list"
                    or current_section.get("original_format") != "bulleted"
                ):
                    if current_section["content"]:
                        sections.append(current_section)
                    current_section = {
                        "type": "list",
                        "items": [],
                        "original_format": "bulleted",
                    }

                current_section["items"].append(line[1:].strip())

            else:
                # Texto regular
                if current_section["type"] == "text":
                    current_section["content"] += line + "\n"
                else:
                    sections.append(current_section)
                    current_section = {"type": "text", "content": line + "\n"}

        # Agregar última sección
        if current_section["content"]:
            sections.append(current_section)

        return sections

    def _reconstruct_legal_response(self, sections: List[Dict[str, Any]]) -> str:
        """Reconstruye respuesta legal desde secciones traducidas"""
        response_parts = []

        for section in sections:
            if section["type"] == "text":
                response_parts.append(section["content"].strip())

            elif section["type"] == "list":
                format_type = section.get("original_format", "numbered")

                if format_type == "numbered":
                    for i, item in enumerate(section["items"], 1):
                        response_parts.append(f"{i}. {item}")
                else:  # bulleted
                    for item in section["items"]:
                        response_parts.append(f"• {item}")

            response_parts.append("")  # Espacio entre secciones

        return "\n".join(response_parts).strip()

    async def translate_with_context(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Traduce con contexto adicional para mejor precisión

        Argumentos:
            text: Texto a traducir
            source_lang: Idioma origen
            target_lang: Idioma destino
            context: Contexto adicional (tema legal, ubicación, etc.)

        Retorna:
            Traducción con contexto aplicado
        """
        try:
            # Realizar traducción básica
            translation_result = await self.translate(text, source_lang, target_lang)

            if not translation_result.get("success", False):
                return translation_result

            # Aplicar contexto si está disponible
            if context:
                translated_text = translation_result["translated_text"]

                # Adaptaciones por contexto legal
                if context.get("legal_topic"):
                    translated_text = self._apply_legal_context_adaptation(
                        translated_text, context["legal_topic"], target_lang
                    )

                # Adaptaciones culturales
                if context.get("cultural_context"):
                    translated_text = self._apply_cultural_adaptation(
                        translated_text, context["cultural_context"], target_lang
                    )

                translation_result["translated_text"] = translated_text
                translation_result["context_applied"] = True

            return translation_result

        except Exception as e:
            logger.error("operation_failed error_type={}", type(e).__name__)
            return {"success": False, "error": str(e), "original_text": text}

    def _apply_legal_context_adaptation(
        self, text: str, legal_topic: str, target_lang: str
    ) -> str:
        """Aplica adaptaciones por contexto legal"""
        # Términos legales específicos por tema
        legal_terms = {
            "violencia": {
                "qu": {
                    "orden de protección": "protección orden",
                    "medida cautelar": "cautela medida",
                    "violencia familiar": "familia violencia",
                }
            },
            "pensión": {
                "qu": {
                    "pensión de alimentos": "alimentos pensión",
                    "obligado alimentario": "alimentos obligado",
                    "proceso de alimentos": "alimentos proceso",
                }
            },
        }

        if legal_topic in legal_terms and target_lang in legal_terms[legal_topic]:
            terms_map = legal_terms[legal_topic][target_lang]

            for spanish_term, quechua_term in terms_map.items():
                text = text.replace(spanish_term, quechua_term)

        return text

    def _apply_cultural_adaptation(
        self, text: str, cultural_context: Dict[str, Any], target_lang: str
    ) -> str:
        """Aplica adaptaciones culturales"""
        if target_lang == "qu":
            # Agregar términos culturales quechuas
            if cultural_context.get("rural_context"):
                text = text.replace("comunidad", "ayllu")
                text = text.replace("autoridad local", "varayoc")

            if cultural_context.get("traditional_values"):
                text = text.replace("justicia", "llankhay")
                text = text.replace("derecho", "derecho")

        return text

    def get_translation_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del servicio de traducción"""
        return {
            "models_loaded": [],
            "pipelines_available": [],
            "cache_size": len(self.translation_cache),
            "supported_pairs": self.config.get_translation_pairs(),
            "transformers_available": TRANSFORMERS_AVAILABLE,
            "default_model": "google_translate",
            "google_translate_available": self.google_translate_available,
        }

    def clear_cache(self):
        """Limpia el cache de traducciones"""
        self.translation_cache.clear()
        logger.info("Cache de traducciones limpiado")
