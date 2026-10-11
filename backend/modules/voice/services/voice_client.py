"""
Cliente HTTP del microservicio TTS (voice-service, docker-compose `voice`).

El backend nunca carga torch/transformers: toda la síntesis vive en el
voice-service. Este cliente solo proxyea con timeout y mapea errores a
excepciones de dominio para que las routes respondan 503/504.
"""

import httpx
from loguru import logger

from config.settings import settings


class VoiceServiceUnavailable(Exception):
    """El voice-service no responde o falló la síntesis."""


class VoiceTTSClient:
    """Wrapper fino sobre GET /health, GET /voices, POST /speak."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ):
        self.base_url = (base_url or settings.VOICE_SERVICE_URL).rstrip("/")
        self.timeout = timeout_seconds or settings.VOICE_TIMEOUT_SECONDS

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning(f"voice health falló: {e}")
            raise VoiceServiceUnavailable(f"voice-service no disponible: {e}")

    async def voices(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/voices")
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning(f"voice voices falló: {e}")
            raise VoiceServiceUnavailable(f"voice-service no disponible: {e}")

    async def speak(self, text: str, lang: str, voice: str) -> tuple[bytes, str]:
        """Retorna (audio_wav_bytes, model_id)."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/speak",
                    json={"text": text, "lang": lang, "voice": voice},
                )
                if resp.status_code == 422:
                    # Error de validación downstream: no reintentar, propagar detalle
                    raise VoiceServiceUnavailable(f"validación TTS: {resp.text[:200]}")
                resp.raise_for_status()
                model_id = resp.headers.get("X-Model", "")
                return bytes(resp.content), model_id
        except VoiceServiceUnavailable:
            raise
        except Exception as e:
            logger.warning(f"voice speak falló: {e}")
            raise VoiceServiceUnavailable(f"síntesis TTS falló: {e}")


voice_client = VoiceTTSClient()
