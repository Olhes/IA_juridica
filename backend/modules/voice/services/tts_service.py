"""Servicio de Text-to-Speech usando MMS-TTS para Quechua y Web Speech API para español"""
import asyncio
import re
import logging
from typing import Optional
from io import BytesIO

from markdown_it import MarkdownIt

logger = logging.getLogger("ia_juridica.tts")
_MARKDOWN = MarkdownIt("commonmark")
_QUECHUA_DIGITS = ("ch'usaq", "huk", "iskay", "kimsa", "tawa", "pichqa", "suqta", "qanchis", "pusaq", "isqun")

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
        self._torch = None
        
        # VITS es opcional; no importar su implementación al arrancar el chat.
        try:
            import torch
            from transformers import AutoTokenizer, VitsModel

            logger.info("Cargando modelo MMS-TTS para Quechua Cusqueño...")
            self.mms_model = VitsModel.from_pretrained("facebook/mms-tts-quz").eval()
            self.mms_tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-quz")
            if torch.cuda.is_available():
                self.mms_model = self.mms_model.to("cuda")
                logger.info("✅ MMS-TTS cargado en GPU")
            else:
                logger.info("✅ MMS-TTS cargado en CPU")
            self._torch = torch
            self.mms_available = True
        except ImportError:
            logger.warning("⚠️  Transformers no disponible, MMS-TTS deshabilitado")
        except Exception as e:
            logger.error("Error cargando MMS-TTS: %s", type(e).__name__)
        
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
        # CommonMark supplies the visible text; we don't render HTML or verbalize code fences.
        spoken = []
        for token in _MARKDOWN.parse(text):
            if token.type == "list_item_open" and token.info:
                # Preserve the written marker even when a list jumps from 2 to 7.
                spoken.append(token.info + token.markup)
            elif token.type == "inline":
                line = []
                for child in token.children or ():
                    if child.type in {"text", "code_inline", "image"}:
                        line.append(child.content)
                    elif child.type in {"softbreak", "hardbreak"}:
                        line.append(" ")
                spoken.append("".join(line))
        text = " ".join(spoken)
        
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
        """Lee secuencias dígito por dígito en vez de inventar cardinales para citas."""
        return re.sub(
            r"[0-9]+",
            lambda match: "chunka" if match[0] == "10" else " ".join(_QUECHUA_DIGITS[int(d)] for d in match[0]),
            text,
        )
    
    async def synthesize_quechua(self, text: str) -> Optional[bytes]:
        """
        Sintetiza texto en quechua usando MMS-TTS.

        Retorna audio en formato WAV como bytes.
        """
        if not self.mms_available:
            logger.error("MMS-TTS no disponible")
            return None

        try:
            # Normalizar texto
            normalized_text = self.normalize_text_for_tts(text, language="qu")

            # Tokenizar
            logger.info("[TTS] Tokenizando...")
            inputs = self.mms_tokenizer(normalized_text, return_tensors="pt")
            logger.info(f"[TTS] Tokenización exitosa. Input shape: {inputs['input_ids'].shape}")

            # Ejecutar en thread separado para no bloquear
            loop = asyncio.get_event_loop()

            def _synthesize(inputs_dict):
                with self._torch.inference_mode():
                    if self._torch.cuda.is_available():
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
                logger.error("[TTS] Error escribiendo WAV: %s", type(e).__name__)
                return None

        except Exception as e:
            logger.error("[TTS] Error sintetizando quechua: %s", type(e).__name__)
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
