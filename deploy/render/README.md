# Guía de despliegue en Render (solo backend — plan gratuito)

Este repositorio incluye un Blueprint de Render (`render.yaml`) y una imagen Docker dedicada (`deploy/render/Dockerfile`) para desplegar el backend FastAPI en el plan gratuito de Render sin requerir una base de datos de pago.

## Arquitectura en el plan gratuito de Render

1. **`ia-juridica-backend`** (`type: web`, `runtime: docker`, `plan: free`)
   - Ejecuta FastAPI (`uvicorn`, 1 worker) en el puerto `PORT` inyectado por Render.
   - Incluye el binario oficial `surrealdb/surrealdb:v4.0.1` enlazado únicamente a loopback (`127.0.0.1:8010`) cuando `EMBEDDED_SURREAL=true` (valor por defecto).
   - Precarga el corpus jurídico versionado SAT (`backend/docs/sat_graph.surql.gz`) en RocksDB durante `docker build` para que los arranques en frío sean rápidos y no tengan que reproducir más de 100 000 aristas con 0.1 vCPU.
   - Health check: `GET /ready` (verifica que el corpus SAT esté cargado).
2. **`ia-juridica-cache`** (`type: keyvalue`, `plan: free`, `ipAllowList: []`)
   - Instancia privada compatible con Redis/Valkey, conectada automáticamente a `REDIS_URL` y `RATE_LIMIT_STORAGE_URI` para cumplir con la validación estricta de rate limiting en producción.

## Despliegue paso a paso

1. En el panel de Render, selecciona **New + -> Blueprint** y conecta este repositorio.
2. Render detectará `render.yaml` y solicitará las variables marcadas con `sync: false`:
   - **`COHERE_API_KEY`** (obligatoria): tu clave de API de Cohere.
   - **`VOYAGE_API_KEY`** (opcional): activa la recuperación híbrida con Voyage dense (`voyage-context-4`) y rerank (`rerank-3-lite`); si se deja vacía, SAT utiliza automáticamente BM25 con encabezados estructurales.
   - **`CORS_ORIGINS`** ya viene preconfigurado en `render.yaml` con `["https://ia-juridica-pe.vercel.app"]` (sin barra final, tal como envían el header `Origin` los navegadores).
3. Haz clic en **Apply** y espera a que finalice la construcción de la imagen Docker y la comprobación `/ready`.

## Conexión con el frontend (`https://ia-juridica-pe.vercel.app`)

### Opción A — Recomendada: proxy first-party con Next.js (Vercel)
`frontend/next.config.mjs` ya reescribe `/api/*` hacia `BACKEND_URL` para que las cookies de sesión permanezcan como first-party:
- En Vercel (frontend `ia-juridica-pe.vercel.app`):
  - `NEXT_PUBLIC_API_URL=/api`
  - `BACKEND_URL=https://<tu-servicio-render>.onrender.com`
- En Render (backend):
  - `CORS_ORIGINS=["https://ia-juridica-pe.vercel.app"]` (ya preconfigurado)
  - `ANONYMOUS_SESSION_COOKIE_SAMESITE=lax` (ya preconfigurado)

### Opción B — Llamadas directas del navegador hacia Render
Si el frontend consulta Render directamente sin pasar por un proxy:
- En Vercel (frontend): `NEXT_PUBLIC_API_URL=https://<tu-servicio-render>.onrender.com`
- En Render (backend):
  - `CORS_ORIGINS=["https://ia-juridica-pe.vercel.app"]` (ya preconfigurado)
  - `ANONYMOUS_SESSION_COOKIE_SAMESITE=none` (`ANONYMOUS_SESSION_COOKIE_SECURE` ya está configurado en `true`)
- Nota: las cookies de inicio de sesión JWT del backend usan `SameSite=Lax`, por lo que si utilizas autenticación de usuarios con cookies conviene usar la **Opción A** (proxy `/api/*` first-party).

## Limitaciones del plan gratuito y migración opcional a base persistente

- **Suspensión por inactividad:** los servicios web gratuitos de Render entran en reposo tras ~15 minutos sin tráfico; la primera solicitud posterior tarda entre 30 y 60 segundos en despertar el contenedor.
- **Límite de 512 MB de RAM:** mantén `WORKERS=1`, `SURREAL_POOL_SIZE=2`, `LOAD_LOCAL_KG=false` y `RAG_ENGINE=sat`.
- **Disco efímero (modo embebido):** con `EMBEDDED_SURREAL=true`, el corpus normativo SAT siempre se restaura íntegro desde la imagen precargada, mientras que las cuentas de usuario, el historial de conversaciones y la caché de embeddings de Voyage se reinician cuando el contenedor se reinicia o se redespliega.
- **Actualización gratuita con persistencia (SurrealDB Cloud Free Tier):** para conservar usuarios y conversaciones entre reinicios y liberar ~150 MB de RAM dentro de Render, crea una instancia gratuita en SurrealDB Cloud y configura estas variables en Render (sin cambios de código):
  - `EMBEDDED_SURREAL=false`
  - `SURREAL_URL=wss://<tu-instancia>.surreal.cloud/rpc`
  - `SURREAL_USER=<usuario-cloud>`
  - `SURREAL_PASSWORD=<clave-cloud>`
  - `AUTO_BOOTSTRAP_SAT=true` (carga `sat_graph.surql.gz` una sola vez de forma idempotente)
