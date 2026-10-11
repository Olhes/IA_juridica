"""Microservicio TTS Quechua Ancash — Meta MMS (VITS) en CPU.

Fase 0: checkpoint base facebook/mms-tts-quy (Ayacucho), el más cercano
a las variedades Ancash Sihuas (qws) / Chiquián (qxa), para las que MMS
no publica checkpoint propio. Fine-tune ancashino real = Fase 2.

Endpoints:
  GET  /health  -> estado + si el modelo ya está cargado
  GET  /voices  -> voces lógicas disponibles (v1: una masculina)
  POST /speak   -> {text, lang, voice} -> audio/wav

Licencia del checkpoint MMS: CC-BY-NC-4.0 (no comercial).
 audios Common Voice usados como referencia: CC0.
"""

import io
import os
import re
import threading

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

MODEL_ID = os.getenv("MODEL_ID", "facebook/mms-tts-quy")
VOICE_ID = os.getenv("VOICE_ID", "ancash-masculino-01")
MAX_CHARS = int(os.getenv("MAX_CHARS", "800"))
SAMPLE_RATE_OUT = int(os.getenv("SAMPLE_RATE_OUT", "16000"))

app = FastAPI(title="IA Jurídica Voice TTS (MMS)", version="0.1.0")

_lock = threading.Lock()
_tokenizer = None
_model = None
_model_sr = None


class SpeakRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=800)
    lang: str = Field(default="qu-ancash")
    voice: str = Field(default=VOICE_ID)


def normalize_ancash(text: str) -> str:
    """Normalización mínima para MMS-TTS (entrenado en minúsculas sin puntuación)."""
    t = text.lower().strip()
    t = re.sub(r"[^\w\s'ñáéíóúüâêîôûç\-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def split_chunks(text: str, limit: int = 350) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+", text)
    chunks: list[str] = []
    buf = ""
    for p in parts:
        p = p.strip(" .!?;,")
        if not p:
            continue
        cand = (buf + " " + p).strip() if buf else p
        if len(cand) <= limit:
            buf = cand
        else:
            if buf:
                chunks.append(buf)
            buf = p[:limit]
    if buf:
        chunks.append(buf)
    return chunks or [text[:limit]]


def get_model():
    global _tokenizer, _model, _model_sr
    if _model is not None:
        return _tokenizer, _model, _model_sr
    with _lock:
        if _model is not None:
            return _tokenizer, _model, _model_sr
        import torch
        from transformers import VitsModel, VitsTokenizer, set_seed

        set_seed(555)  # VITS es no-determinístico; semilla fija = reproducible
        _tokenizer = VitsTokenizer.from_pretrained(MODEL_ID)
        _model = VitsModel.from_pretrained(MODEL_ID)
        _model.eval()
        _model_sr = int(_model.config.sampling_rate)
        return _tokenizer, _model, _model_sr


@app.get("/health")
def health():
    import importlib.util

    return {
        "status": "ok",
        "model_id": MODEL_ID,
        "model_loaded": _model is not None,
        "torch_available": importlib.util.find_spec("torch") is not None,
        "voice": VOICE_ID,
    }


@app.get("/voices")
def voices():
    return {
        "voices": [
            {
                "id": VOICE_ID,
                "label": "Ancash masculino 01 (base Ayacucho MMS, Fase 0)",
                "gender": "masculino",
                "langs": ["qu-ancash", "quy", "es"],
                "model_id": MODEL_ID,
            }
        ]
    }


@app.post("/speak")
def speak(payload: SpeakRequest):
    if payload.voice != VOICE_ID:
        raise HTTPException(status_code=404, detail=f"voice desconocida: {payload.voice}")
    if payload.lang not in ("qu-ancash", "quy", "qu", "es"):
        raise HTTPException(status_code=422, detail=f"lang no soportada: {payload.lang}")

    text = normalize_ancash(payload.text[:MAX_CHARS])
    if not text:
        raise HTTPException(status_code=422, detail="texto vacío tras normalizar")

    try:
        tokenizer, model, model_sr = get_model()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"modelo no disponible: {e}")

    import torch

    waves: list[np.ndarray] = []
    try:
        with torch.no_grad():
            for chunk in split_chunks(text):
                inputs = tokenizer(chunk, return_tensors="pt")
                out = model(**inputs).waveform[0].cpu().numpy()
                waves.append(out.astype(np.float32))
                # pausa corta entre frases (0.15s)
                waves.append(np.zeros(int(model_sr * 0.15), dtype=np.float32))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error de síntesis: {e}")

    audio = np.concatenate(waves) if waves else np.zeros(0, dtype=np.float32)
    # remuestreo simple a 16k si el checkpoint usa otra tasa
    if model_sr != SAMPLE_RATE_OUT and len(audio):
        idx = np.linspace(0, len(audio) - 1, int(len(audio) * SAMPLE_RATE_OUT / model_sr))
        audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)

    peak = np.max(np.abs(audio)) if len(audio) else 0.0
    if peak > 0:
        audio = (audio / peak * 0.9).astype(np.float32)

    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE_OUT, format="WAV", subtype="PCM_16")
    return Response(
        content=buf.getvalue(),
        media_type="audio/wav",
        headers={"X-Voice": VOICE_ID, "X-Model": MODEL_ID},
    )
