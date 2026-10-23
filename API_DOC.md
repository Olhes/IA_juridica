# API de IA Jurídica — rama v8

Actualización: **2026-10-06**. Referencia de los contratos implementados; no una
release. `APP_VERSION` configura la identidad de raíz, `/health` y OpenAPI.
En desarrollo consulta `/docs` y `/openapi.json` para esquemas completos.
La documentación interactiva está deshabilitada por defecto en producción.

## Acceso y estado

| Ruta | Acceso | Propósito |
|---|---|---|
| `GET /` | Público | Identidad configurada de la API |
| `GET /health` | Público | Componentes y `healthy`/`degraded`; HTTP 200 no implica corpus listo |
| `GET /ready` | Público | 200 solo con corpus `ready`; 503 en otro estado |
| `POST /session/bootstrap` | Público, limitado por IP | Cookie de principal anónimo firmada; `principal_id`, `expires_at` |
| `POST /legal-query` | Principal anónimo | Respuesta JSON validada |
| `POST /legal-query-stream` | Principal anónimo | Respuesta final transportada por NDJSON |
| `POST /telemetry/stream` | Público, limitado por IP | Telemetría numérica del cliente (sin texto); 204 |
| `GET /telemetry/stream/summary` | Admin | p50/p95 por etapa, resultados y líneas inválidas |
| `POST /feedback` | Principal anónimo, limitado | 👍/👎 con motivo; el texto solo con `share_text` y 👎 |
| `GET /feedback/queue`, `POST /feedback/queue/{item_id}/decision` | Admin (clave o rol `admin`) | Cola de candidatos al gold: aceptar o descartar |
| `GET /quality/published` | Público | Métricas publicadas (agregados, sin texto de consultas) |
| `GET /quality/admin/overview` | Admin (clave o rol `admin`) | Regresiones entre commits, colas de revisión, feedback y latencia |
| `POST /generate-pdf-report` | Principal anónimo | PDF de consulta/respuesta suministradas por cliente |
| `/chat/*` | Principal anónimo, excepto health | Conversaciones, mensajes y caché del propietario |
| `POST /upload-pdf`, `POST /batch-process` | Admin | Ingesta documental |
| `GET /documents`, `GET /knowledge-graph`, `GET /validation-stats` | Admin | Inspección de corpus/validación |
| `POST /evaluate-system` | Admin | Evaluación del sistema; puede consumir proveedores |

Las operaciones admin requieren **ambos** `ADMIN_ENDPOINTS_ENABLED=true` y
`X-API-Key: <ADMIN_API_KEY>`. No uses `SECRET_KEY` ni hay bypass de desarrollo.
Admin deshabilitado o clave incorrecta devuelve 403. No expongas la clave en frontend.

## Sesión y consulta mínima

```javascript
const base = 'http://localhost:8000';
await fetch(`${base}/session/bootstrap`, { method: 'POST', credentials: 'include' });
const result = await fetch(`${base}/legal-query`, {
  method: 'POST', credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: 'Consulta sintética de prueba', language: 'spanish' }),
});
if (!result.ok) throw new Error(`HTTP ${result.status}`);
const data = await result.json();
```

`query` debe ser no vacío tras trim, máximo **8000 caracteres**; idiomas admitidos
`spanish` y `quechua`. `conversation_id` es opcional y debe pertenecer al principal.
`context` es un objeto tipado, no un prompt arbitrario; consulta el esquema de
`RequestContext`. Campos desconocidos se rechazan con 422. El servidor acota
historial/contexto antes de construir el prompt; presupuesto excedido devuelve 422.

Respuesta común: `success`, `query`, `language`, `cached`, `response`, `sources`,
`validation`, `metadata`. En `metadata` se informa `pipeline=validated-before-delivery-v1`,
estado de evidencia y traducción. `response` puede ser texto u objeto estructurado;
no asumas siempre una única clave. Traducción quechua incompleta/no disponible
conserva texto y advertencias. `validation.is_reliable` no certifica verdad jurídica.
Sin documentos recuperados: abstención, sin fuentes y sin fiabilidad positiva.

`metadata` también incluye, para que la interfaz explique la respuesta sin inventar nada:

| Campo | Contenido |
|---|---|
| `evidence_status` | `retrieved` o `insufficient_evidence` (abstención) |
| `citations` | `[{key, text, status, source, excerpt}]`: cada norma citada (Ley, artículo, Casación, D.S.) y si aparece (`verified`) o no (`unverified`) en las fuentes recuperadas; `excerpt` es texto del corpus, nunca del modelo |
| `evidence` | `[{source, relevance, excerpt}]`: fuentes recuperadas con un extracto de hasta 240 caracteres |
| `timings` | `total_ms`, `stages` y `cache_hit` (ver NDJSON) |
| `translation` | Solo con `language=quechua`: `success`, `complete`, `warning`, `review_required` (siempre `true`), `fallback_to_spanish`, `quality` (`alta` \| `media` \| `baja`), `reasons` y `basis` |

El aviso de revisión de la traducción **no** va pegado al texto: vive solo en `metadata.translation.warning`.
Con `fallback_to_spanish=true` la respuesta conserva el español. `quality` es una estimación automática sin
referencia (idioma del resultado, texto sin traducir, referencias legales conservadas y longitud); `alta` no
significa que un hablante nativo la haya revisado.

Que una cita sea `verified` solo significa que aparece en el texto recuperado: no acredita
vigencia ni que la norma diga lo que la respuesta le atribuye.

## NDJSON v1: etapas en vivo, texto solo validado

`POST /legal-query-stream` acepta el mismo payload. La autorización (401) y la
conversación ajena o inexistente (404) se resuelven **antes** de abrir el stream;
el resto del pipeline corre mientras el stream ya está abierto. Cada línea es un
evento `{v, seq, request_id, type, ...}` (`v` = 1, `seq` consecutivo desde 0,
`request_id` = cabecera `X-Request-ID`):

```json
{"v":1,"seq":0,"request_id":"3f1c…","type":"meta","data":{"language":"spanish"}}
{"v":1,"seq":1,"request_id":"3f1c…","type":"stage","stage":"retrieval","status":"start"}
{"v":1,"seq":2,"request_id":"3f1c…","type":"stage","stage":"retrieval","status":"end","elapsed_ms":412.5}
{"v":1,"seq":7,"request_id":"3f1c…","type":"chunk","delta":"Contenido final validado"}
{"v":1,"seq":8,"request_id":"3f1c…","type":"final","data":{"success":true,"metadata":{"timings":{"total_ms":2310.4,"stages":{"retrieval":412.5},"cache_hit":false}}}}
{"v":1,"seq":9,"request_id":"3f1c…","type":"done"}
```

Etapas (`stage`): `translate_in`, `retrieval`, `generation`, `validation` y
`translate_out`; solo aparecen las que se ejecutan. El texto (`chunk`) se envía
únicamente cuando ya está validado: nunca hay borradores. Un fallo posterior a
la apertura emite un único `error` y luego `done`, sin `final`:

```json
{"v":1,"seq":3,"request_id":"3f1c…","type":"error","code":"RETRIEVAL_UNAVAILABLE","message":"Legal retrieval unavailable","retryable":true}
```

`code` es uno de `RETRIEVAL_UNAVAILABLE`, `GENERATION_UNAVAILABLE`,
`TRANSLATION_UNAVAILABLE`, `TIMEOUT` (`STREAM_PIPELINE_TIMEOUT_SECONDS`, 120 s por
defecto) o `INTERNAL_ERROR` (no reintentable). El mensaje es fijo: nunca repite
la consulta ni el texto de una excepción. `final.data.metadata.timings` lleva
`total_ms`, `stages` (milisegundos por etapa) y `cache_hit`; los tiempos no se
guardan en la caché de respuestas.

`StreamGuard` verifica todo lo que sale: esquema, `seq` consecutivo, un único terminal seguido de un único
`done`, y que el `chunk` coincida con el texto del `final`. Si el origen se queda mudo más de
`STREAM_IDLE_TIMEOUT_SECONDS` (135 s por defecto) emite `error` `TIMEOUT`; ante cualquier violación el
cliente recibe `INTERNAL_ERROR` en lugar de datos dudosos y se registra solo el tipo de violación.

El cliente debe tolerar BOM, CRLF y líneas partidas, descartar o reparar líneas inválidas contándolas,
deduplicar por `seq` y, si falta el `final`, usar el `chunk` avisando de que la respuesta es parcial
(`frontend/src/application/legal/stream/ndjsonParser.ts`). Al terminar envía, con `navigator.sendBeacon`, una
telemetría de **solo números** y el `request_id` a `POST /telemetry/stream` (cuerpo JSON de hasta 4 KB, sin
campos extra; límite `TELEMETRY_RATE_LIMIT`, 120/minuto): resultado, `ttfb_ms`, `total_ms`, `stage_ms` y
contadores de líneas válidas/inválidas/reparadas/duplicadas. Nunca texto de consultas ni de respuestas.
`GET /telemetry/stream/summary` (admin) agrega los últimos 2000 streams en memoria.

El contrato se define en `backend/models/stream_events.py` y se exporta a
`backend/contracts/stream_event.v1.schema.json` y a
`frontend/src/domain/legal/streamEvents.generated.ts`. Se envían
`Content-Type: application/x-ndjson`, `Cache-Control: no-cache, no-transform`
y `X-Accel-Buffering: no`. El cliente debe gestionar líneas partidas entre lecturas,
UTF-8 incremental, cancelación y errores HTTP antes del primer evento.

## Feedback y calidad

`POST /feedback` recibe `{request_id, rating: up|down, reason?, comment?, conversation_id?, language,
evidence_status?, translation_quality?, share_text}`. Un 👎 exige `reason` (`incorrecta`, `incompleta`, `sin_fuentes`,
`mala_traduccion`, `confusa`, `otro`) y un 👍 no lleva motivo. Se guardan solo etiquetas, números y un hash del
propietario; la consulta y la respuesta se guardan **únicamente** con 👎 y `share_text=true` (el servidor las lee de una
conversación del propio propietario) y entran a la cola de candidatos, pendiente de revisión humana. Un candidato
aceptado no se agrega al gold: se exporta como esqueleto para que abogados redacten los hechos y citas. Un voto por
persona y petición (el último prevalece). Límite `FEEDBACK_RATE_LIMIT` (30/hora). `FEEDBACK_DIR` define dónde se guarda.

`GET /quality/published` devuelve `docs/quality/published.json`: solo se publica lo medido con un sistema real; las
líneas base sintéticas figuran como «no medido». Las vistas de administración aceptan `X-API-Key` o una sesión de
persona con el rol `admin` (la clave nunca va al navegador). Límite `QUALITY_RATE_LIMIT` (60/minuto).

## Chat persistente

Rutas principales: `POST/GET /chat/conversations`,
`GET/PUT/DELETE /chat/conversations/{conversation_id}` y `POST /chat/message`.
El GET de conversación incluye el historial; no hay un endpoint independiente
de mensajes por conversación.
Consulta OpenAPI para continuación, stats, invalidación y health.
El cliente no elige `user_id`: la identidad se obtiene de la cookie firmada.
Acceder a una conversación ajena devuelve 404 sin revelar su existencia.
PostgreSQL no disponible devuelve 503; no se fabrican mensajes/conversaciones.

## PDF e ingesta

`POST /generate-pdf-report`: JSON con `query` y `response` (objeto). Devuelve
`application/pdf`, adjunto `reporte_legal.pdf`, `Cache-Control: no-store`.
Renderiza el contenido proporcionado, **no vuelve a validar ni autentica sus fuentes**.
500: `PDF generation failed`; 503: `PDF generation unavailable`.

`POST /upload-pdf`: multipart, campo `file`, extensión `.pdf`, MIME
`application/pdf`, firma `%PDF-`, archivo no vacío, máximo `MAX_FILE_SIZE`
(50 MiB por defecto). Nombre del servidor UUID, no ruta elegida por el cliente.
Errores: 400 formato/firma, 413 tamaño, 500 procesamiento.
Retorna `filename`, `original_filename`, `evidence_id`,
`graph_write_state=unverified`. Se preserva evidencia de bytes y Markdown con
SHA-256 antes de la escritura RAG; ese estado no confirma procedencia ni autoridad legal.
`/batch-process` recorre los PDFs locales pendientes, no una cola cloud.

## Errores y límites

| Código | Interpretación |
|---|---|
| 401 | Cookie de principal ausente, inválida o expirada |
| 403 | Administración deshabilitada / clave incorrecta |
| 404 | Conversación inexistente o ajena |
| 422 | Payload, idioma o presupuesto de contexto inválido |
| 429 | Límite de uso excedido |
| 502 | Generación sin respuesta utilizable |
| 503 | Corpus, retrieval, traducción de consulta o persistencia no disponibles |
| 500 | Error interno; detalles sanitizados |

Límites configurables por ruta, no un único límite global de 100/15 minutos:
`LLM_RATE_LIMIT=10/minute`, `CONVERSATION_CREATE_RATE_LIMIT=20/hour`,
`ADMIN_RATE_LIMIT=5/hour`, `SESSION_BOOTSTRAP_RATE_LIMIT=20/hour`.
En producción, `RATE_LIMIT_STORAGE_URI` debe ser compartido entre workers.

## OAuth es otro contrato

`/auth/google`, `/auth/google/callback`, `/auth/login`, `/auth/refresh`, `/auth/me`
y `/auth/logout` corresponden al módulo de cuentas heredado. No equivalen al
principal anónimo del chat ni realizan migración automática de historial.
Consulta [OAuth y limitaciones](OAUTH_SETUP.md) antes de exponerlo públicamente.
Pruebas y evaluación: [guía única](tests/README.md).
