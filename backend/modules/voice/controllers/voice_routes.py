"""
Rutas del módulo de voz TTS — proxy con caché hacia voice-service.

  GET  /voice/health  -> estado del backend + downstream MMS
  GET  /voice/voices  -> voces lógicas (proxy)
  POST /voice/speak   -> {text, lang, voice} -> audio/wav (caché Redis)
"""

import base64
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from loguru import logger

from config.settings import settings
from database.redis_adapter import redis_adapter
from models.voice_models import SpeakRequest, VoiceHealthResponse, VoiceListResponse
from modules.voice.services.text_normalizer_ancash import canonical_form, voice_cache_key
from modules.voice.services.voice_client import VoiceServiceUnavailable, voice_client
from security import Principal, limiter

router = APIRouter(prefix="/voice", tags=["voice"])
# Mismo patrón temporal que chat_routes: auth deshabilitada en debug
CurrentPrincipal = Annotated[Optional[Principal], Depends(lambda: None)]


def _service_down(detail: str) -> HTTPException:
    return HTTPException(status_code=503, detail=detail)


@router.get("/health", response_model=VoiceHealthResponse)
async def voice_health(request: Request, principal: CurrentPrincipal):
    if not settings.VOICE_ENABLED:
        return VoiceHealthResponse(status="disabled", cache="disabled")
    try:
        downstream = await voice_client.health()
        return VoiceHealthResponse(
            status="ok" if downstream.get("status") == "ok" else "degraded",
            model_id=downstream.get("model_id"),
            model_loaded=bool(downstream.get("model_loaded")),
            voice=downstream.get("voice"),
            cache="redis" if settings.CACHE_ENABLED else "disabled",
        )
    except VoiceServiceUnavailable as e:
        return VoiceHealthResponse(
            status="degraded",
            cache="redis" if settings.CACHE_ENABLED else "disabled",
            downstream_error=str(e)[:200],
        )


@router.get("/voices", response_model=VoiceListResponse)
async def voice_voices(request: Request, principal: CurrentPrincipal):
    try:
        return await voice_client.voices()
    except VoiceServiceUnavailable as e:
        raise _service_down(str(e))


@router.post("/speak")
@limiter.limit(settings.VOICE_RATE_LIMIT)
async def voice_speak(request: Request, payload: SpeakRequest, principal: CurrentPrincipal):
    if not settings.VOICE_ENABLED:
        raise HTTPException(status_code=503, detail="voz deshabilitada (VOICE_ENABLED=false)")
    if payload.voice != settings.VOICE_ID:
        raise HTTPException(status_code=404, detail=f"voice desconocida: {payload.voice}")

    lang = payload.lang.value if hasattr(payload.lang, "value") else str(payload.lang)
    # Grafía canónica del corpus si el texto existe en el léxico ancashino
    text = canonical_form(payload.text)
    cache_key = voice_cache_key(text, lang, payload.voice)

    # 1) Caché Redis (guarda dict JSON: audio_b64 + model_id)
    if settings.CACHE_ENABLED:
        try:
            cached = await redis_adapter.get_cache(cache_key)
            if isinstance(cached, dict) and cached.get("audio_b64"):
                logger.info(f"voice caché HIT {cache_key[:12]}")
                return Response(
                    content=base64.b64decode(cached["audio_b64"]),
                    media_type="audio/wav",
                    headers={
                        "X-Cache": "HIT",
                        "X-Voice": payload.voice,
                        "X-Model": cached.get("model_id", ""),
                    },
                )
        except Exception as e:
            logger.warning(f"voice caché lectura falló (sigo sin caché): {e}")

    # 2) Síntesis downstream
    try:
        audio, model_id = await voice_client.speak(text, lang, payload.voice)
    except VoiceServiceUnavailable as e:
        raise _service_down(str(e))

    # 3) Guardar en caché si cabe (audios cortos; evita saturar Redis)
    if settings.CACHE_ENABLED and len(audio) <= settings.VOICE_MAX_CACHED_BYTES:
        try:
            await redis_adapter.set_cache(
                cache_key,
                {"audio_b64": base64.b64encode(audio).decode(), "model_id": model_id},
                ttl=settings.VOICE_CACHE_TTL,
            )
        except Exception as e:
            logger.warning(f"voice caché escritura falló: {e}")

    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"X-Cache": "MISS", "X-Voice": payload.voice, "X-Model": model_id},
    )
