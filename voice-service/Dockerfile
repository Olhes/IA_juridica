# Servicio TTS Quechua Ancash — Meta MMS (CPU)
# Fase 0: checkpoint base facebook/mms-tts-quy (Ayacucho, el más cercano a Ancash qws/qxa).
# Licencia checkpoint MMS: CC-BY-NC-4.0 (ver docs/voice/VOICE_TTS_ANCASH.md).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_CACHE=/models \
    HF_HOME=/models \
    MODEL_ID=facebook/mms-tts-quy

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

# Torch CPU explícito (imagen ~2.5GB con torch; solo este servicio lo lleva,
# el backend principal sigue liviano sin torch).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY app.py /app/app.py

EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
