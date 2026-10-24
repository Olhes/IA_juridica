"""Servicio de Text-to-Speech usando MMS-TTS para Quechua y Web Speech API para español"""
import asyncio
import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from io import BytesIO

logger = logging.getLogger("ia_juridica.tts")

try:
    from transformers import VitsModel, AutoTokenizer
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    logger.warning("transformers no disponible. MMS-TTS no estará disponible.")
    TRANSFORMERS_AVAILABLE = False


class TTSService:
    """Servicio de Text-to-Speech para Quechua (MMS-TTS) y español (Web Speech API)"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TTSService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if TTSService._initialized:
            return
        
        logger.info("🔄 Inicializando TTSService (Singleton)...")
        
        self.mms_model = None
        self.mms_tokenizer = None
        self.mms_available = False
        
        # Cargar modelo MMS-TTS para Quechua Cusqueño (quz)
        if TRANSFORMERS_AVAILABLE:
            try:
                logger.info("Cargando modelo MMS-TTS para Quechua Cusqueño...")
                self.mms_model = VitsModel.from_pretrained("facebook/mms-tts-quz")
                self.mms_tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-quz")
                
                # Mover a GPU si está disponible
                if torch.cuda.is_available():
                    self.mms_model = self.mms_model.to("cuda")
                    logger.info("✅ MMS-TTS cargado en GPU")
                else:
                    logger.info("✅ MMS-TTS cargado en CPU")
                
                self.mms_available = True
            except Exception as e:
                logger.error(f"Error cargando MMS-TTS: {e}")
                self.mms_available = False
        else:
            logger.warning("⚠️  Transformers no disponible, MMS-TTS deshabilitado")
        
        TTSService._initialized = True
        logger.info("✅ TTSService inicializado")
    
    def normalize_text_for_tts(self, text: str, language: str = "es") -> str:
        """
        Normaliza texto para síntesis de voz.
        
        - Elimina markdown y símbolos especiales
        - Convierte números a palabras
        - Elimina URLs
        - Normaliza espacios
        """
        # Eliminar markdown
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # Italic
        text = re.sub(r'`([^`]+)`', r'\1', text)          # Code
        text = re.sub(r'```[\s\S]*?```', '', text)       # Code blocks
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Links
        
        # Eliminar URLs
        text = re.sub(r'https?://[^\s]+', '', text)
        
        # Para quechua, convertir números a palabras
        if language in ["qu", "quy", "quz"]:
            text = self._convert_numbers_to_words_quechua(text)
        
        # Eliminar caracteres especiales excepto puntuación básica
        text = re.sub(r'[^\w\s.,;:¿?!¡\-\'"áéíóúñ]', ' ', text)
        
        # Normalizar espacios
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _convert_numbers_to_words_quechua(self, text: str) -> str:
        """
        Convierte números a palabras en quechua.
        Implementación básica para números comunes.
        """
        # Diccionario básico de números en quechua
        number_words = {
            "0": "ch'usaq",
            "1": "huk",
            "2": "iskay",
            "3": "kimsa",
            "4": "tawa",
            "5": "pichqa",
            "6": "suqta",
            "7": "qanchis",
            "8": "pusaq",
            "9": "isqun",
            "10": "chunka",
            "30364": "kimsa pachak chunka isqunniyuq pichqayuq chunka tawa",
            # Agregar más según necesidad
        }
        
        # Reemplazar números individuales
        for num, word in number_words.items():
            text = text.replace(num, word)
        
        return text
    
    async def synthesize_quechua(self, text: str) -> Optional[bytes]:
        """
        Sintetiza texto en quechua usando MMS-TTS.

        Retorna audio en formato WAV como bytes.
        """
        if not self.mms_available:
            logger.error("MMS-TTS no disponible")
            return None

        try:
            logger.info(f"[TTS] Texto original: {text[:100]}...")

            # Normalizar texto
            normalized_text = self.normalize_text_for_tts(text, language="qu")
            logger.info(f"[TTS] Texto normalizado: {normalized_text[:100]}...")

            # Tokenizar
            logger.info("[TTS] Tokenizando...")
            inputs = self.mms_tokenizer(normalized_text, return_tensors="pt")
            logger.info(f"[TTS] Tokenización exitosa. Input shape: {inputs['input_ids'].shape}")

            # Ejecutar en thread separado para no bloquear
            loop = asyncio.get_event_loop()

            def _synthesize(inputs_dict):
                with torch.no_grad():
                    if torch.cuda.is_available():
                        inputs_dict = {k: v.to("cuda") for k, v in inputs_dict.items()}
                    output = self.mms_model(**inputs_dict).waveform
                    return output

            logger.info("[TTS] Ejecutando modelo MMS-TTS...")
            output = await loop.run_in_executor(None, _synthesize, inputs)
            logger.info(f"[TTS] Modelo ejecutado. Output shape: {output.shape}")

            # Convertir a WAV
            audio_array = output.squeeze().cpu().numpy()
            logger.info(f"[TTS] Audio array shape: {audio_array.shape}, dtype: {audio_array.dtype}")

            # Usar scipy o soundfile para guardar como WAV
            try:
                import soundfile as sf

                buffer = BytesIO()
                logger.info("[TTS] Escribiendo WAV...")
                sf.write(buffer, audio_array, 16000, format='WAV')
                buffer.seek(0)
                audio_bytes = buffer.read()
                logger.info(f"[TTS] WAV generado exitosamente. Size: {len(audio_bytes)} bytes")

                return audio_bytes
            except ImportError:
                logger.error("soundfile no disponible. Instala con: pip install soundfile")
                return None
            except Exception as e:
                logger.error(f"[TTS] Error escribiendo WAV: {e}")
                return None

        except Exception as e:
            logger.error(f"[TTS] Error sintetizando quechua: {e}", exc_info=True)
            return None
    
    def is_available(self, language: str) -> bool:
        """Verifica si TTS está disponible para el idioma"""
        if language in ["qu", "quy", "quz", "qul"]:
            return self.mms_available
        elif language == "es":
            # Español usa Web Speech API en el frontend
            return True
        return False
    
    def get_supported_languages(self) -> list:
        """Retorna lista de idiomas soportados"""
        languages = ["es"]  # Web Speech API
        if self.mms_available:
            languages.extend(["qu", "quy", "quz", "qul"])
        return languages
