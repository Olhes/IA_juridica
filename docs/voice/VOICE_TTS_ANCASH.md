# Voz TTS Quechua Ancash — Meta MMS (voz masculina)

> Estado a 2026-10-11: **Fase 0, Fase 1 e ingesta del léxico (§6 pasos 1–3) implementadas y verificadas** (imagen Docker construida, 3 audios de prueba, proxy backend con 11 tests en verde, `ancash_lexicon.json` con 1993 pares + 45 entidades conectado al normalizador con 6 tests en verde). Stack: backend FastAPI (`backend/main.py`, `backend/modules/*`) + frontend Next.js + `docker-compose.yml` (postgres/redis/qdrant/**voice**). Pendiente: indexado RAG del léxico (§6 paso 4), Common Voice y fine-tune Fase 2.

## 1) Resumen y decisiones

- **Objetivo:** dar voz al chatbot RAG en quechua ancashino (masculina), empezando por las variedades **Sihuas (qws)** y **Chiquián (qxa)**.
- **Motor:** **Meta MMS-TTS (VITS)** en CPU, servido como microservicio FastAPI independiente (`voice-service/app.py`) para no engordar el backend principal con torch.
- **Checkpoint base:** `facebook/mms-tts-quy` (quechua **Ayacucho**, el más cercano disponible). **MMS no publica checkpoint ancashino `qws`/`qxa`**, por eso la voz v1 suena con acento base Ayacucho y el acento ancashino real queda para Fase 2 (fine-tune).
- **Voz lógica v1:** `ancash-masculino-01` (única voz; `GET /voices` la lista).
- **Contrato bilingüe v1:** `lang ∈ {qu-ancash, quy, qu, es}`. El español se sintetiza con el mismo checkpoint `quy` (limitación conocida, §8).
- **Claves de implementación verificadas en código:** normalización a minúsculas sin puntuación (`normalize_ancash`), chunking por frases con límite 350 caracteres (`split_chunks`), semilla fija `set_seed(555)` para reproducibilidad VITS, remuestreo de salida a **16 kHz** (`SAMPLE_RATE_OUT`), normalización de pico a 0.9, respuesta `audio/wav` con headers `X-Voice` / `X-Model`.
- **Respuesta a la pregunta del Excel:** **ya ingerido.** Los archivos `QuechuaSihuas.xlsx` y `QuechuaChiquian.xlsx` (corpus paralelo `Oración_Quechua|Oración_Español`) están copiados en `backend/docs/voice/corpus/` e ingeridos en `backend/docs/voice/ancash_lexicon.json` (1993 pares + 45 entidades) y conectados al normalizador vía `canonical_form()` + `gloss_hint()`. Detalle y pasos restantes (RAG, Common Voice, fine-tune) en §6.

## 2) Fases y estado

| Fase | Alcance | Estado real |
|------|---------|-------------|
| **Fase 0 — Spike Docker** | Microservicio `voice-service` + servicio `voice` en compose + colección de pruebas. Sin tocar el backend principal. | ✅ **Verificada 2026-10-04.** Imagen `ia_juridica-voice` construida (torch 2.14.1+cpu, transformers 5.18.0). `GET /health` → `model_loaded=true`. 3 audios generados en `backend/docs/voice/samples_fase0/`: `01_sihuas_zorro.wav` (2.1 s), `02_frase_legal_qu.wav` (5.2 s), `03_frase_legal_es.wav` (4.6 s). |
| **Fase 1 — Backend proxy** | `backend/modules/voice/` (settings `VOICE_*`, routes `GET /voice/health` + `GET /voice/voices` + `POST /voice/speak`, proxy HTTP al `voice-service` + caché Redis). Frontend llama solo al backend `:8000`. | ✅ **Implementada y testeada 2026-10-04.** Archivos: `models/voice_models.py`, `modules/voice/{services/voice_client.py, services/text_normalizer_ancash.py, controllers/voice_routes.py}`, router registrado en `main.py`, vars en `.env.example`, 11 tests en `backend/tests/unit/test_voice_proxy.py` (verde). Cliente real probado contra servicio vivo (bytes `RIFF` OK). |
| **Fase 2 — Fine-tune ancashino** | Ingesta Excels Sihuas/Chiquián → `backend/docs/voice/ancash_lexicon.json` → normalizador + RAG; descarga Common Voice v26 `qws`+`qxa` filtrando género masculino; fine-tune VITS ancashino + voz propia. | ❌ **Pendiente.** Ver §6 para pasos concretos. |

## 3) Arquitectura y archivos creados

```
frontend Next.js ──POST /voice/speak──▶ backend :8000 ✅ (proxy + caché Redis, X-Cache HIT/MISS)
                                        │ httpx, timeout 120 s, rate-limit 20/min
                                        ▼
                              voice-service :8001 ──▶ facebook/mms-tts-quy (Ayacucho, /models)
                              audio/wav 16kHz ◀── VITS + normalización ancashina
```

| Archivo | Qué hace |
|---------|----------|
| `voice-service/app.py` | Microservicio FastAPI: `GET /health` (estado + `model_loaded`), `GET /voices` (voz lógica `ancash-masculino-01`), `POST /speak` (`{text, lang, voice}` → `audio/wav`). Env: `MODEL_ID`, `VOICE_ID`, `MAX_CHARS=800`, `SAMPLE_RATE_OUT=16000`. Lazy-load del modelo con lock, chunking 350 chars + pausa 0.15 s entre frases, `set_seed(555)`, remuestreo a 16 kHz, pico a 0.9. |
| `voice-service/Dockerfile` | Imagen `python:3.12-slim` + `build-essential curl libsndfile1`. Instala `torch` CPU explícito y luego `requirements.txt`. `HF_HUB_CACHE=/models`, `MODEL_ID=facebook/mms-tts-quy`. `uvicorn app:app --host 0.0.0.0 --port 8001 --workers 1`. |
| `voice-service/requirements.txt` | `fastapi==0.129.0`, `uvicorn[standard]==0.41.0`, `transformers>=4.33`, `accelerate`, `numpy>=2.4.2,<3.0`, `scipy`, `soundfile`. |
| `docker-compose.yml` (servicio `voice`) | Build `./voice-service`. Puertos `127.0.0.1:8001:8001`. Volumen `mms_models:/models`. Env `MODEL_ID=${VOICE_MODEL_ID:-facebook/mms-tts-quy}`, `VOICE_ID=${VOICE_ID:-ancash-masculino-01}`, `MAX_CHARS=800`, `SAMPLE_RATE_OUT=16000`. Healthcheck HTTP a `/health` con `start_period: 120s`. Red `ia_juridica_network`. |
| `voice-service/IA_Juridica_Voice.postman_collection.json` | Colección Postman importable en Bruno. Carpeta 1 **Voice Service (directo :8001)**: Health, Voices, Speak Quechua Ancash, Speak Frase Legal, Speak Español, Speak Lang inválido (422). Carpeta 2 **Backend proxy (:8000)**: Voice Health, Voice Speak, Legal Query — **ya funcionales** (requieren backend `:8000` + Redis arriba; `503` si `voice-service` está caído). Vars `baseVoiceUrl=http://localhost:8001`, `baseApiUrl=http://localhost:8000`, `voiceId=ancash-masculino-01`. |
| `backend/models/voice_models.py` | Contratos Pydantic `extra="forbid"`: `SpeakRequest` (`text` 1–800, `lang` ∈ {qu-ancash, quy, qu, es} default `qu-ancash`, `voice` default `ancash-masculino-01`), `VoiceListResponse`, `VoiceHealthResponse`. ⚠️ **Al crear la rama de voz, agregarlo con `git add -f`** (`.gitignore:70` ignora `models/`, igual que pasó con `chat_models.py` que ya está trackeado). |
| `backend/modules/voice/services/voice_client.py` | `VoiceTTSClient` (httpx): `health()`, `voices()`, `speak()` → `(wav_bytes, model_id)`. Errores → `VoiceServiceUnavailable` (routes responden 503; 422 downstream se propaga sin reintento). Singleton `voice_client`. El backend **no** instala torch. |
| `backend/modules/voice/services/text_normalizer_ancash.py` | Espeja `normalize_ancash()` del voice-service + `voice_cache_key()` = `tts:<sha256(normalizado\|lang\|voz)>` (mismo texto con distinta puntuación/mayúsculas = mismo caché). |
| `backend/modules/voice/controllers/voice_routes.py` | `APIRouter(prefix="/voice")`: `GET /health` (200 siempre; `degraded` + `downstream_error` si cae el servicio), `GET /voices` (proxy), `POST /speak` (rate-limit `VOICE_RATE_LIMIT`, 404 voz desconocida, caché Redis `audio_b64` TTL `VOICE_CACHE_TTL=86400` solo si ≤2 MB, headers `X-Cache HIT/MISS`, `X-Voice`, `X-Model`). Mismo patrón de auth-debug que `chat_routes`. |
| `backend/config/settings.py` (+ `.env.example`) | `VOICE_ENABLED`, `VOICE_SERVICE_URL=http://localhost:8001`, `VOICE_ID`, `VOICE_TIMEOUT_SECONDS=120`, `VOICE_CACHE_TTL=86400`, `VOICE_MAX_CHARS=800`, `VOICE_MAX_CACHED_BYTES=2MB`, `VOICE_RATE_LIMIT=20/minute`. |
| `backend/main.py` | `app.include_router(voice_router)` junto a `chat_router` (con `try/except` para no tumbar el arranque si el módulo falta). Rutas vivas: `/voice/health`, `/voice/voices`, `/voice/speak`. |
| `backend/tests/unit/test_voice_proxy.py` | 11 tests (verde 2026-10-04): normalizador, clave canónica, validación Pydantic, MISS→HIT, 404/422/503, health ok/degraded. Sin IO externo (mocks). |

## 4) API del voice-service

Base: `http://localhost:8001`. Sin auth (solo bind a loopback en compose).

### `GET /health`

```bash
curl -s http://localhost:8001/health
# {"status":"ok","model_id":"facebook/mms-tts-quy","model_loaded":false,
#  "torch_available":true,"voice":"ancash-masculino-01"}
# model_loaded=false hasta el primer POST /speak (descarga ~400MB a /models).
```

### `GET /voices`

```bash
curl -s http://localhost:8001/voices
# {"voices":[{"id":"ancash-masculino-01","label":"Ancash masculino 01 (base Ayacucho MMS, Fase 0)",
#  "gender":"masculino","langs":["qu-ancash","quy","es"],"model_id":"facebook/mms-tts-quy"}]}
```

### `POST /speak` → `audio/wav`

```bash
# Quechua ancashino (caso principal)
curl -s -X POST http://localhost:8001/speak \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Atuqmi ashkallata mikun\",\"lang\":\"qu-ancash\",\"voice\":\"ancash-masculino-01\"}" \
  --output ancash.wav

# Frase legal tipo RAG
curl -s -X POST http://localhost:8001/speak \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Ley 30364 qamta protegenki, denuncia comisariaman churanqui\",\"lang\":\"qu-ancash\",\"voice\":\"ancash-masculino-01\"}" \
  --output legal_qu.wav

# Español (mismo checkpoint quy — ver §8)
curl -s -X POST http://localhost:8001/speak \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"La ley 30364 te protege, puedes denunciar en la comisaria\",\"lang\":\"es\",\"voice\":\"ancash-masculino-01\"}" \
  --output legal_es.wav
```

Errores: `404` voz desconocida (`voice` ≠ `ancash-masculino-01`); `422` `lang` no soportado o texto vacío tras normalizar; `503` modelo no descargable; `500` fallo de síntesis. Límite `MAX_CHARS=800` (Pydantic `max_length=800`); textos largos se dividen en chunks de 350 caracteres.

## 5) Uso con Docker Compose y con Bruno/Postman

### Docker Compose

```bash
# Desde C:\Users\Lenovo\Desktop\IA_juridica
docker compose build voice        # ⚠️ pesado: Torch CPU ~800MB; si hay timeout, reintentar (usa caché por capas)
docker compose up -d voice        # levanta solo el TTS
curl -s http://localhost:8001/health
# Primera síntesis = descarga facebook/mms-tts-quy (~400MB) a volumen mms_models; tarda minutos.
docker compose logs -f voice      # vigilar descarga/carga del modelo
docker volume inspect ia_juridica_mms_models  # el nombre real lleva prefijo del proyecto
```

Variables opcionales (`.env` o entorno): `VOICE_MODEL_ID`, `VOICE_ID`. En producción no exponer `8001`; el frontend debe llamar al backend `:8000/voice/*` (Fase 1).

### Bruno / Postman

1. Bruno → `Open Collection` → `Import` → `Postman (.json)` → seleccionar `voice-service/IA_Juridica_Voice.postman_collection.json`.
2. Flujo: carpeta **Voice Service (directo :8001)** → `Health` (`model_loaded`), `Voices`, `Speak Quechua Ancash` (200 `audio/wav`; en Bruno usar **Save response to file** → `*.wav` para escuchar).
3. Carpeta **Backend proxy (:8000)** → `Voice Health` / `Voice Speak` **ya responden** (requieren backend + Redis en marcha: `docker compose up -d redis` y `uv run python backend/main.py`; `503` si `voice-service` está caído). `Legal Query` sirve para obtener `respuesta_quechua` del RAG y pegarla como `text` en `Speak`. Nota: el primer `Speak` tras levantar `voice` tarda minutos (descarga del modelo); los repetidos devuelven `X-Cache: HIT` al instante.

## 6) Gap Excel + Common Voice (qué falta y pasos concretos)

**Estado 2026-10-11:** pasos 1–3 ✅ hechos y verificados en repo (1993 pares + 45 entidades en `backend/docs/voice/ancash_lexicon.json`, normalizador + hook RAG conectados, 6 tests verdes). Pasos 4–6 pendientes (indexado RAG, Common Voice, fine-tune). Detalle:

1. **Copiar e inspeccionar corpus:** ✅ Excels copiados a `backend/docs/voice/corpus/` (Sihuas 1000 filas + Chiquián N=1..1000 con datos; el resto de filas numeradas están vacías). Columnas `N|Variedad|Oración_Quechua|Oración_Español` + hoja `Etiquetado` (entidades tipo `Lima - ciudad`).
2. **Script de ingesta** ✅ `backend/scripts/ingest_ancash_lexicon.py` (openpyxl, sin pandas): `python scripts/ingest_ancash_lexicon.py` desde `backend/` → `ancash_lexicon.json` con `{meta, entries[{id,qu,es,variedad}], variant_index{es:[qu...]}, entities[{qu,es,tags,variedades}]}`. Resultado real: **1993 pares** (997 Sihuas + 996 Chiquián, 3 dups fuera), **45 entidades únicas** (las hojas Etiquetado se solapan al 100%), **10 glosas** con >1 variante quechua.
3. **Uso en normalizador:** ✅ `canonical_form()` en `text_normalizer_ancash.py` (grafía del corpus si hay match exacto normalizado; no-op sin léxico) aplicado en `POST /voice/speak` antes de caché y síntesis; `gloss_hint()` expone glosas para RAG/traducción. Tests en `backend/tests/unit/test_ancash_lexicon.py` (6/6 verde).
4. **Uso en RAG:** indexar `ancash_lexicon.json` como colección qdrant o boost léxico en `backend/modules/rag/` para respuestas `qu-ancash` con vocabulario local.
5. **Common Voice v26:** descargar clips `qws` + `qxa` (https://commonvoice.mozilla.org/datasets), filtrar `metadata.tsv` por `gender == male`, guardar manifiesto `backend/docs/voice/commonvoice_ancash_manifest.csv` (clip, variedad, duración, hash). Sin este filtro no hay voz masculina ancashina para Fase 2.
6. **Fase 2 (fine-tune VITS):** con el manifiesto + lexicon, fine-tunear `facebook/mms-tts-quy` hacia `ancash-masculino-01` propio (entrenamiento GPU fuera de compose), versionar checkpoint resultante y actualizar `VOICE_MODEL_ID` / `X-Model`.

## 7) Licencias y riesgo

| Activo | Licencia | Implicancia |
|--------|----------|-------------|
| Checkpoint `facebook/mms-tts-quy` (Meta MMS) | **CC-BY-NC-4.0 (No Comercial)** | ⚠️ **Uso académico/demostración OK; producción comercial PROHIBIDA** con este checkpoint. Requiere atribución a Meta/HuggingFace. El fine-tune Fase 2 **hereda la restricción NC** si parte de este checkpoint. |
| Audios Common Voice (referencia/entreno) | **CC0 (dominio público)** | ✅ Sin restricción; citar dataset por buenas prácticas, no obligatorio. |
| Código propio (`voice-service/`, proxy futuro) | Licencia del repo | ✅ Sin conflicto; el riesgo está solo en el **modelo**, no en el código. |

**Riesgo principal:** desplegar el servicio con checkpoint MMS en un producto que cobre o genere ingreso = violación de licencia. **Mitigación:** mantener flag `VOICE_MODEL_ID` para sustituir por checkpoint propio/CC0 en Fase 2, añadir aviso NC en README/frontend, y no publicar `/models` (volumen, no versionado).

## 8) Limitaciones v1

1. **Acento base Ayacucho, no ancashino.** `mms-tts-quy` es lo más cercano; Sihuas/Chiquián difieren en fonética y léxico. Se mitiga parcialmente con normalización, pero el timbre/acentos son ayacuchanos hasta Fase 2.
2. **Español con el mismo checkpoint.** `lang=es` se sintetiza con el modelo quechua → acento quechua marcado y peor prosodia en español. Modelo español dedicado fuera de alcance Fase 0/1.
3. **CPU y latencia.** VITS en CPU + descarga inicial ~400 MB; primera request lenta (minutos), siguientes de segundos según largo. `workers=1` + lock: sin concurrencia real.
4. **Proxy v1 sin auth real.** `backend/modules/voice/` existe con caché Redis (TTL 86400, audios ≤2 MB), rate-limit `20/minute` y logging loguru, pero usa el mismo patrón de auth-debug que `chat_routes` (principal opcional). Endurecer auth antes de exponer fuera de loopback.
5. **Normalización con léxico, pero sin números/siglas.** Minúsculas + limpieza de puntuación + `canonical_form()` con grafía del corpus `ancash_lexicon.json` (aplicado en `POST /voice/speak` antes de caché y síntesis) y `gloss_hint()` disponible para RAG/traducción. Pendiente: manejo de números/siglas legales y uso de `gloss_hint()` en `translation_service` + indexado RAG (§6 paso 4).

## 9) Próximos pasos (checklist)

- [x] `docker compose build voice` + `GET /health` → `model_loaded=true` tras primer `/speak` (2026-10-04, 3 wavs en `backend/docs/voice/samples_fase0/`).
- [x] Fase 1: `backend/modules/voice/` + settings `VOICE_*` + router en `main.py` + tests `backend/tests/unit/test_voice_proxy.py` (11/11 verde) + cliente real contra servicio vivo.
- [x] Ingerir Excels → `backend/docs/voice/ancash_lexicon.json` y conectar al normalizador + hook `gloss_hint` (2026-10-04).
- [ ] Indexar `ancash_lexicon.json` en el RAG (qdrant o boost léxico en `modules/rag/`) y usar `gloss_hint()` en `translation_service` como diccionario antes de Google Translate (§6 paso 4).
- [ ] Descargar Common Voice v26 `qws`+`qxa`, filtrar masculino, generar `commonvoice_ancash_manifest.csv` (§6 paso 5).
- [ ] Fase 2: fine-tune VITS ancashino masculino, publicar checkpoint propio, actualizar `VOICE_MODEL_ID` y revalidar colección Bruno + avisar cambio de licencia si aplica.
- [ ] Endurecer v1: rate-limit, `MAX_CHARS` por rol, métricas de latencia/errores, aviso de licencia NC en frontend.
