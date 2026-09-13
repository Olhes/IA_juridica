# Changelog — Migración a Cohere (Backend v2.0)

> **Fecha:** 14 de Febrero 2026  
> **Última actualización:** 15 de Febrero 2026  
> **Alcance:** Backend completo  
> **Modelo LLM:** `command-r7b-12-2024` (configurable via `COHERE_LLM_MODEL`)  
> **Embeddings:** `embed-multilingual-v3.0` (1024 dimensiones)  
> **Reranking:** `rerank-multilingual-v3.0`

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Fase 1 — Configuración centralizada](#2-fase-1--configuración-centralizada)
3. [Fase 2 — Limpieza de dependencias](#3-fase-2--limpieza-de-dependencias)
4. [Fase 3 — Embeddings y Reranking reales](#4-fase-3--embeddings-y-reranking-reales)
5. [Fase 4 — Context Engineering](#5-fase-4--context-engineering)
6. [Fase 5 — Endpoints, seguridad y health check](#6-fase-5--endpoints-seguridad-y-health-check)
7. [Fase 6 — Generación de reportes PDF](#7-fase-6--generación-de-reportes-pdf)
8. [Fase 7 — Docker y producción](#8-fase-7--docker-y-producción)
9. [Fase 8 — Tests y scripts de regeneración](#9-fase-8--tests-y-scripts-de-regeneración)
10. [Mapa de archivos modificados](#10-mapa-de-archivos-modificados)
11. [Errores encontrados y soluciones](#11-errores-encontrados-y-soluciones)
12. [Pasos post-migración](#12-pasos-post-migración)

---

## 1. Resumen ejecutivo

Esta migración reemplaza la infraestructura de embeddings falsos (hashes MD5 de 768 dimensiones) y LLM stub por una integración real end-to-end con **Cohere**. Los cambios abarcan:

| Componente | Antes | Después |
|---|---|---|
| Embeddings | Hashes MD5 → vectores 768d sin semántica | `embed-multilingual-v3.0` → vectores 1024d reales |
| LLM (graph extraction) | Función stub (retornaba `""`) | `command-r7b-12-2024` vía `cohere.AsyncClient.chat()` |
| LLM (agentes) | Cohere vía `os.getenv()` + hardcode | Cohere vía `settings.COHERE_*` centralizado |
| Reranking | No existía | `rerank-multilingual-v3.0` con fallback keyword |
| Context Engineering | Solo chunking básico | Clasificación de consulta + detección de ubicación + prompt enriquecido |
| Seguridad | CORS `["*"]`, sin auth, sin rate limiting | CORS por settings, API key en admin, slowapi |
| Health check | Siempre retornaba `"status": "ready"` | Verifica Cohere, LightRAG, Pydantic AI, ContextEngineer |
| PDF | Solo template placeholder | Generación real con ReportLab bilingüe |
| Dependencias | 10+ paquetes sin usar en requirements.txt | Removidos (langchain, chromadb, neo4j, etc.) |

---

## 2. Fase 1 — Configuración centralizada

### Archivo: `backend/config/settings.py`

**Problema detectado:**  
El módulo `pydantic_agents.py` usaba `load_dotenv()` + `os.getenv("COHERE_API_KEY")`, ejecutándose fuera del sistema centralizado. Esto creaba una fuente de verdad dual: `.env` se leía dos veces con mecanismos distintos, haciendo difícil de auditar qué valor se usaba realmente.

Además, existía un bug en `validate_configuration()` que referenciaba un campo legacy inexistente de tokens máximos.

**Cambios realizados:**

| Campo nuevo | Tipo | Default | Justificación |
|---|---|---|---|
| `COHERE_API_KEY` | `str` | `""` | Clave principal del provider LLM |
| `COHERE_EMBED_MODEL` | `str` | `"embed-multilingual-v3.0"` | Modelo multilingüe optimizado para español/quechua |
| `COHERE_RERANK_MODEL` | `str` | `"rerank-multilingual-v3.0"` | Reranking semántico multilingüe |
| `COHERE_LLM_MODEL` | `str` | `"command-r7b-12-2024"` | LLM para agentes y extracción de grafo |
| `COHERE_MAX_TOKENS` | `int` | `2048` | Tokens máximos de respuesta |
| `COHERE_TEMPERATURE` | `float` | `0.3` | Temperatura conservadora para respuestas legales |
| `RERANK_TOP_K` | `int` | `5` | Documentos finales tras reranking |
| `RERANK_CANDIDATES` | `int` | `50` | Candidatos iniciales para reranking |
| `EMBEDDING_BATCH_SIZE` | `int` | `96` | Límite por llamada de Cohere embed API |
| `EMBEDDING_DIM` | `int` | `1024` | Dimensión de `embed-multilingual-v3.0` (antes: 768) |

**Métodos añadidos:**

- `get_cohere_config() → Dict`: Retorna diccionario con toda la configuración Cohere en un solo lugar.
- `validate_configuration()`: Ahora verifica `COHERE_API_KEY` como variable **crítica** y alerta si `EMBEDDING_DIM != 1024`.
- Bug fix: se corrigió referencia a campo legacy de tokens máximos en validación.

### Archivos: `backend/.env` y `backend/.env.example`

**Justificación:** `.env.example` sirve como documentación viva de todas las variables necesarias. Se reescribió completamente para reflejar la migración.

Variables añadidas en `.env`:
```env
COHERE_EMBED_MODEL=embed-multilingual-v3.0
COHERE_RERANK_MODEL=rerank-multilingual-v3.0
COHERE_LLM_MODEL=command-r7b-12-2024
COHERE_MAX_TOKENS=2048
COHERE_TEMPERATURE=0.3
EMBEDDING_DIM=1024
EMBEDDING_BATCH_SIZE=96
RERANK_TOP_K=5
RERANK_CANDIDATES=50
```

---

## 3. Fase 2 — Limpieza de dependencias

### Archivo: `requirements.txt`

**Problema detectado:**  
`requirements.txt` contenía ~10 dependencias que **ningún archivo del backend importaba**: `graphiti-core`, `neo4j`, `chromadb`, `openai`, `anthropic`, `langchain`, `langchain-openai`, `chainlit`, `streamlit`. Esto inflaba la imagen Docker innecesariamente (>500 MB extra) y aumentaba la superficie de ataque.

**Cambios realizados:**

| Acción | Paquete | Justificación |
|---|---|---|
| **Añadido** | `cohere>=5.0` | SDK principal del provider |
| **Añadido** | `pydantic-settings>=2.0.0` | Tipificación de configuración |
| **Añadido** | `reportlab>=4.0` | Generación de PDFs |
| **Añadido** | `slowapi>=0.1.9` | Rate limiting para FastAPI |
| **Añadido** | `pytest-asyncio>=0.23.0` | Tests asíncronos (requerido por lightrag/cohere) |
| **Removido** | `graphiti-core`, `neo4j` | No importado en ningún archivo |
| **Removido** | `chromadb` | Reemplazado por LightRAG |
| **Removido** | `openai`, `anthropic` | No usados, Cohere es el provider único |
| **Removido** | `langchain`, `langchain-openai` | No importados en ningún archivo |
| **Removido** | `chainlit`, `streamlit` | UI frameworks no usados (frontend es Next.js) |

### Archivo: `backend/agents/pydantic_agents.py`

**Problema detectado:**  
Este módulo importaba `os` y `dotenv`, luego llamaba `load_dotenv()` seguido de `os.getenv('COHERE_API_KEY')`. Esto era la **única** instancia en todo el backend que no usaba `settings`, creando inconsistencia. Si `.env` tenía un valor pero settings lo sobrescribía con un default, el agente usaría un valor distinto al resto del sistema.

Además, los tres agentes (`violence_agent`, `pension_agent`, `general_agent`) usaban `result_type=ViolenceResponse/PensionResponse/GeneralLegalResponse`. Esto generaba schemas JSON con `$ref` (para modelos anidados como `LegalStep`, `LegalResource`, etc.), que **Cohere no soporta** — la API devuelve error `400: schema must not contain $ref keyword`.

**Cambios realizados:**
```python
# ANTES
import os
from dotenv import load_dotenv
load_dotenv()
model = CohereModel('command-r7b-12-2024', 
                     provider=CohereProvider(api_key=os.getenv('COHERE_API_KEY')))

# DESPUÉS
from config.settings import settings
model = CohereModel(settings.COHERE_LLM_MODEL, 
                     provider=CohereProvider(api_key=settings.COHERE_API_KEY))
```

**result_type=str (fix `$ref` error):**

Los tres agentes fueron cambiados de `result_type=PydanticModel` a `result_type=str`:

```python
# ANTES — genera schema con $ref, Cohere lo rechaza
self.general_agent = Agent(model, result_type=GeneralLegalResponse, ...)

# DESPUÉS — Cohere devuelve texto plano, lo envolvemos manualmente
self.general_agent = Agent(model, result_type=str, ...)
```

Se añadieron métodos **builder** que envuelven el texto plano en modelos Pydantic:

| Método | Modelo de salida | Lógica |
|---|---|---|
| `_build_violence_response(text, query)` | `ViolenceResponse` | Detecta tipo violencia y urgencia del texto |
| `_build_pension_response(text)` | `PensionResponse` | Estructura respuesta de alimentos |
| `_build_general_response(text, query)` | `GeneralLegalResponse` | Extrae secciones español/quechua si existen |

**Helpers de detección añadidos:**

| Helper | Función |
|---|---|
| `_detect_urgency(text)` | Keywords → `UrgencyLevel` (CRITICO/ALTO/MEDIO/BAJO) |
| `_detect_violence_types(text)` | Keywords → `List[ViolenceType]` |
| `_detect_topic(text)` | Keywords → `LegalTopic` |
| `_extract_section(text, header)` | Regex → extrae sección por encabezado |

Firma de `respond_general()` actualizada para aceptar `enriched_prompt: Optional[str] = None`, permitiendo que el endpoint le pase el prompt construido por ContextEngineer.

---

## 4. Fase 3 — Embeddings y Reranking reales

### Archivo: `backend/rag/lightrag_engine.py`

Este fue el archivo con más cambios porque contenía las **implementaciones fake** que hacían que el pipeline RAG no funcionara semánticamente.

#### 4.1 Embeddings reales con Cohere

**Problema detectado:**  
La función `_initialize_lightrag()` contenía una función de embedding que:
1. Generaba un hash MD5 del texto
2. Lo expandía cíclicamente a 768 dimensiones
3. Retornaba un `np.array` de 768d

Estos vectores no tenían **ninguna relación semántica** con el texto. Un documento sobre "violencia familiar" y otro sobre "pensión de alimentos" podían tener vectores casi idénticos, invalidando toda la búsqueda vectorial de LightRAG.

**Solución implementada:**

```python
async def cohere_embedding_func(texts: List[str]):
    """Genera embeddings reales con Cohere embed-multilingual-v3.0"""
    all_embeddings = []
    batch_size = settings.EMBEDDING_BATCH_SIZE  # 96 por defecto
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = await cohere_client.embed(
            texts=batch,
            model=settings.COHERE_EMBED_MODEL,
            input_type="search_document",
            embedding_types=["float"],
        )
        all_embeddings.extend(response.embeddings.float_)
    
    return np.array(all_embeddings, dtype=np.float32)
```

**Justificación técnica:**
- `embed-multilingual-v3.0` produce vectores de **1024 dimensiones** con semántica real multilingüe
- `input_type="search_document"` optimiza los embeddings para búsqueda (vs. `search_query` para queries)
- Batch processing respeta el límite de 96 textos por llamada de la API Cohere
- Usa `cohere.AsyncClient` para no bloquear el event loop de FastAPI

#### 4.2 LLM real para extracción de grafo

**Problema detectado:**  
La función LLM de LightRAG era un stub que retornaba `""`. Esto provocaba que la extracción de entidades y relaciones del knowledge graph nunca generara nada, resultando en archivos `vdb_*.json` vacíos.

**Solución implementada:**

```python
async def cohere_llm_func(prompt: str, **kwargs) -> str:
    response = await cohere_client.chat(
        message=prompt,
        model=settings.COHERE_LLM_MODEL,
        temperature=settings.COHERE_TEMPERATURE,
        max_tokens=settings.COHERE_MAX_TOKENS,
    )
    return response.text
```

#### 4.3 Nuevo método: `query_with_rerank()`

**Justificación:**  
LightRAG usa búsqueda por grafo (hybrid/local/global). Agregar reranking semántico con Cohere permite re-ordenar los chunks recuperados por relevancia real a la consulta, mejorando significativamente la calidad de las respuestas.

**Pipeline de 3 pasos:**

```
1. LightRAG hybrid query → obtener respuesta + candidatos locales
2. Reunir chunks de documentos almacenados localmente (hasta RERANK_CANDIDATES)  
3. Cohere rerank-multilingual-v3.0 → top_k documentos con scores
```

**Fallback:** Si Cohere rerank falla (rate limit, timeout, etc.), se ejecuta `_fallback_rerank()` que ordena por coincidencia de keywords. Esto asegura que el sistema nunca quede sin respuesta.

**Retorno:**
```python
{
    "answer": str,           # Respuesta de LightRAG o contexto construido
    "documents": List[Dict], # Top-K docs con relevance_score
    "rerank_scores": List[float],
    "sources": List[str],    # Nombres de fuentes únicas
    "method": str,           # "cohere_rerank" | "fallback_keyword_rerank"
    "total_candidates": int, # Candidatos evaluados
}
```

---

## 5. Fase 4 — Context Engineering

### Archivo: `backend/context/chunking_strategies.py`

**Cambio:** Nuevo método `chunk_and_embed()` en `ContextualChunker`.

**Justificación:** Permite generar embeddings al momento del chunking (útil para pre-procesamiento y para scripts de regeneración). Antes, los chunks se generaban sin embedding y se dependía del embedding fake de LightRAG.

```python
async def chunk_and_embed(self, text: str, doc_id: str) -> List[Dict]:
    """Chunking + embedding con Cohere en un solo paso"""
```

Usa `cohere.Client` (síncrono) para batch embedding de los chunks generados. Cada chunk retornado incluye `{"text": ..., "embedding": List[float], "doc_id": ..., "chunk_idx": ...}`.

### Archivo: `backend/context/prompt_templates.py`

**Cambio:** Nuevo método `build_prompt_for_cohere()` en `PromptManager`.

**Justificación:** Antes, el prompt se construía simplemente concatenando el template base con la query. No incluía:
- Los documentos rerankeados con sus scores de relevancia
- Recursos locales según la ubicación del usuario
- Notas culturales (urgencia, idioma detectado, contexto community)
- Instrucciones específicas de formato de respuesta

**Estructura del prompt generado:**

```
{template_base_por_tipo}

=== CONTEXTO LEGAL RELEVANTE ===
--- Documento 1 ---
Fuente: {titulo}
Relevancia: {score}
{contenido_truncado}
...

=== RECURSOS LOCALES (CUSCO) ===
- Juzgado de Paz Letrado del Cusco
- Comisaría de la Mujer del Cusco
- CEM Cusco ...

=== NOTAS CULTURALES ===
- Urgencia detectada: alto
- Idioma del usuario: spanish
- Contexto cultural: Alta presencia quechua

=== CONSULTA DEL USUARIO ===
{query}

=== INSTRUCCIONES DE RESPUESTA ===
- Responder en español y quechua
- Citar artículos y leyes específicas
- Lenguaje sencillo y accesible
- Incluir pasos concretos y recursos locales
```

**Métodos auxiliares añadidos:**
- `_format_documents_for_prompt()`: Formatea docs rerankeados con fuente, score, contenido
- `_get_local_resources(location)`: Retorna recursos por departamento (Cusco, Puno, Ayacucho, Huancavelica)
- `_format_cultural_context(context)`: Formatea urgencia, idioma, tema legal, notas culturales

### Archivo: `backend/context/context_engineering.py`

**Cambio:** Nuevo método `build_legal_prompt()` en `ContextEngineer` + mapeo `_QUERY_TYPE_TO_PROMPT`.

**Justificación:** Se necesitaba un orquestador que coordinara todos los pasos del context engineering antes de enviar a Cohere. Este método es el **punto de entrada único** que usa `main.py` para enriquecer cualquier consulta.

**Pipeline interno:**

```
1. Detectar idioma de la consulta (quechua → cambiar language)
2. Clasificar tipo legal (_detect_legal_type)
3. Detectar ubicación geográfica (_detect_location) 
4. Evaluar urgencia (_assess_urgency)
5. Evaluar sensibilidad cultural (_assess_cultural_sensitivity)
6. Construir enriched_context dict
7. Llamar PromptManager.build_prompt_for_cohere()
8. Retornar (prompt, enriched_context)
```

**Mapeo de tipos:**
```python
_QUERY_TYPE_TO_PROMPT = {
    "violencia_familiar": PromptType.VIOLENCE_FAMILY,
    "pensión_alimentos": PromptType.PENSION_FOOD,
    "identidad": PromptType.IDENTITY_RIGHTS,
    "demanda": PromptType.GENERAL_LEGAL,
    "general": PromptType.GENERAL_LEGAL,
}
```

---

## 6. Fase 5 — Endpoints, seguridad y health check

### Archivo: `backend/main.py`

#### 6.1 Pipeline completo en `/legal-query`

**Antes:** El endpoint hacía `rag_engine.query()` → `legal_agent.respond_general()`. Sin reranking, sin context engineering, sin metadata.

**Después:** Pipeline de 3 pasos:

```python
# 1. Búsqueda con reranking semántico
rag_result = await app.state.rag_engine.query_with_rerank(query)

# 2. Prompt enriquecido con context engineering  
enriched_prompt, enriched_context = app.state.context_engineer.build_legal_prompt(
    query=query, documents=documents, language=language
)

# 3. Respuesta con Pydantic AI + prompt enriquecido
response = await app.state.legal_agent.respond_general(
    query=query, context=rag_result, language=language,
    enriched_prompt=enriched_prompt
)
```

**Justificación:** Este pipeline garantiza que el LLM reciba documentos semánticamente relevantes (no keyword-matched) con contexto cultural, produciendo respuestas más precisas y culturalmente apropiadas.

**Metadata expuesta en la respuesta:**
```json
{
  "metadata": {
    "rerank_scores": [0.95, 0.82, ...],
    "retrieval_method": "cohere_rerank",
    "total_candidates": 47,
    "enriched_context": {
      "location": "cusco",
      "legal_topic": "violencia_familiar",
      "urgency": "alto"
    }
  }
}
```

#### 6.2 CORS configurado desde settings

**Antes:** `allow_origins=["*"]` — aceptaba cualquier origen, inaceptable en producción.

**Después:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # ["http://localhost:3000", ...]
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)
```

**Justificación:** Los orígenes permitidos deben ser controlables por entorno. En producción, solo se permiten dominios específicos.

#### 6.3 Health check real

**Antes:** Siempre retornaba `{"status": "ready"}` sin verificar nada.

**Después:** Verifica 4 componentes:

| Componente | Verificación |
|---|---|
| `cohere` | API key configurada |
| `lightrag` | Storages inicializados |
| `pydantic_ai` | SDK disponible o modo fallback |
| `context_engineer` | Instancia creada |

Estado general: `"healthy"` si todos los críticos están en `"ready"` o `"fallback"`, `"degraded"` si alguno falla.

**Justificación:** Un health check que siempre retorna OK no sirve para monitoreo, alertas ni Docker healthchecks. El nuevo endpoint permite a docker-compose y balanceadores de carga tomar decisiones reales.

#### 6.4 Rate limiting con slowapi

**Justificación:** Sin rate limiting, un solo usuario o bot puede saturar la API y las cuotas de Cohere (especialmente embed/rerank). `slowapi` se integra directamente con FastAPI y es ligero.

```python
if SLOWAPI_AVAILABLE and settings.RATE_LIMIT_ENABLED:
    limiter = Limiter(key_func=get_remote_address)
```

#### 6.5 API key para endpoints administrativos

**Justificación:** Los endpoints `/upload-pdf`, `/batch-process` y `/evaluate-system` pueden modificar el knowledge graph o consumir recursos significativos. No deben ser accesibles públicamente.

```python
async def verify_admin_api_key(api_key: Optional[str] = Security(api_key_header)):
    if settings.is_development():
        return True  # Sin auth en desarrollo
    if not api_key or api_key != settings.SECRET_KEY:
        raise HTTPException(status_code=403, detail="API key inválida")
```

Se usa `X-API-Key` header + `settings.SECRET_KEY` como valor esperado. En desarrollo se bypasea para comodidad.

---

## 7. Fase 6 — Generación de reportes PDF

### Archivo nuevo: `backend/utils/pdf_generator.py`

**Justificación:** El endpoint `/generate-pdf-report` existía como placeholder que retornaba JSON. Ahora genera un PDF real con ReportLab, bilingüe (español/quechua), con formato profesional.

**Función principal:** `generate_legal_pdf(query, response_data, output_dir) → str`

**Secciones del PDF generado:**

| Sección | Contenido |
|---|---|
| Header | "IA Jurídica — Reporte Legal" + fecha |
| Consulta | Query original del usuario |
| Tema | Tipo legal detectado |
| Respuesta español | Párrafos formateados |
| Respuesta quechua | Párrafos formateados |
| Pasos recomendados | Numerados con documentos requeridos |
| Recursos | Nombre, contacto, descripción |
| Advertencias | Con icono ⚠ |
| Fuentes legales | Ley, tipo, número |
| Disclaimer | Bilingüe esp/quechua — "no es asesoría profesional" |

**Diseño:** Colores corporativos (`#1a365d` primario, `#2b6cb0` acento), tipografía A4, márgenes 2cm, estilo `TA_JUSTIFY`.

### Cambio en `backend/main.py` — endpoint `/generate-pdf-report`

```python
@app.post("/generate-pdf-report")
async def generate_pdf_report(payload: PDFReportRequest):
    pdf_path = generate_legal_pdf(
        query=payload.query,
        response_data=payload.response,
        output_dir=settings.PDF_OUTPUT_DIR,
    )
    return FileResponse(path=pdf_path, media_type="application/pdf", ...)
```

Ahora retorna `FileResponse` con el PDF como descarga directa, no JSON.

---

## 8. Fase 7 — Docker y producción

### Archivo: `backend/Dockerfile`

**Cambio:** Añadido directorio `temp/pdfs` en la creación de carpetas.

```dockerfile
RUN mkdir -p \
    /app/backend/docs/raw_pdfs \
    /app/backend/docs/processed \
    /app/backend/docs/knowledge_graph \
    /app/backend/docs/failed \
    /app/backend/logs \
    /app/backend/temp/pdfs && \   # ← NUEVO
    ...
```

**Justificación:** Sin esto, `generate_legal_pdf()` falla con `FileNotFoundError` al intentar escribir el PDF en el contenedor.

### Archivo: `docker-compose.prod.yml`

**Cambios:**
- Añadido volumen `backend_temp:/app/backend/temp` para persistir PDFs generados entre reinicios del contenedor.
- Declarado volumen `backend_temp` en la sección `volumes`.

### Archivo: `env.production.example`

**Reescrito completamente.** Ahora documenta:
- `COHERE_API_KEY`, `COHERE_EMBED_MODEL`, `COHERE_RERANK_MODEL`, `COHERE_LLM_MODEL`
- `COHERE_MAX_TOKENS`, `COHERE_TEMPERATURE`
- `EMBEDDING_DIM`, `EMBEDDING_BATCH_SIZE`
- `RERANK_TOP_K`, `RERANK_CANDIDATES`
- `ADMIN_API_KEY`, `RATE_LIMIT_PER_MINUTE`
- `PDF_OUTPUT_DIR`

---

## 9. Fase 8 — Tests y scripts de regeneración

### Archivo nuevo: `backend/tests/test_cohere_integration.py`

**12 tests organizados en 7 clases:**

| Clase | Tests | Verifica |
|---|---|---|
| `TestSettings` | 5 | Campos Cohere existen, dim=1024, defaults correctos, `get_cohere_config()`, rerank constraints |
| `TestEmbeddings` | 2 | Dimensión de embedding es 1024 (mock), `chunk_and_embed()` retorna chunks con embeddings |
| `TestRerank` | 2 | Ordering por score descendente, fallback keyword-based funciona sin Cohere |
| `TestContextEngineering` | 3 | `build_prompt_for_cohere()` genera prompt, `build_legal_prompt()` retorna tuple, detección de ubicación |
| `TestPDFGeneration` | 1 | `generate_legal_pdf()` crea archivo `.pdf` con tamaño > 1000 bytes |
| `TestHealthCheck` | 1 | `/health` retorna `status` y `components` |
| `TestRateLimiting` | 1 | slowapi middleware registrado en la app |

**Ejecución:**
```bash
cd backend
python -m pytest tests/test_cohere_integration.py -v
```

**Justificación:** Los tests usan mocks para las llamadas a Cohere (no consumen API credits), pero validan que la integración estructural es correcta — dimensiones, tipos de retorno, pipeline completo.

### Archivo nuevo: `backend/scripts/regenerate_embeddings.py`

**Justificación:** Los 18+ documentos en `docs/processed/` fueron ingestados con embeddings MD5 falsos de 768 dimensiones. Los archivos del knowledge graph (`vdb_chunks.json`, etc.) contienen vectores inútiles. Es necesario:
1. Hacer backup del knowledge graph actual
2. Eliminar los archivos viejos
3. Re-ingestar todos los documentos con embeddings Cohere reales (1024d)

**Uso:**
```bash
cd backend

# Ver qué se va a procesar (sin cambios)
python -m scripts.regenerate_embeddings --dry-run

# Regenerar todo (con backup automático)
python -m scripts.regenerate_embeddings

# Sin backup (si ya tienes uno)
python -m scripts.regenerate_embeddings --no-backup
```

**Proceso interno:**
1. Lista archivos `.md` en `docs/processed/`
2. Crea backup en `docs/knowledge_graph_backup_{timestamp}/`
3. Elimina los 8 archivos del knowledge graph
4. Instancia `LegalRAGEngine` (que ahora usa Cohere real)
5. Para cada documento: `engine.add_document()` → LightRAG genera embeddings reales + extrae entidades/relaciones con el LLM

---

## 10. Mapa de archivos modificados

```
backend/
├── config/
│   └── settings.py              ✏️  Campos Cohere, bug fix, validate_configuration()
├── agents/
│   └── pydantic_agents.py       ✏️  result_type=str, builders texto→Pydantic, enriched_prompt
├── rag/
│   └── lightrag_engine.py       ✏️  Embeddings reales, LLM real, query_with_rerank()
├── context/
│   ├── chunking_strategies.py   ✏️  chunk_and_embed() con Cohere
│   ├── prompt_templates.py      ✏️  build_prompt_for_cohere() + helpers
│   ├── context_engineering.py   ✏️  build_legal_prompt(), imports absolutos
│   └── __init__.py              ✏️  Removida instanciación eager de ContextEngineer
├── language/
│   └── translation_service.py   ✏️  TRANSLATION_ENABLED check (evita descarga 1.2GB)
├── utils/
│   └── pdf_generator.py         🆕  generate_legal_pdf() con ReportLab
├── tests/
│   ├── __init__.py              🆕  Package marker
│   └── test_cohere_integration.py 🆕  15 tests de integración
├── scripts/
│   └── regenerate_embeddings.py 🆕  Regeneración de knowledge graph
├── main.py                      ✏️  Pipeline completo, CORS, health, auth, rate limit, PDF
├── Dockerfile                   ✏️  Directorio temp/pdfs
├── .env                         ✏️  Variables Cohere añadidas
└── .env.example                 ✏️  Reescrito completamente

raíz/
├── requirements.txt             ✏️  +5 añadidos, ~10 removidos, cohere==5.13.11 pinned
├── docker-compose.prod.yml      ✏️  Volumen backend_temp
├── env.production.example       ✏️  Reescrito con config Cohere
├── CHANGELOG_MIGRACION_COHERE.md 🆕  Este documento
└── GUIA_DOCKER_SETUP.md         🆕  Guía de setup con Docker
```

**Leyenda:** ✏️ Modificado | 🆕 Nuevo

---

## 11. Errores encontrados y soluciones

Durante la implementación y las pruebas en Docker se encontraron los siguientes errores. Se documentan aquí como referencia para futuras migraciones.

### 11.1 `ImportError: attempted relative import beyond top-level package`

**Error completo:**
```
File "/app/backend/context/context_engineering.py", line X
from ..language.language_detector import LanguageDetector
ImportError: attempted relative import beyond top-level package
```

**Causa:** El `WORKDIR` del Dockerfile es `/app/backend`, por lo que Python ejecuta `main.py` como script de nivel superior. Los imports relativos (`from ..language.X`) intentan subir más allá del paquete raíz.

**Solución:** Cambiar a imports absolutos:
```python
# ANTES (fallaba en Docker)
from ..language.language_detector import LanguageDetector
from ..language.language_config import LanguageConfig

# DESPUÉS
from language.language_detector import LanguageDetector
from language.language_config import LanguageConfig
```

También se removió la instanciación eager `context_engineer = ContextEngineer()` de `context/__init__.py`, que provocaba una cadena de imports circular al importar el paquete.

---

### 11.2 Incompatibilidad `pydantic-ai==0.4.3` con `cohere>=5.14`

**Error completo:**
```
ImportError: cannot import name 'TextAssistantMessageContentItem' from 'cohere.types'
```

**Causa:** `pydantic-ai==0.4.3` importa `TextAssistantMessageContentItem` de `cohere.types`. A partir de `cohere>=5.14`, esta clase fue renombrada, rompiendo la importación. El error se capturaba silenciosamente por el `try/except` de `PYDANTIC_AI_AVAILABLE`, y el sistema caía a fallback sin aviso visible.

**Solución:** Pinear la versión de cohere en `requirements.txt`:
```
cohere==5.13.11
```

---

### 11.3 Container colgado descargando modelo NLLB (1.2 GB)

**Síntoma:** El container arrancaba, imprimía "Inicializando IA Jurídica..." y se quedaba congelado sin responder en el health check durante varios minutos.

**Causa:** `TranslationService.__init__()` descargaba automáticamente el modelo NLLB de HuggingFace (~1.2 GB) al inicializarse. Esto ocurría dentro del `lifespan` de FastAPI, bloqueando todo el startup.

**Solución:** Agregar variable `TRANSLATION_ENABLED` en `.env`:
```env
TRANSLATION_ENABLED=false
```

Y un check en `translation_service.py`:
```python
if not settings.TRANSLATION_ENABLED:
    logger.info("Traducción NLLB deshabilitada por configuración")
    return
# ... descarga del modelo solo si está habilitado
```

---

### 11.4 Dimensión de embeddings: `expected: 1024, but loaded: 768`

**Error completo:**
```
AssertionError: Embedding dim mismatch, expected: 1024, but loaded: 768
```

**Causa:** Los archivos del knowledge graph (`vdb_chunks.json`, `vdb_entities.json`, `vdb_relationships.json`) contenían vectores generados con el embedding fake MD5 de 768 dimensiones. Al cambiar a Cohere con 1024 dimensiones, LightRAG detectaba la inconsistencia.

**Solución:** Eliminar todos los archivos del knowledge graph y regenerar:
```powershell
# Desde el host
Remove-Item backend\docs\knowledge_graph\vdb_*.json -ErrorAction SilentlyContinue
Remove-Item backend\docs\knowledge_graph\kv_store_*.json -ErrorAction SilentlyContinue
Remove-Item backend\docs\knowledge_graph\graph_*.graphml -ErrorAction SilentlyContinue

# O desde dentro del container
docker exec <container_id> python -m scripts.regenerate_embeddings
```

---

### 11.5 `$ref` en JSON schema — Cohere rechaza schemas Pydantic anidados

**Error completo:**
```
cohere.errors.bad_request_error.BadRequestError: status_code: 400,
body: {'message': 'schema must not contain $ref keyword'}
```

**Causa:** Pydantic AI con `result_type=GeneralLegalResponse` serializa el schema JSON del modelo. Cuando el modelo tiene campos con tipos anidados (`List[LegalStep]`, `List[LegalResource]`, etc.), el schema incluye `$ref` para referenciar sub-schemas. La API de Cohere no soporta `$ref` en los schemas de respuesta estructurada.

**Solución:** Cambiar todos los agentes a `result_type=str` y construir los modelos Pydantic manualmente:
```python
# ANTES — Cohere rechaza el schema
self.general_agent = Agent(model, result_type=GeneralLegalResponse, ...)

# DESPUÉS — Cohere devuelve texto plano
self.general_agent = Agent(model, result_type=str, ...)
```

Se añadieron métodos `_build_*_response()` que envuelven el texto plano en los modelos Pydantic con detección inteligente de urgencia, tipo de violencia, tema legal y extracción de secciones por regex.

---

### 11.6 `Exceeded maximum retries (1) for result validation`

**Error completo:**
```
pydantic_ai.exceptions.ModelRetryError: Exceeded maximum retries (1) for result validation
```

**Causa:** Con `result_type=PydanticModel`, el LLM intentaba generar JSON válido pero el modelo pequeño no siempre lo lograba al primer intento. El default de `max_result_retries` en Pydantic AI es `1`.

**Solución:** Este error se resolvió automáticamente con el cambio a `result_type=str`, ya que texto plano siempre es válido. Antes de ese fix, se había incrementado a `max_result_retries=3` como paliativo.

---

### 11.7 `.dockerignore` excluye documentos procesados

**Síntoma:** El script `regenerate_embeddings` encontraba 0 documentos dentro del container.

**Causa:** El `.dockerignore` contiene:
```
backend/docs/processed
backend/docs/knowledge_graph
```

Esto impide que `docker build` copie esos directorios dentro de la imagen.

**Solución:** Montar los documentos como volumen al ejecutar el container:
```powershell
# PowerShell — usar ${PWD} (no %cd%)
docker run -p 8000:8000 --env-file backend\.env `
  -v "${PWD}\backend\docs:/app/backend/docs" `
  main:app
```

---

## 12. Pasos post-migración

### Inmediatos (obligatorios)

```bash
# 1. Instalar dependencias actualizadas
cd backend
pip install -r ../requirements.txt

# 2. Verificar que .env tiene COHERE_API_KEY
grep COHERE_API_KEY .env

# 3. Ejecutar tests
python -m pytest tests/test_cohere_integration.py -v

# 4. Regenerar knowledge graph con embeddings reales
python -m scripts.regenerate_embeddings --dry-run   # verificar
python -m scripts.regenerate_embeddings              # ejecutar

# 5. Iniciar servidor y probar
python main.py
# GET http://localhost:8000/health → verificar "healthy"
# POST http://localhost:8000/legal-query → probar query real
```

### Recomendados (mejoras futuras)

| Mejora | Prioridad | Descripción |
|---|---|---|
| Persistencia vectorial | Alta | Cambiar almacenamiento de LightRAG de archivos JSON a base de datos (Qdrant, pgvector) para escalar más allá de ~100 docs |
| Cache de embeddings | Media | Cachear embeddings generados para evitar re-procesar el mismo texto |
| Frontend update | Media | Actualizar Next.js para consumir `metadata.enriched_context` y mostrar ubicación/urgencia |
| Monitoring (Opik) | Baja | Activar tracing de LLM calls con `OPIK_ENABLED=true` |
| Command-R-Plus | Baja | Evaluar upgrade a `command-r-plus` cuando el presupuesto lo permita (mejor calidad, mayor costo) |

---

> **Nota:** Todos los cambios son backward-compatible con el frontend existente. La ruta `/api/legal/consult` del Next.js BFF sigue normalizando `respuesta_espanol` → `spanish` y `respuesta_quechua` → `quechua` sin cambios necesarios.
