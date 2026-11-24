# IA Jurídica

IA Jurídica es un asistente experimental de orientación legal en español y
quechua. En la rama `v8`, busca fuentes en un corpus normativo versionado
con **SAT-Graph**, genera respuestas con **Cohere** y presenta las citas
recuperadas. El corpus y las conversaciones se guardan en **SurrealDB**.
**Redis** apoya la caché y los límites de solicitudes.

## Arranque local

Instala Python y Node según [.python-version](.python-version) y
[.node-version](.node-version), además de uv, la versión de pnpm que fija el
[manifiesto raíz](package.json) y Docker Compose.

```bash
uv sync --frozen --extra dev --inexact
pnpm install --frozen-lockfile
pnpm --dir frontend install --frozen-lockfile
```

Copia [backend/.env.example](backend/.env.example) a `backend/.env` si todavía
no tienes ese archivo. Configura `COHERE_API_KEY` y los secretos locales.
Completa las credenciales de Google si vas a probar el inicio de sesión.
[Configuración de OAuth](OAUTH_SETUP.md).

```bash
pnpm dev:full
```

El comando levanta SurrealDB y Redis, importa
`backend/docs/sat_graph.surql.gz` si la base está vacía y espera a que
FastAPI responda a `/ready` antes de iniciar Next.js. Los arranques
posteriores usan el corpus del volumen persistente.

PostgreSQL no arranca por defecto. Para acceder a datos antiguos solo cuando
sea necesario, usa `docker compose --profile legacy-postgres up -d postgres`.

| Servicio | Dirección local |
| --- | --- |
| Interfaz Next.js | [localhost:3000](http://localhost:3000) |
| API FastAPI | [localhost:8000](http://localhost:8000) |
| Estado del corpus | [localhost:8000/ready](http://localhost:8000/ready) |
| SurrealDB | `ws://127.0.0.1:8010/rpc` |

## Recuperación y datos

| Componente | Función |
| --- | --- |
| SAT-Graph | Recupera normas, artículos y referencias desde el corpus de SurrealDB. Es el motor que arranca con `RAG_ENGINE=sat`. |
| Cohere y validación | Generan la respuesta a partir del contexto recuperado y aplican los controles de la aplicación. El flujo puede abstenerse si falta evidencia. |
| Next.js y FastAPI | Gestionan las consultas, las sesiones anónimas, el acceso con Google y las conversaciones. La API ofrece respuestas JSON y streaming NDJSON. |
| SurrealDB y Redis | SurrealDB conserva el corpus y los datos de la aplicación. Redis apoya la caché y el control de solicitudes. |

El editor del corpus se abre con `pnpm sat:review`. La ingestión administrativa
registra el documento y su evidencia antes de la revisión editorial.
[Corpus e ingesta](KNOWLEDGE_GRAPH_SETUP.md) · [Editor de SAT-Graph](docs/SAT_CORPUS_EDITOR.md).

La interfaz ofrece dictado en español, lectura en español mediante el
navegador y síntesis de voz en quechua desde el backend para usuarios autenticados.

La orientación es informativa. Para usar una cita en un trámite o proceso,
consulta la fuente oficial y verifica su vigencia.

## Pruebas y despliegue

| Objetivo | Comando o guía |
| --- | --- |
| Pruebas offline de Python, Node y React | `pnpm test` |
| Evaluación offline del pipeline | `pnpm test:harness` |
| Playwright con API simulada | `pnpm test:e2e` |
| Evaluación con proveedores reales | [Guía de pruebas](tests/README.md) |
| Frontend en Vercel y backend en Azure | [Guía de despliegue](deploy/azure/README.md) |
| Rutas y permisos | [API](API_DOC.md) |
| Validación de respuestas | [Pipeline de validación](backend/VALIDATION_GUIDE.md) |

GitHub Actions ejecuta las pruebas al abrir o actualizar un pull request y en
los pushes a `main` y `v8`. El despliegue del backend usa el runner de Azure,
mientras que Vercel publica el frontend. [CI](.github/workflows/ci.yml) ·
[Despliegue de Azure](.github/workflows/deploy-azure.yml).
