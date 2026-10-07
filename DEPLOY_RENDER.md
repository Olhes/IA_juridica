# Despliegue en Render — checklist de v8

Actualización: **2026-10-06**. Esta guía describe configuración del repositorio,
no certifica preparación para producción ni promete RAM, precios o cuotas de un
proveedor. Antes de contratar, verifica los límites vigentes de tu plan.

## Antes de publicar

1. Ejecuta `pnpm test:coverage`, `pnpm deps:check` y build frontend.
2. Revisa [seguridad](docs/SECURITY.md), [OAuth](OAUTH_SETUP.md) y auditoría vigente.
   El módulo OAuth heredado contiene limitaciones pendientes; no lo expongas
   confiando únicamente en esta plantilla.
3. Provisiona PostgreSQL y Redis privados, con autenticación, backups y persistencia.
   No uses Compose de desarrollo (`trust`, claves de prueba) en producción.
4. Define corpus, volumen y estado de readiness: levantar HTTP no carga por sí
   solo documentos ni convierte el grafo en una fuente jurídica verificada.

## Backend Docker

- Repositorio/rama: selecciona **v8** o un commit revisado; no supongas `main`.
- Contexto de build: raíz del repositorio.
- Dockerfile: `backend/Dockerfile.production`.
- Puerto: `PORT` del servicio; la imagen admite `WORKERS` (por defecto 1).
- En el contenedor Uvicorn escucha en `0.0.0.0`; limita exposición con el proveedor,
  proxy, red y firewall. El bind del contenedor no es una protección de seguridad.
- Health de proceso: `/health` puede devolver 200 con `status=degraded`.
  Para tráfico que requiera corpus listo usa `/ready` (503 hasta ready).

La imagen incluye dependencias ML/Docling; mide tiempo de build, memoria máxima,
concurrencia y almacenamiento con tu corpus. No se garantiza ejecución en un
plan pequeño ni OCR sin instalar/configurar sus dependencias y pesos.

## Entorno de producción

Parte de [env.production.example](env.production.example), reemplaza placeholders
y entrega secretos mediante configuración del servicio, nunca en Git.

| Variable | Condición |
|---|---|
| `ENVIRONMENT=production`, `DEBUG=false` | Activan validación de producción |
| `COHERE_API_KEY` | Proveedor de generación/embeddings/reranking configurado |
| `SECRET_KEY`, `ANONYMOUS_SESSION_SECRET` | Aleatorios, independientes; anónimo ≥32 bytes |
| `DATABASE_URL` / credenciales `DATABASE_*` | PostgreSQL real accesible desde el backend |
| `REDIS_URL`, `REDIS_HOST`, `REDIS_PORT` | Configura coherentemente según consumidores |
| `RATE_LIMIT_STORAGE_URI` | Redis compartido entre workers, no `memory://` |
| `CORS_ORIGINS` | JSON con orígenes HTTPS explícitos, no wildcard |
| `ANONYMOUS_SESSION_COOKIE_SAMESITE` | `lax` mismo sitio; `none` requiere Secure/HTTPS y comprobar políticas del navegador |
| `ADMIN_ENDPOINTS_ENABLED` | `false` por defecto; si se activa, clave independiente obligatoria |
| `API_DOCS_ENABLED=false` | Desactiva Swagger/OpenAPI públicos |
| `LOAD_LOCAL_KG`, `NEO4J_ENABLED` | Opt-in; no aseguran que el corpus exista ni esté listo |

La API usa rutas documentales ancladas a `backend/docs` en `main.py`; no basta
cambiar `DOCS_ROOT_DIR` para redirigir todas las operaciones. Prepara almacenamiento
persistente/evidencias y permisos, y prueba restauración. No borres corpus para
arreglar un boot. Consulta [grafo](KNOWLEDGE_GRAPH_SETUP.md).

## Frontend

Configura `NEXT_PUBLIC_API_URL=https://<tu-backend>` **antes del build**.
Desde raíz: `pnpm --dir frontend install --frozen-lockfile` y `pnpm frontend:build`.
Para servicio Node: `pnpm frontend:start` (ajusta puerto mediante el entorno del proveedor).
La URL del backend debe permitir cookies/CORS del origen frontend. Valida login,
bootstrap anónimo, persistencia, cancelación y PDF desde el dominio real.
La pantalla heredada `LoginPage` tiene URL local fija y exige corrección antes de
usarla en producción; no confundas configuración del chat con todos los flujos OAuth.

## Comprobación y rollback

- `/ready` 200, `/health` con componentes esperados y versión configurada.
- Una conversación de A no puede leerse/modificarse desde B.
- Clave admin ausente/incorrecta devuelve 403; endpoints deshabilitados por defecto.
- Respuesta NDJSON validada, abstención sin evidencia y errores sanitizados.
- Rutas PDF/Markdown/evidencia sobreviven reinicio y restauración.
- Mantén el commit previo y backup de datos; rollback de imagen no revierte schemas
  ni recupera un volumen borrado. Las consultas de aceptación reales pueden facturar.
