"""
Tests unitarios del proxy de voz TTS (sin IO externo: sin Docker, sin Redis real).

Cubre:
  - normalizador ancashino + clave de caché canónica
  - validación Pydantic de SpeakRequest
  - routes /voice/* con voice_client y redis mockeados (MISS, HIT, 404, 422, 503)
"""

import base64
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import modules.voice.controllers.voice_routes as voice_routes
from models.voice_models import SpeakRequest
from modules.voice.services.text_normalizer_ancash import normalize_ancash, voice_cache_key
from modules.voice.services.voice_client import VoiceServiceUnavailable
from security import limiter

FAKE_WAV = b"RIFF....WAVEfakepcm"  # bytes opacos; el proxy no parsea audio


def make_client(monkeypatch, speak_result="ok"):
    """App aislada con el router de voz y dependencias mockeadas."""
    store = {}

    async def fake_get_cache(key):
        return store.get(key)

    async def fake_set_cache(key, value, ttl=None):
        store[key] = value
        return True

    monkeypatch.setattr(voice_routes.redis_adapter, "get_cache", fake_get_cache)
    monkeypatch.setattr(voice_routes.redis_adapter, "set_cache", fake_set_cache)

    mock_client = AsyncMock()
    if speak_result == "ok":
        mock_client.speak.return_value = (FAKE_WAV, "facebook/mms-tts-quy")
    elif speak_result == "down":
        mock_client.speak.side_effect = VoiceServiceUnavailable("caído")
    mock_client.health.return_value = {
        "status": "ok",
        "model_id": "facebook/mms-tts-quy",
        "model_loaded": True,
        "voice": "ancash-masculino-01",
    }
    mock_client.voices.return_value = {"voices": []}
    monkeypatch.setattr(voice_routes, "voice_client", mock_client)

    app = FastAPI()
    app.state.limiter = limiter  # igual que main.py
    app.include_router(voice_routes.router)
    return TestClient(app), store


# ── Normalizador ─────────────────────────────────────────────────────────────

def test_normalize_minusculas_sin_puntuacion():
    assert normalize_ancash("  ¡Atuqmi, ASHKALLATA mikun!  ") == "atuqmi ashkallata mikun"


def test_cache_key_canonica_ignora_caso_y_puntuacion():
    k1 = voice_cache_key("Atuqmi ashkallata mikun.", "qu-ancash", "ancash-masculino-01")
    k2 = voice_cache_key("atuqmi ASHKALLATA mikun", "qu-ancash", "ancash-masculino-01")
    assert k1 == k2
    assert k1.startswith("tts:")


def test_cache_key_difiere_por_texto_lang_o_voz():
    base = ("atuqmi ashkallata mikun", "qu-ancash", "ancash-masculino-01")
    assert voice_cache_key(*base) != voice_cache_key("otro texto", base[1], base[2])
    assert voice_cache_key(*base) != voice_cache_key(base[0], "es", base[2])
    assert voice_cache_key(*base) != voice_cache_key(base[0], base[1], "otra-voz")


# ── Validación Pydantic ──────────────────────────────────────────────────────

def test_speak_request_defaults():
    req = SpeakRequest(text="hola")
    assert req.lang.value == "qu-ancash"
    assert req.voice == "ancash-masculino-01"


def test_speak_request_rechaza_texto_vacio_y_lang_invalida():
    with pytest.raises(ValidationError):
        SpeakRequest(text="")
    with pytest.raises(ValidationError):
        SpeakRequest(text="hola", lang="en")


# ── Routes ───────────────────────────────────────────────────────────────────

def test_speak_miss_luego_hit(monkeypatch):
    client, store = make_client(monkeypatch)
    body = {"text": "Atuqmi ashkallata mikun", "lang": "qu-ancash", "voice": "ancash-masculino-01"}

    r1 = client.post("/voice/speak", json=body)
    assert r1.status_code == 200
    assert r1.headers["content-type"] == "audio/wav"
    assert r1.headers["X-Cache"] == "MISS"
    assert r1.content == FAKE_WAV
    assert len(store) == 1  # se guardó en caché

    r2 = client.post("/voice/speak", json=body)
    assert r2.status_code == 200
    assert r2.headers["X-Cache"] == "HIT"
    assert r2.content == FAKE_WAV


def test_speak_voz_desconocida_404(monkeypatch):
    client, _ = make_client(monkeypatch)
    r = client.post("/voice/speak", json={"text": "hola", "lang": "es", "voice": "otra-voz"})
    assert r.status_code == 404


def test_speak_texto_vacio_422(monkeypatch):
    client, _ = make_client(monkeypatch)
    r = client.post("/voice/speak", json={"text": "", "lang": "es", "voice": "ancash-masculino-01"})
    assert r.status_code == 422


def test_speak_downstream_caido_503(monkeypatch):
    client, _ = make_client(monkeypatch, speak_result="down")
    r = client.post("/voice/speak", json={"text": "hola", "lang": "es", "voice": "ancash-masculino-01"})
    assert r.status_code == 503


def test_health_ok_y_voices(monkeypatch):
    client, _ = make_client(monkeypatch)
    h = client.get("/voice/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"
    assert h.json()["model_loaded"] is True
    v = client.get("/voice/voices")
    assert v.status_code == 200
    assert "voices" in v.json()


def test_health_degraded_si_downstream_cae(monkeypatch):
    client, _ = make_client(monkeypatch)
    voice_routes.voice_client.health = AsyncMock(side_effect=VoiceServiceUnavailable("caído"))
    h = client.get("/voice/health")
    assert h.status_code == 200
    assert h.json()["status"] == "degraded"
    assert "downstream_error" in h.json()
