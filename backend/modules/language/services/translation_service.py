"""
Servicio de traducción especializado para español/quechua
Implementa traducción en cascada con modelos específicos
"""

from typing import Dict, List, Optional, Tuple, Any
import asyncio
from loguru import logger

try:
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    logger.warning("transformers no disponible. Usando implementación simulada.")
    TRANSFORMERS_AVAILABLE = False

try:
    from googletrans import Translator
    GOOGLE_TRANSLATE_AVAILABLE = True
except ImportError:
    logger.warning("googletrans no disponible. Google Translate API no estará disponible.")
    GOOGLE_TRANSLATE_AVAILABLE = False

from .language_config import LanguageConfig, LanguageCode
from .language_detector import LanguageDetector

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
                logger.warning(f"⚠️  Error inicializando Google Translate: {e}")
                self.google_translator = None
                self.google_translate_available = False
        else:
            self.google_translator = None
        
        # Inicializar modelos solo si están disponibles Y habilitados
        from config.settings import settings
        logger.info(f"⚙️  TRANSLATION_ENABLED: {settings.TRANSLATION_ENABLED}")
        logger.info(f"⚙️  TRANSLATION_METHOD: {settings.TRANSLATION_METHOD}")
        
        if TRANSFORMERS_AVAILABLE and settings.TRANSLATION_ENABLED and settings.TRANSLATION_METHOD == "nllb":
            logger.info("🚀 Inicializando modelos de traducción NLLB...")
            self._initialize_translation_models()
        elif settings.TRANSLATION_METHOD == "google_translate":
            logger.info("🌐 Usando Google Translate como método de traducción principal")
        elif not settings.TRANSLATION_ENABLED:
            logger.warning("⚠️  Traducción deshabilitada (TRANSLATION_ENABLED=false)")
        else:
            logger.warning("⚠️  Transformers no disponible, usando traducción basada en reglas")
        
        TranslationService._initialized = True
        logger.info("✅ TranslationService inicializado (Singleton)")
    
    def _initialize_translation_models(self):
        """Inicializa modelos de traducción"""
        try:
            # Modelo NLLB para traducción general
            nllb_model = self.config.TRANSLATION_MODELS.get("nllb")
            logger.info(f"📥 Cargando modelo NLLB: {nllb_model}")
            
            # Configurar directorio de cache local para evitar errores de ruta
            import os
            from pathlib import Path
            
            # Usar directorio cache en el proyecto
            cache_dir = Path(__file__).parent.parent.parent / "models" / "transformers_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"💾 Cache directory: {cache_dir}")
            
            if nllb_model:
                logger.info("⏳ Descargando tokenizer y modelo (puede tardar varios minutos)...")
                self.translation_models["nllb"] = {
                    "tokenizer": AutoTokenizer.from_pretrained(nllb_model, cache_dir=str(cache_dir)),
                    "model": AutoModelForSeq2SeqLM.from_pretrained(nllb_model, cache_dir=str(cache_dir))
                }
                logger.info("✅ Modelo NLLB cargado exitosamente")
            else:
                logger.warning("⚠️  No se encontró configuración del modelo NLLB")
            
            # Crear pipelines
            for model_name, model_data in self.translation_models.items():
                logger.info(f"🔧 Creando pipeline para {model_name}...")
                self.translation_pipelines[model_name] = pipeline(
                    "translation",
                    model=model_data["model"],
                    tokenizer=model_data["tokenizer"],
                    max_length=1024,  # Aumentar max_length para traducciones largas
                    device="cpu"
                )
                logger.info(f"✅ Pipeline {model_name} creado (max_length=1024)")
            
            logger.info(f"📊 Modelos disponibles: {list(self.translation_pipelines.keys())}")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando modelos de traducción: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def translate(self, text: str, source_lang: str, target_lang: str, 
                       model: str = "nllb") -> Dict[str, Any]:
        """
        Traduce texto entre idiomas soportados
        
        Args:
            text: Texto a traducir
            source_lang: Idioma origen
            target_lang: Idioma destino
            model: Modelo a usar
            
        Returns:
            Diccionario con traducción y metadatos
        """
        try:
            # Verificar soporte de idiomas
            if not self._is_translation_supported(source_lang, target_lang):
                return {
                    "success": False,
                    "error": f"Traducción no soportada: {source_lang} -> {target_lang}",
                    "original_text": text
                }
            
            # Truncar texto si es muy largo (max 1000 caracteres para NLLB)
            MAX_TEXT_LENGTH = 1000
            original_length = len(text)
            if len(text) > MAX_TEXT_LENGTH:
                logger.warning(f"⚠️  Texto muy largo ({len(text)} chars), truncando a {MAX_TEXT_LENGTH}")
                text = text[:MAX_TEXT_LENGTH] + "..."
            
            # Verificar cache
            cache_key = f"{source_lang}_{target_lang}_{hash(text)}"
            if cache_key in self.translation_cache:
                logger.debug("Traducción encontrada en cache")
                return self.translation_cache[cache_key]
            
            # Priorizar Google Translate para quechua (evita repeticiones de NLLB-200)
            if target_lang in ["qu", "quy", "quz", "qul"] and self.google_translate_available:
                logger.info("🌐 Usando Google Translate para quechua (mejor calidad que NLLB-200)")
                result = await self._translate_with_google(text, source_lang, target_lang)
            # Usar modelo NLLB para otros idiomas
            elif TRANSFORMERS_AVAILABLE and model in self.translation_pipelines:
                result = await self._translate_with_model(text, source_lang, target_lang, model)
                if original_length > MAX_TEXT_LENGTH:
                    result["truncated"] = True
                    result["original_length"] = original_length
            else:
                result = await self._translate_with_rules(text, source_lang, target_lang)
            
            # Guardar en cache
            self.translation_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Error en traducción: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "original_text": text
            }
    
    def _is_translation_supported(self, source_lang: str, target_lang: str) -> bool:
        """Verifica si el par de traducción es soportado"""
        supported_pairs = self.config.get_translation_pairs()
        return (source_lang, target_lang) in supported_pairs
    
    async def _translate_with_model(self, text: str, source_lang: str, target_lang: str, 
                                  model: str) -> Dict[str, Any]:
        """Usa modelo de transformers para traducción"""
        try:
            # Mapear códigos de idioma a códigos de modelo
            # Usar Quechua Southern (quy_Latn) que tiene mejor soporte en NLLB-200
            lang_mapping = {
                "es": "spa_Latn",
                "qu": "quy_Latn",  # Quechua Southern (mejor soporte en NLLB-200)
                "quy": "quy_Latn",  # Quechua Southern
                "quz": "quz_Latn",  # Quechua Cuzqueño
                "qul": "quy_Latn",  # Mapear a Southern por mejor soporte
                "ay": "ayr_Latn"
            }
            
            source_code = lang_mapping.get(source_lang, source_lang)
            target_code = lang_mapping.get(target_lang, target_lang)
            
            # Realizar traducción
            pipeline = self.translation_pipelines[model]
            result = pipeline(text, src_lang=source_code, tgt_lang=target_code)
            
            return {
                "success": True,
                "translated_text": result[0]["translation_text"],
                "source_language": source_lang,
                "target_language": target_lang,
                "model_used": model,
                "confidence": 0.85,  # Estimación
                "method": "model"
            }
            
        except Exception as e:
            logger.error(f"Error en traducción con modelo: {str(e)}")
            # Fallback a traducción basada en reglas
            return await self._translate_with_rules(text, source_lang, target_lang)
    
    async def _translate_with_google(self, text: str, source_lang: str, target_lang: str) -> Dict[str, Any]:
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
                "ay": "ay"
            }
            
            src_lang = google_lang_mapping.get(source_lang, source_lang)
            tgt_lang = google_lang_mapping.get(target_lang, target_lang)
            
            # Realizar traducción (googletrans es async en versión 4.0+)
            result = await self.google_translator.translate(text, src=src_lang, dest=tgt_lang)
            
            return {
                "success": True,
                "translated_text": result.text,
                "source_language": source_lang,
                "target_language": target_lang,
                "model_used": "google_translate",
                "confidence": 0.90,  # Google Translate generalmente tiene buena calidad
                "method": "google_translate"
            }
            
        except Exception as e:
            logger.error(f"Error en traducción con Google Translate: {str(e)}")
            # Fallback a traducción con modelo NLLB
            if TRANSFORMERS_AVAILABLE and "nllb" in self.translation_pipelines:
                return await self._translate_with_model(text, source_lang, target_lang, "nllb")
            # Fallback a reglas
            return await self._translate_with_rules(text, source_lang, target_lang)
    
    async def _translate_with_rules(self, text: str, source_lang: str, target_lang: str) -> Dict[str, Any]:
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
                "confidence": 0.65,  # Menor confianza para reglas
                "method": "rules"
            }
            
        except Exception as e:
            logger.error(f"Error en traducción con reglas: {str(e)}")
            raise
    
    def _translate_spanish_to_quechua(self, text: str) -> str:
        """Traducción de español a quechua basada en reglas"""
        # Diccionario básico español-quechua
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
            
            # Palabras comunes
            "casa": "was",
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
            "noche": "tuta"
        }
        
        # Procesar texto palabra por palabra
        words = text.lower().split()
        translated_words = []
        
        for word in words:
            # Limpiar palabra
            clean_word = word.strip('.,!?;:()[]{}"\'')
            
            # Buscar en diccionario
            if clean_word in dictionary:
                translated_word = dictionary[clean_word]
            else:
                # Mantener palabra original si no se encuentra
                translated_word = word
            
            # Restaurar puntuación
            if word.endswith('.') and not translated_word.endswith('.'):
                translated_word += '.'
            elif word.endswith(',') and not translated_word.endswith(','):
                translated_word += ','
            
            translated_words.append(translated_word)
        
        return ' '.join(translated_words)
    
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
            "tuta": "noche"
        }
        
        # Procesar texto palabra por palabra
        words = text.lower().split()
        translated_words = []
        
        for word in words:
            # Limpiar palabra
            clean_word = word.strip('.,!?;:()[]{}"\'')
            
            # Buscar en diccionario
            if clean_word in dictionary:
                translated_word = dictionary[clean_word]
            else:
                # Mantener palabra original si no se encuentra
                translated_word = word
            
            # Restaurar puntuación
            if word.endswith('.') and not translated_word.endswith('.'):
                translated_word += '.'
            elif word.endswith(',') and not translated_word.endswith(','):
                translated_word += ','
            
            translated_words.append(translated_word)
        
        return ' '.join(translated_words)
    
    async def translate_legal_response(self, response: str, target_language: str) -> Dict[str, Any]:
        """
        Traduce respuesta legal completa manteniendo estructura
        
        Args:
            response: Respuesta legal a traducir
            target_language: Idioma destino
            
        Returns:
            Respuesta traducida con metadatos
        """
        try:
            # Detectar idioma origen
            source_lang = self.detector.detect_language(response)
            
            # Si ya está en el idioma destino, retornar original
            if source_lang == target_language:
                return {
                    "success": True,
                    "translated_text": response,
                    "source_language": source_lang,
                    "target_language": target_language,
                    "translation_needed": False,
                    "method": "none"
                }
            
            # Dividir respuesta en secciones para traducción preservando estructura
            sections = self._split_legal_response(response)
            translated_sections = []
            
            for section in sections:
                if section['type'] == 'text':
                    # Traducir texto
                    translation_result = await self.translate(
                        section['content'], 
                        source_lang, 
                        target_language
                    )
                    
                    translated_sections.append({
                        'type': 'text',
                        'content': translation_result.get('translated_text', section['content']),
                        'translation_confidence': translation_result.get('confidence', 0.0)
                    })
                
                elif section['type'] == 'list':
                    # Traducir cada elemento de la lista
                    translated_items = []
                    for item in section['items']:
                        translation_result = await self.translate(
                            item, source_lang, target_language
                        )
                        translated_items.append(
                            translation_result.get('translated_text', item)
                        )
                    
                    translated_sections.append({
                        'type': 'list',
                        'items': translated_items,
                        'original_format': section.get('original_format', 'numbered')
                    })
                
                else:
                    # Mantener sección sin cambios
                    translated_sections.append(section)
            
            # Reconstruir respuesta
            translated_response = self._reconstruct_legal_response(translated_sections)
            
            return {
                "success": True,
                "translated_text": translated_response,
                "source_language": source_lang,
                "target_language": target_language,
                "translation_needed": True,
                "sections_translated": len([s for s in translated_sections if s['type'] == 'text']),
                "method": "structured"
            }
            
        except Exception as e:
            logger.error(f"Error en traducción de respuesta legal: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "original_text": response
            }
    
    def _split_legal_response(self, response: str) -> List[Dict[str, Any]]:
        """Divide respuesta legal en secciones estructuradas"""
        sections = []
        lines = response.split('\n')
        current_section = {'type': 'text', 'content': ''}
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
            
            # Detectar listas
            if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                # Guardar sección actual si tiene contenido
                if current_section['content']:
                    sections.append(current_section)
                
                # Iniciar nueva sección de lista
                sections.append({
                    'type': 'list',
                    'items': [line[2:].strip()],
                    'original_format': 'numbered'
                })
                current_section = {'type': 'text', 'content': ''}
            
            elif line.startswith(('-', '•', '*')):
                # Lista con viñetas
                if current_section['type'] != 'list' or current_section.get('original_format') != 'bulleted':
                    if current_section['content']:
                        sections.append(current_section)
                    current_section = {
                        'type': 'list',
                        'items': [],
                        'original_format': 'bulleted'
                    }
                
                current_section['items'].append(line[1:].strip())
            
            else:
                # Texto regular
                if current_section['type'] == 'text':
                    current_section['content'] += line + '\n'
                else:
                    sections.append(current_section)
                    current_section = {'type': 'text', 'content': line + '\n'}
        
        # Agregar última sección
        if current_section['content']:
            sections.append(current_section)
        
        return sections
    
    def _reconstruct_legal_response(self, sections: List[Dict[str, Any]]) -> str:
        """Reconstruye respuesta legal desde secciones traducidas"""
        response_parts = []
        
        for section in sections:
            if section['type'] == 'text':
                response_parts.append(section['content'].strip())
            
            elif section['type'] == 'list':
                format_type = section.get('original_format', 'numbered')
                
                if format_type == 'numbered':
                    for i, item in enumerate(section['items'], 1):
                        response_parts.append(f"{i}. {item}")
                else:  # bulleted
                    for item in section['items']:
                        response_parts.append(f"• {item}")
            
            response_parts.append('')  # Espacio entre secciones
        
        return '\n'.join(response_parts).strip()
    
    async def translate_with_context(self, text: str, source_lang: str, target_lang: str,
                                   context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Traduce con contexto adicional para mejor precisión
        
        Args:
            text: Texto a traducir
            source_lang: Idioma origen
            target_lang: Idioma destino
            context: Contexto adicional (tema legal, ubicación, etc.)
            
        Returns:
            Traducción con contexto aplicado
        """
        try:
            # Realizar traducción básica
            translation_result = await self.translate(text, source_lang, target_lang)
            
            if not translation_result.get('success', False):
                return translation_result
            
            # Aplicar contexto si está disponible
            if context:
                translated_text = translation_result['translated_text']
                
                # Adaptaciones por contexto legal
                if context.get('legal_topic'):
                    translated_text = self._apply_legal_context_adaptation(
                        translated_text, context['legal_topic'], target_lang
                    )
                
                # Adaptaciones culturales
                if context.get('cultural_context'):
                    translated_text = self._apply_cultural_adaptation(
                        translated_text, context['cultural_context'], target_lang
                    )
                
                translation_result['translated_text'] = translated_text
                translation_result['context_applied'] = True
            
            return translation_result
            
        except Exception as e:
            logger.error(f"Error en traducción con contexto: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "original_text": text
            }
    
    def _apply_legal_context_adaptation(self, text: str, legal_topic: str, target_lang: str) -> str:
        """Aplica adaptaciones por contexto legal"""
        # Términos legales específicos por tema
        legal_terms = {
            'violencia': {
                'qu': {
                    'orden de protección': 'protección orden',
                    'medida cautelar': 'cautela medida',
                    'violencia familiar': 'familia violencia'
                }
            },
            'pensión': {
                'qu': {
                    'pensión de alimentos': 'alimentos pensión',
                    'obligado alimentario': 'alimentos obligado',
                    'proceso de alimentos': 'alimentos proceso'
                }
            }
        }
        
        if legal_topic in legal_terms and target_lang in legal_terms[legal_topic]:
            terms_map = legal_terms[legal_topic][target_lang]
            
            for spanish_term, quechua_term in terms_map.items():
                text = text.replace(spanish_term, quechua_term)
        
        return text
    
    def _apply_cultural_adaptation(self, text: str, cultural_context: Dict[str, Any], target_lang: str) -> str:
        """Aplica adaptaciones culturales"""
        if target_lang == "qu":
            # Agregar términos culturales quechuas
            if cultural_context.get('rural_context'):
                text = text.replace('comunidad', 'ayllu')
                text = text.replace('autoridad local', 'varayoc')
            
            if cultural_context.get('traditional_values'):
                text = text.replace('justicia', 'llankhay')
                text = text.replace('derecho', 'derecho')
        
        return text
    
    def get_translation_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del servicio de traducción"""
        return {
            "models_loaded": list(self.translation_models.keys()),
            "pipelines_available": list(self.translation_pipelines.keys()),
            "cache_size": len(self.translation_cache),
            "supported_pairs": self.config.get_translation_pairs(),
            "transformers_available": TRANSFORMERS_AVAILABLE,
            "default_model": "nllb" if TRANSFORMERS_AVAILABLE else "rules"
        }
    
    def clear_cache(self):
        """Limpia el cache de traducciones"""
        self.translation_cache.clear()
        logger.info("Cache de traducciones limpiado")