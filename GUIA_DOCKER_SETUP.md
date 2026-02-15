# Guía: Levantar IA Jurídica con Docker + Ingesta de documentos

> **Última actualización:** 15 de Febrero 2026  
> **Prerequisitos:** Docker Desktop, una API key de Cohere, PowerShell  
> **Tiempo estimado:** ~10 minutos (build) + ~5-15 minutos (ingesta, depende de la cantidad de docs)

---

## Índice

1. [Estructura del proyecto](#1-estructura-del-proyecto)
2. [Configurar el archivo .env](#2-configurar-el-archivo-env)
3. [Construir la imagen Docker](#3-construir-la-imagen-docker)
4. [Levantar el container](#4-levantar-el-container)
5. [Verificar que el servidor está corriendo](#5-verificar-que-el-servidor-está-corriendo)
6. [Ingesta de documentos (regenerar embeddings)](#6-ingesta-de-documentos-regenerar-embeddings)
7. [Probar una consulta legal](#7-probar-una-consulta-legal)
8. [Comandos útiles de Docker](#8-comandos-útiles-de-docker)
9. [Errores comunes y soluciones](#9-errores-comunes-y-soluciones)
10. [Flujo completo resumido](#10-flujo-completo-resumido)

---

## 1. Estructura del proyecto

```
IA_juridica/
├── backend/
│   ├── Dockerfile            ← imagen Docker del backend
│   ├── main.py               ← FastAPI app
│   ├── .env                  ← variables de entorno (no se sube a git)
│   ├── docs/
│   │   ├── raw_pdfs/         ← PDFs originales
│   │   ├── processed/        ← documentos .md convertidos
│   │   └── knowledge_graph/  ← vectores, entidades, relaciones (LightRAG)
│   └── scripts/
│       └── regenerate_embeddings.py  ← script de ingesta
├── requirements.txt          ← dependencias Python
└── .dockerignore             ← excluye docs/processed y knowledge_graph del build
```

> **Nota importante:** El `.dockerignore` excluye `backend/docs/processed` y `backend/docs/knowledge_graph`. Esto significa que esos archivos **no se copian** dentro de la imagen Docker. Se montan como **volumen** al correr el container.

---

## 2. Configurar el archivo .env

Crear `backend/.env` (o editar el existente):

```env
# === COHERE (obligatorio) ===
COHERE_API_KEY=tu_api_key_cohere_aqui
COHERE_EMBED_MODEL=embed-multilingual-v3.0
COHERE_RERANK_MODEL=rerank-multilingual-v3.0
COHERE_LLM_MODEL=command-r-plus-08-2024
COHERE_MAX_TOKENS=2048
COHERE_TEMPERATURE=0.3

# === Embeddings / RAG ===
EMBEDDING_DIM=1024
EMBEDDING_BATCH_SIZE=96
RERANK_TOP_K=5
RERANK_CANDIDATES=50
RAG_ENGINE=lightrag
EMBEDDING_MODEL=embed-multilingual-v3.0

# === Directorios ===
DOCS_ROOT_DIR=./docs
RAW_PDF_DIR=./docs/raw_pdfs
PROCESSED_DIR=./docs/processed
KNOWLEDGE_GRAPH_DIR=./docs/knowledge_graph

# === Servidor ===
PORT=5000
NODE_ENV=development

# === Seguridad ===
SECRET_KEY=tu_secret_key_aqui
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=900

# === Traducción NLLB ===
# false = no descargar modelo de 1.2GB al iniciar (Cohere traduce directamente)
TRANSLATION_ENABLED=false

# === Logging ===
LOG_LEVEL=INFO
```

### Variables críticas

| Variable | Obligatoria | Descripción |
|---|---|---|
| `COHERE_API_KEY` | **Sí** | Sin esto, nada funciona |
| `COHERE_LLM_MODEL` | Sí | Modelo para agentes (ej: `command-r-plus-08-2024`) |
| `TRANSLATION_ENABLED` | Recomendado en `false` | Si es `true`, descarga modelo NLLB de ~1.2 GB al arrancar |
| `EMBEDDING_DIM` | Sí | Debe ser `1024` para `embed-multilingual-v3.0` |

---

## 3. Construir la imagen Docker

Desde la **raíz del proyecto** (donde está `requirements.txt`):

```powershell
cd C:\Users\Lenovo\Desktop\IA_juridica

docker build -t main:app -f backend/Dockerfile .
```

La primera vez tarda ~3-5 minutos (descarga imagen Python + instala dependencias).

### Qué hace el Dockerfile

1. Usa `python:3.12-slim` como base
2. Instala dependencias del sistema (`build-essential`, `libgomp1`, etc.)
3. Copia `requirements.txt` e instala las dependencias Python
4. Copia todo el directorio `backend/` (excepto lo que excluye `.dockerignore`)
5. Crea directorios necesarios (`docs/`, `logs/`, `temp/pdfs/`)
6. Ejecuta con `uvicorn main:app --port 8000 --workers 2`

---

## 4. Levantar el container

```powershell
docker run -p 8000:8000 --env-file backend\.env `
  -v "${PWD}\backend\docs:/app/backend/docs" `
  main:app
```

### Explicación de los flags

| Flag | Propósito |
|---|---|
| `-p 8000:8000` | Expone puerto 8000 (FastAPI) |
| `--env-file backend\.env` | Carga variables de entorno |
| `-v "${PWD}\backend\docs:/app/backend/docs"` | Monta directorio `docs/` como volumen |
| `main:app` | Nombre de la imagen |

### ¿Por qué el volumen `-v`?

El `.dockerignore` excluye `backend/docs/processed` y `backend/docs/knowledge_graph` del build. Esto es intencional — son datos que pueden ser grandes y cambiantes. El volumen permite:

- Acceder a los archivos `.md` procesados desde el container
- Que el knowledge graph se persista entre reinicios del container
- Editar documentos en el host y verlos reflejados en el container

### Verificar que arrancó correctamente

En los logs deberías ver:
```
Inicializando IA Jurídica...
Componentes inicializados
INFO:     Started server process [1]
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> **⚠️ Si se queda colgado en "Inicializando"**, revisa que `TRANSLATION_ENABLED=false` en tu `.env`. Ver [sección 9.2](#92-container-colgado-al-iniciar).

---

## 5. Verificar que el servidor está corriendo

```powershell
# Health check
Invoke-RestMethod -Uri http://localhost:8000/health | ConvertTo-Json -Depth 5
```

Respuesta esperada:
```json
{
  "status": "healthy",
  "components": {
    "cohere": { "status": "ready" },
    "lightrag": { "status": "ready" },
    "pydantic_ai": { "status": "ready" },
    "context_engineer": { "status": "ready" }
  }
}
```

Si `pydantic_ai` aparece como `"fallback"`, no bloquea el flujo principal actual. El backend usa Cohere directo para generación/streaming. Ver [sección 9.3](#93-cohere-no-inicializado-o-respuestas-basicas).

---

## 6. Ingesta de documentos (regenerar embeddings)

### ¿Cuándo es necesario?

- **Primera vez** que levantas el container (knowledge graph vacío)
- Después de agregar nuevos documentos `.md` a `docs/processed/`
- Si borras los archivos del knowledge graph
- Si cambias de modelo de embeddings (ej: 768d → 1024d)

### Paso 1: Verificar que hay documentos

```powershell
# Obtener el ID del container
docker ps

# Listar documentos disponibles (dry-run)
docker exec <container_id> python -m scripts.regenerate_embeddings --dry-run
```

Deberías ver algo como:
```
Documentos procesados encontrados: 18
  - Definición normativa de la violencia psicológica...
  - El delito de omisión de la asistencia familiar...
  ...
Modo dry-run: no se realizan cambios
```

> **Si muestra 0 documentos:** Verifica que montaste el volumen `-v` correctamente. Ver [sección 9.5](#95-script-de-ingesta-encuentra-0-documentos).

### Paso 2: Limpiar knowledge graph antiguo (si existe)

Si ya había archivos con embeddings viejos (768d), hay que limpiarlos primero:

```powershell
# Desde PowerShell en el host:
Remove-Item backend\docs\knowledge_graph\vdb_*.json -ErrorAction SilentlyContinue
Remove-Item backend\docs\knowledge_graph\kv_store_*.json -ErrorAction SilentlyContinue
Remove-Item backend\docs\knowledge_graph\graph_*.graphml -ErrorAction SilentlyContinue
```

### Paso 3: Ejecutar la ingesta

```powershell
docker exec <container_id> python -m scripts.regenerate_embeddings
```

Esto hace:
1. Crea un backup del knowledge graph actual (si existe)
2. Limpia todos los archivos del KG
3. Lee cada documento `.md` de `docs/processed/`
4. Para cada documento:
   - Genera embeddings reales con Cohere `embed-multilingual-v3.0` (1024d)
   - Extrae entidades y relaciones con el LLM Cohere
   - Almacena todo en el knowledge graph de LightRAG

**Duración estimada:** ~30-60 segundos por documento (depende de longitud y rate limits de Cohere). Para 18 docs ≈ 10-15 minutos.

**Output esperado:**
```
Documentos procesados encontrados: 18
Limpiando knowledge graph antiguo...
  Eliminado: vdb_chunks.json
  ...
Re-ingesta con Cohere embeddings (1024d)...
Procesando: Definición normativa de la violencia psicológica...
  ✓ Definición normativa de la violencia psicológica...
  ...
Resultados: 18 OK, 0 fallidos de 18 total
¡Regeneración completa!
```

### Paso 4: Verificar la ingesta

```powershell
# Verificar que se crearon los archivos del knowledge graph
Get-ChildItem backend\docs\knowledge_graph\
```

Deberías ver:
```
vdb_chunks.json
vdb_entities.json
vdb_relationships.json
kv_store_doc_status.json
kv_store_full_docs.json
kv_store_text_chunks.json
kv_store_llm_response_cache.json
graph_chunk_entity_relation.graphml
```

---

## 7. Probar una consulta legal

```powershell
$body = @{
    query = "¿Cuáles son los pasos para denunciar violencia familiar?"
    language = "spanish"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/legal-query `
  -Method POST `
  -ContentType "application/json" `
  -Body $body | ConvertTo-Json -Depth 10
```

Respuesta exitosa (simplificada):
```json
{
  "success": true,
  "query": "¿Cuáles son los pasos para denunciar violencia familiar?",
  "response": {
    "tema": "violencia_familiar",
    "respuesta_espanol": "Para denunciar violencia familiar en Perú...",
    "respuesta_quechua": "...",
    "pasos_recomendados": [...],
    "recursos": [...],
    "confianza": 0.85
  },
  "sources": ["Definición normativa...", "Ley 30364..."],
  "metadata": {
    "rerank_scores": [0.95, 0.82],
    "retrieval_method": "cohere_rerank",
    "enriched_context": {
      "legal_topic": "violencia_familiar",
      "urgency": "alto"
    }
  }
}
```

> **Si falla con 500:** Puede ser que el knowledge graph esté vacío (no se corrió la ingesta). Ver [sección 6](#6-ingesta-de-documentos-regenerar-embeddings).

---

## 8. Comandos útiles de Docker

### Ver logs en tiempo real
```powershell
docker logs -f <container_id>
```

### Entrar al container con shell
```powershell
docker exec -it <container_id> bash
```

### Correr tests dentro del container
```powershell
docker exec <container_id> python -m pytest tests/test_cohere_integration.py -v
```

### Detener el container
```powershell
docker stop <container_id>
```

### Reconstruir imagen después de cambios en el código
```powershell
docker build -t main:app -f backend/Dockerfile .
```

### Ver consumo de recursos
```powershell
docker stats <container_id>
```

---

## 9. Errores comunes y soluciones

### 9.1 `ImportError: attempted relative import beyond top-level package`

```
from ..language.language_detector import LanguageDetector
ImportError: attempted relative import beyond top-level package
```

**Causa:** El `WORKDIR` del Dockerfile es `/app/backend`. Los imports relativos (`from ..`) intentan salir del paquete raíz.

**Solución:** Ya corregido en el código actual. Los imports en `context/context_engineering.py` usan paths absolutos:
```python
from language.language_detector import LanguageDetector  # ✅
```

---

### 9.2 Container colgado al iniciar

El container imprime "Inicializando IA Jurídica..." y no avanza durante minutos.

**Causa:** `TranslationService` intenta descargar el modelo NLLB (~1.2 GB) de HuggingFace.

**Solución:** Verificar en `backend/.env`:
```env
TRANSLATION_ENABLED=false
```

Luego reconstruir la imagen y reiniciar.

---

### 9.3 Cohere no inicializado o respuestas básicas

El health check muestra `cohere: { status: "not_configured" }` o las respuestas salen muy básicas.

**Causa:** Falta `COHERE_API_KEY` o no se cargó correctamente el `.env` dentro del container.

**Solución:**
```powershell
# 1) Verifica variable dentro del container
docker exec <container_id> printenv COHERE_API_KEY

# 2) Si está vacía, corrige backend/.env o .env.production
# 3) Reconstruye y levanta de nuevo
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

---

### 9.4 `AssertionError: Embedding dim mismatch, expected: 1024, but loaded: 768`

**Causa:** Archivos viejos del knowledge graph con embeddings de 768 dimensiones.

**Solución:**
```powershell
# Borrar archivos viejos desde el host
Remove-Item backend\docs\knowledge_graph\vdb_*.json -ErrorAction SilentlyContinue
Remove-Item backend\docs\knowledge_graph\kv_store_*.json -ErrorAction SilentlyContinue
Remove-Item backend\docs\knowledge_graph\graph_*.graphml -ErrorAction SilentlyContinue

# Reiniciar container + re-ingestar
docker exec <container_id> python -m scripts.regenerate_embeddings
```

---

### 9.5 Script de ingesta encuentra 0 documentos

```
Documentos procesados encontrados: 0
```

**Causa:** El volumen no se montó correctamente, o no hay archivos `.md` en `backend/docs/processed/`.

**Solución:**
```powershell
# 1. Verificar que existen los archivos locales
Get-ChildItem backend\docs\processed\*.md | Measure-Object

# 2. Verificar el mount desde dentro del container
docker exec <container_id> ls -la /app/backend/docs/processed/

# 3. Si está vacío, revisar la sintaxis del -v:
# PowerShell usa ${PWD} — NO uses %cd% (eso es CMD)
docker run -p 8000:8000 --env-file backend\.env `
  -v "${PWD}\backend\docs:/app/backend/docs" `
  main:app
```

---

### 9.6 Error de streaming o chat con Cohere (400/401/429)

```
Cohere API error: status_code: 401/429/400
```

**Causa:**
- `401`: API key inválida o revocada
- `429`: límite/rate limit alcanzado
- `400`: payload inválido o parámetros fuera de rango

**Solución:**
```powershell
# Validar key
docker exec <container_id> printenv COHERE_API_KEY

# Revisar logs recientes
docker compose -f docker-compose.prod.yml logs backend --tail=120
```

Si es `429`, reduce concurrencia o espera ventana de rate limit.

---

### 9.7 `%cd%` no funciona en PowerShell

```powershell
# ❌ Esto NO funciona en PowerShell
docker run -v "%cd%\backend\docs:/app/backend/docs" main:app

# ✅ Usar ${PWD} en PowerShell
docker run -v "${PWD}\backend\docs:/app/backend/docs" main:app

# ✅ O en CMD (Command Prompt):
docker run -v "%cd%\backend\docs:/app/backend/docs" main:app
```

---

## 10. Flujo completo resumido

```powershell
# ── 1. Configurar ──
# Editar backend/.env con tu COHERE_API_KEY

# ── 2. Construir imagen ──
cd C:\Users\Lenovo\Desktop\IA_juridica
docker build -t main:app -f backend/Dockerfile .

# ── 3. Limpiar KG viejo (si es necesario) ──
Remove-Item backend\docs\knowledge_graph\vdb_*.json -ErrorAction SilentlyContinue
Remove-Item backend\docs\knowledge_graph\kv_store_*.json -ErrorAction SilentlyContinue
Remove-Item backend\docs\knowledge_graph\graph_*.graphml -ErrorAction SilentlyContinue

# ── 4. Levantar container ──
docker run -d -p 8000:8000 --env-file backend\.env `
  -v "${PWD}\backend\docs:/app/backend/docs" `
  --name ia-juridica `
  main:app

# ── 5. Esperar a que arranque (~10 seg) ──
Start-Sleep -Seconds 10
Invoke-RestMethod http://localhost:8000/health | ConvertTo-Json

# ── 6. Ingesta de documentos ──
docker exec ia-juridica python -m scripts.regenerate_embeddings

# ── 7. Probar consulta ──
$body = '{"query": "¿Cómo denunciar violencia familiar?", "language": "spanish"}'
Invoke-RestMethod -Uri http://localhost:8000/legal-query `
  -Method POST -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 5

# ── 8. (Opcional) Correr tests ──
docker exec ia-juridica python -m pytest tests/test_cohere_integration.py -v
```

---

## Arquitectura del pipeline

```
                    ┌──────────────────────┐
                    │   POST /legal-query  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  LightRAG hybrid     │ ← busca en knowledge graph
                    │  query + candidates  │   (embeddings 1024d Cohere)
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Cohere Rerank       │ ← reordena por relevancia
                    │  rerank-v3.0         │   semántica (top_k=5)
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Context Engineer    │ ← clasifica consulta, detecta
                    │  build_legal_prompt  │   ubicación, urgencia, idioma
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  LegalAgent (Cohere) │ ← Cohere LLM genera respuesta
                    │  chat / chat_stream  │   en texto plano
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  _build_*_response() │ ← envuelve texto en modelo
                    │  → Pydantic model    │   Pydantic estructurado
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  JSON Response       │ ← respuesta al frontend
                    │  + metadata + sources│
                    └──────────────────────┘
```

---

> **Documento relacionado:** Ver [CHANGELOG_MIGRACION_COHERE.md](CHANGELOG_MIGRACION_COHERE.md) para el detalle técnico completo de todos los cambios implementados.
