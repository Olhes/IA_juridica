# API Documentation — IA Jurídica v2.1

> **Base URL (desarrollo):** `http://localhost:8000`  
> **Base URL (producción):** ajustar según entorno de despliegue  
> **Content-Type:** `application/json` (salvo `/upload-pdf` = `multipart/form-data`, `/legal-query-stream` = `application/x-ndjson`)

---

## Tabla de contenidos

| Endpoint | Método | Descripción | Auth |
|---|---|---|---|
| [`/`](#-get-) | `GET` | Raíz — info de la API | No |
| [`/health`](#-get-health) | `GET` | Estado de los componentes del sistema | No |
| [`/legal-query`](#-post-legal-query) | `POST` | Consulta legal principal con RAG + validación | No |
| [`/legal-query-stream`](#-post-legal-query-stream) | `POST` | Consulta legal con respuesta en streaming | No |
| [`/documents`](#-get-documents) | `GET` | Lista de documentos indexados en RAG | No |
| [`/knowledge-graph`](#-get-knowledge-graph) | `GET` | Datos del grafo de conocimiento | No |
| [`/validation-stats`](#-get-validation-stats) | `GET` | Estadísticas del pipeline de validación | No |
| [`/generate-pdf-report`](#-post-generate-pdf-report) | `POST` | Genera y descarga reporte PDF | No |
| [`/upload-pdf`](#-post-upload-pdf) | `POST` | Sube y procesa un nuevo PDF (**admin**) | ✅ API Key |
| [`/batch-process`](#-post-batch-process) | `POST` | Procesa todos los PDFs pendientes (**admin**) | ✅ API Key |
| [`/evaluate-system`](#-post-evaluate-system) | `POST` | Ejecuta suite de evaluación (**admin**) | ✅ API Key |

---

## Autenticación

Los endpoints marcados con ✅ **API Key** requieren el header:

```
X-API-Key: <SECRET_KEY>
```

> En entorno de **desarrollo** (`ENVIRONMENT=development`), la verificación de API Key está deshabilitada y cualquier llamada es aceptada.

---

## Rate Limiting

Cuando `RATE_LIMIT_ENABLED=true`, el servidor limita las solicitudes a **100 requests por 15 minutos** por IP.  
Si se supera el límite, la API responde con `HTTP 429 Too Many Requests`.

---

## CORS

El servidor permite peticiones desde los siguientes orígenes por defecto:

- `http://localhost:3000`
- `http://localhost:3001`

Configurable vía variable de entorno `CORS_ORIGINS`.

---

## Endpoints públicos

### 🟢 `GET /`

Retorna información básica de la API. Útil para verificar que el servidor esté levantado.

**Response:**
```json
{
  "message": "IA Jurídica API v2.1 - Sistema Legal con Docling, RAG y Validación Anti-Alucinación"
}
```

---

### 🟢 `GET /health`

Health check completo que reporta el estado de todos los componentes internos del sistema.

**Response `200 OK`:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "environment": "development",
  "components": {
    "cohere": "ready",
    "lightrag": "ready",
    "pydantic_ai": "ready",
    "context_engineer": "ready",
    "response_validator": "ready",
    "llm_optimizer": "ready"
  }
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `status` | `string` | `"healthy"` si todos los componentes críticos están listos, `"degraded"` si alguno falla |
| `version` | `string` | Versión del sistema |
| `environment` | `string` | `"development"` o `"production"` |
| `components` | `object` | Estado individual de cada componente (`"ready"`, `"fallback"`, `"not_initialized"`, `"unavailable"`, `"error"`) |

**Componentes críticos** (determinan `status`): `cohere`, `lightrag`, `pydantic_ai`.

**Uso recomendado en el frontend:**
- Llamar al iniciar la app para mostrar un banner de estado.
- Polling opcional cada 30–60 segundos para detectar degradación del servicio.

---

### 🔵 `POST /legal-query`

**Endpoint no-stream (respuesta única).** Procesa una consulta legal con el pipeline completo:
1. Búsqueda RAG con reranking (Cohere)
2. Context Engineering (enriquecimiento del prompt con contexto jurídico y cultural)
3. Generación de respuesta con el LLM (Cohere `command-r7b-12-2024`)
4. Pipeline de validación anti-alucinación (hallucination detection + cross-check + self-correction)
5. Caché semántico (respuestas confiables se cachean por 1 hora)

**Request body:**
```json
{
  "query": "¿Cómo puedo denunciar violencia familiar?",
  "language": "spanish",
  "context": null
}
```

| Campo | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `query` | `string` (min 1 char) | ✅ | — | Consulta del usuario |
| `language` | `string` | ❌ | `"spanish"` | Idioma de la respuesta: `"spanish"` o `"quechua"` |
| `context` | `object \| null` | ❌ | `null` | Contexto adicional (no utilizado en versión actual) |

**Response `200 OK`:**
```json
{
  "success": true,
  "query": "¿Cómo puedo denunciar violencia familiar?",
  "language": "spanish",
  "cached": false,
  "response": {
    "tema": "violencia_familiar",
    "respuesta_espanol": "Para denunciar violencia familiar en Perú, debes...",
    "respuesta_quechua": "(Traducción quechua no disponible)",
    "pasos_recomendados": [
      {
        "paso": 1,
        "descripcion": "Acude a la comisaría de Mujeres más cercana",
        "documentos_requeridos": ["DNI"],
        "plazo": null,
        "lugar": "Comisaría de Mujeres"
      }
    ],
    "recursos": [
      {
        "nombre": "Línea 113",
        "tipo": "Línea de ayuda",
        "contacto": "113",
        "horario": "24/7",
        "descripcion": "Atención gratuita para mujeres"
      }
    ],
    "advertencias": [
      {
        "tipo": "Información",
        "mensaje": "Esta orientación no reemplaza asesoría legal profesional",
        "urgencia": "bajo"
      }
    ],
    "fuentes": [
      {
        "nombre": "Ley 30364",
        "tipo": "Ley",
        "numero": null,
        "enlace": null
      }
    ],
    "confianza": 0.85,
    "fecha_respuesta": "2026-02-22T15:00:00"
  },
  "sources": ["documento_legal_1.pdf", "ley_30364.pdf"],
  "validation": {
    "status": "passed",
    "confidence": "high",
    "confidence_score": 0.87,
    "hallucination_risk": 0.12,
    "is_grounded": true,
    "corrections_applied": 0,
    "flags": [],
    "cross_check": {
      "is_grounded": true,
      "overlap_score": 0.78,
      "ungrounded_claims": [],
      "supporting_chunks": ["chunk_text_1", "chunk_text_2"]
    },
    "cultural_issues": [],
    "warnings": [],
    "processing_time_ms": 1234.5,
    "validated_at": "2026-02-22T20:00:00"
  },
  "metadata": {
    "rerank_scores": [0.95, 0.87, 0.76],
    "retrieval_method": "hybrid",
    "total_candidates": 12,
    "enriched_context": {
      "location": "Lima",
      "legal_topic": "violencia_familiar",
      "urgency": "alto"
    },
    "optimizer_stats": {
      "total_queries": 5,
      "cache_hits": 1,
      "total_tokens_estimated": 4200
    }
  }
}
```

#### Esquemas de los objetos de respuesta

##### `response` — `GeneralLegalResponse`

| Campo | Tipo | Descripción |
|---|---|---|
| `tema` | `string` (enum) | Tema detectado: `violencia_familiar`, `pension_alimentos`, `medidas_proteccion`, `regimen_visitas`, `denuncias_procesos` |
| `respuesta_espanol` | `string` | Respuesta principal del LLM en español |
| `respuesta_quechua` | `string` | Respuesta en quechua (si `language="quechua"`) |
| `pasos_recomendados` | `LegalStep[]` | Lista de pasos del procedimiento |
| `recursos` | `LegalResource[]` | Recursos institucionales disponibles |
| `advertencias` | `LegalWarning[]` | Advertencias legales importantes |
| `fuentes` | `LegalSource[]` | Fuentes legales citadas |
| `confianza` | `float` [0–1] | Nivel de confianza interno del agente |
| `fecha_respuesta` | `datetime` | Timestamp de la respuesta |

##### `LegalStep`

| Campo | Tipo | Descripción |
|---|---|---|
| `paso` | `int` | Número de paso |
| `descripcion` | `string` | Descripción del paso |
| `documentos_requeridos` | `string[]` | Documentos necesarios |
| `plazo` | `string \| null` | Plazo estimado |
| `lugar` | `string \| null` | Lugar donde realizar el paso |

##### `LegalResource`

| Campo | Tipo | Descripción |
|---|---|---|
| `nombre` | `string` | Nombre del recurso o institución |
| `tipo` | `string` | Tipo (comisaría, juzgado, línea de ayuda, etc.) |
| `contacto` | `string \| null` | Teléfono, dirección o contacto |
| `horario` | `string \| null` | Horario de atención |
| `descripcion` | `string` | Descripción breve |

##### `LegalWarning`

| Campo | Tipo | Descripción |
|---|---|---|
| `tipo` | `string` | Categoría de la advertencia |
| `mensaje` | `string` | Texto de la advertencia |
| `urgencia` | `string` (enum) | `bajo`, `medio`, `alto`, `critico` |

##### `LegalSource`

| Campo | Tipo | Descripción |
|---|---|---|
| `nombre` | `string` | Nombre de la fuente |
| `tipo` | `string` | Tipo (`ley`, `código`, `artículo`) |
| `numero` | `string \| null` | Número identificador |
| `enlace` | `string \| null` | URL de la fuente |

##### `validation` — `ValidationReport`

| Campo | Tipo | Descripción |
|---|---|---|
| `status` | `string` (enum) | `passed`, `warned`, `corrected`, `failed` |
| `confidence` | `string` (enum) | `high` (≥0.80), `medium` (≥0.55), `low` (<0.55) |
| `confidence_score` | `float` [0–1] | Score numérico combinado (RAG + anti-hallucination + cross-check) |
| `hallucination_risk` | `float` [0–1] | Riesgo estimado de alucinación |
| `is_grounded` | `bool` | Si la respuesta está respaldada por el corpus RAG |
| `corrections_applied` | `int` | Número de auto-correcciones aplicadas |
| `flags` | `HallucinationFlag[]` | Patrones problemáticos detectados |
| `cross_check` | `CrossCheckSummary \| null` | Resultado del cross-check RAG ↔ LLM |
| `cultural_issues` | `string[]` | Observaciones de validación cultural |
| `warnings` | `string[]` | Advertencias del pipeline |
| `processing_time_ms` | `float` | Tiempo de procesamiento en milisegundos |
| `validated_at` | `datetime` | Timestamp de la validación |

**Guía para el frontend:**

```
validation.status === "failed"    → Mostrar advertencia prominente; sugerir asesoría profesional
validation.status === "corrected" → Indicar que la respuesta fue revisada automáticamente
validation.confidence === "low"   → Mostrar disclaimer de baja confianza
validation.is_grounded === false  → Indicar que puede no estar respaldado por documentos
```

**Errores:**

| Código | Situación |
|---|---|
| `500` | Error interno en el pipeline (RAG, LLM o validación) |

---

### 🔵 `POST /legal-query-stream`

Endpoint **streaming principal** del chat. Ejecuta el pipeline completo (RAG + Context Engineering + LLM + validación) y responde en **NDJSON** con eventos incrementales.

**Request body:** Idéntico a `/legal-query`

```json
{
  "query": "¿Qué es una medida de protección?",
  "language": "spanish"
}
```

**Response:**
- **Content-Type:** `application/x-ndjson`
- **Transfer-Encoding:** `chunked`
- **Headers:** `Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`

Cada línea del stream es un JSON independiente (`\n` delimitado):

1. Evento de texto parcial:
```json
{"type":"chunk","delta":"...texto incremental..."}
```

2. Evento final (payload estructurado completo):
```json
{
  "type": "final",
  "data": {
    "success": true,
    "query": "...",
    "language": "spanish",
    "cached": false,
    "response": {"tema": "...", "respuesta_espanol": "...", "fecha_respuesta": "2026-02-25T01:00:00"},
    "sources": [],
    "validation": {"status": "warned"},
    "metadata": {}
  }
}
```

3. Evento de error (si falla durante el stream):
```json
{"type":"error","error":"Legal query stream failed: ..."}
```

**Ejemplo de consumo en el frontend (JavaScript):**
```javascript
const response = await fetch('http://localhost:8000/legal-query-stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: '¿Qué es una medida de protección?', language: 'spanish' })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
let fullText = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  let nl = buffer.indexOf('\n');

  while (nl !== -1) {
    const line = buffer.slice(0, nl);
    buffer = buffer.slice(nl + 1);
    if (line.trim()) {
      const event = JSON.parse(line);
      if (event.type === 'chunk') {
        fullText += event.delta || '';
      }
      if (event.type === 'final') {
        // event.data contiene validation, sources, metadata y response
      }
    }
    nl = buffer.indexOf('\n');
  }
}
```

**Errores:**

| Código | Situación |
|---|---|
| `500` | Error al iniciar el stream antes de enviar eventos |

> **Nota:** El evento `final` ya incluye `validation`, `sources` y `metadata`; no hace falta una segunda llamada para completar la respuesta del chat.

---

### 🟢 `GET /documents`

Lista todos los documentos actualmente indexados en el motor RAG.

**Response `200 OK`:**
```json
{
  "success": true,
  "documents": [
    {
      "id": "ley_30364.pdf",
      "title": "ley_30364.pdf",
      "document_type": "legal_pdf",
      "source": "upload-pdf"
    }
  ]
}
```

**Uso en el frontend:** Mostrar al usuario qué documentos cubre el sistema.

---

### 🟢 `GET /knowledge-graph`

Retorna los datos del grafo de conocimiento construido por LightRAG a partir del corpus legal.

**Response `200 OK`:**
```json
{
  "success": true,
  "graph": {
    "nodes": [...],
    "edges": [...]
  }
}
```

> La estructura exacta de `graph` depende del estado de LightRAG. Puede variar según documentos procesados.

---

### 🟢 `GET /validation-stats`

Retorna estadísticas del pipeline de validación y del optimizador de tokens. Útil para un panel de monitoreo en el frontend.

**Response `200 OK`:**
```json
{
  "success": true,
  "optimizer": {
    "total_queries": 42,
    "cache_hits": 8,
    "cache_hit_rate": 0.19,
    "total_tokens_estimated": 87400
  },
  "rag_engine": {
    "total_documents": 15,
    "total_chunks": 320
  },
  "validation_config": {
    "hallucination_threshold": 0.7,
    "cross_check_threshold": 0.55,
    "min_confidence_score": 0.3,
    "self_correction_retries": 2
  }
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `optimizer.cache_hit_rate` | `float` [0–1] | Porcentaje de consultas respondidas desde caché |
| `validation_config` | `object` | Umbrales actuales del pipeline de validación |

---

### 🔵 `POST /generate-pdf-report`

Genera un reporte PDF de una respuesta legal y lo devuelve como descarga directa.

**Request body:**
```json
{
  "query": "¿Cómo denuncio violencia familiar?",
  "response": {
    "tema": "violencia_familiar",
    "respuesta_espanol": "Para denunciar...",
    "respuesta_quechua": "...",
    "pasos_recomendados": [],
    "recursos": [],
    "advertencias": [],
    "fuentes": [],
    "confianza": 0.85,
    "fecha_respuesta": "2026-02-22T15:00:00"
  }
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `query` | `string` (min 1 char) | ✅ | Consulta original del usuario |
| `response` | `object` | ✅ | Objeto `response` obtenido de `/legal-query` |

**Response `200 OK`:**
- **Content-Type:** `application/pdf`
- **Content-Disposition:** `attachment; filename="reporte_legal.pdf"`
- Body: bytes del archivo PDF

**Errores:**

| Código | Situación |
|---|---|
| `200` (con `success: false`) | `reportlab` no instalado en el servidor |
| `500` | Error generando el PDF |

**Ejemplo de descarga en el frontend:**
```javascript
const res = await fetch('http://localhost:8000/generate-pdf-report', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query, response: legalQueryResponse.response })
});

if (res.ok && res.headers.get('content-type') === 'application/pdf') {
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'reporte_legal.pdf';
  a.click();
}
```

---

## Endpoints de administración (requieren `X-API-Key`)

### 🔴 `POST /upload-pdf`

Sube un archivo PDF, lo procesa con Docling y lo indexa en el motor RAG.

**Request:** `multipart/form-data`

| Campo del formulario | Tipo | Requerido | Descripción |
|---|---|---|---|
| `file` | `File` (.pdf) | ✅ | Archivo PDF a procesar |

**Headers adicionales:**
```
X-API-Key: <SECRET_KEY>
Content-Type: multipart/form-data
```

**Response `200 OK`:**
```json
{
  "success": true,
  "filename": "ley_30364.pdf",
  "processed_path": "/app/docs/processed/ley_30364.pdf.md",
  "message": "PDF procesado correctamente con Docling"
}
```

**Errores:**

| Código | Situación |
|---|---|
| `400` | El archivo no tiene extensión `.pdf` |
| `403` | API Key inválida o ausente (en producción) |
| `500` | Error durante el procesamiento con Docling |

---

### 🔴 `POST /batch-process`

Procesa todos los archivos PDF que estén en el directorio `docs/raw_pdfs/` del servidor que aún no hayan sido procesados.

**Headers requeridos:** `X-API-Key: <SECRET_KEY>`

**Response `200 OK`:**
```json
{
  "success": true,
  "processed": 5,
  "failed": 1,
  "details": [
    { "filename": "ley_30364.pdf", "status": "ok" },
    { "filename": "codigo_civil.pdf", "status": "failed", "error": "..." }
  ]
}
```

---

### 🔴 `POST /evaluate-system`

Ejecuta la suite de evaluación completa con DeepEval sobre el sistema RAG + LLM.

**Headers requeridos:** `X-API-Key: <SECRET_KEY>`

**Response `200 OK`:**
```json
{
  "success": true,
  "results": {
    "faithfulness": 0.91,
    "answer_relevancy": 0.87,
    "contextual_precision": 0.83
  }
}
```

> Requiere que `DEEPEVAL_API_KEY` esté configurada. Si la suite no fue inicializada, retornará `500`.

---

## Tipos enumerados de referencia

### `UrgencyLevel` (urgencia)

| Valor | Descripción |
|---|---|
| `"bajo"` | Sin urgencia inmediata |
| `"medio"` | Requiere atención en días |
| `"alto"` | Requiere atención urgente |
| `"critico"` | Emergencia, actuar de inmediato |

### `LegalTopic` (tema)

| Valor | Descripción |
|---|---|
| `"violencia_familiar"` | Violencia familiar / doméstica |
| `"pension_alimentos"` | Pensión de alimentos |
| `"medidas_proteccion"` | Medidas de protección |
| `"regimen_visitas"` | Régimen de visitas |
| `"denuncias_procesos"` | Denuncias y procesos generales |

### `ValidationStatus` (estado de validación)

| Valor | Descripción | Acción recomendada en UI |
|---|---|---|
| `"passed"` | Sin problemas detectados | Mostrar respuesta normalmente |
| `"warned"` | Advertencias, respuesta válida | Mostrar disclaimer leve |
| `"corrected"` | Se aplicó auto-corrección | Indicar revisión automática |
| `"failed"` | No superó umbral mínimo | Advertir y sugerir asesoría profesional |

### `ConfidenceLevel` (nivel de confianza)

| Valor | Score numérico | Descripción |
|---|---|---|
| `"high"` | ≥ 0.80 | Alta confianza, respuesta bien respaldada |
| `"medium"` | ≥ 0.55 | Confianza media, usar con precaución |
| `"low"` | < 0.55 | Baja confianza, mostrar advertencia prominente |

---

## Flujo recomendado para el chat del frontend

```
Usuario escribe consulta
        │
        ▼
[Opcional] GET /health  ──── sistema degradado? ──── Mostrar banner de advertencia
        │
        ▼
POST /legal-query-stream          ← Para respuesta inmediata (streaming)
  ├── Eventos `chunk` → Mostrar texto a medida que llega
  └── Evento `final`  → Obtener validation + sources + metadata
          │
          ├── validation.status === "failed"  → Advertencia prominente
          ├── validation.confidence === "low" → Disclaimer
          ├── sources[]                        → Lista de fuentes citadas
          └── response.pasos_recomendados[]   → Renderizar como lista numerada
                    │
                    ▼
        [Botón] POST /generate-pdf-report  ← Descarga del resumen en PDF
```

---

## Variables de entorno requeridas en el backend

| Variable | Descripción |
|---|---|
| `COHERE_API_KEY` | API Key de Cohere (obligatoria) |
| `SECRET_KEY` | Clave para endpoints de administración |
| `ENVIRONMENT` | `development` o `production` |
| `CORS_ORIGINS` | Lista de orígenes permitidos (JSON array) |
| `RATE_LIMIT_ENABLED` | `true` / `false` |
| `CACHE_TTL` | TTL del caché semántico en segundos (default: 3600) |

---

*Última actualización: 2026-02-25 — IA Jurídica v2.1*
