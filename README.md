# IA Jurídica

Asistente experimental de orientación legal bilingüe español/quechua, con
recuperación documental, validación de respuestas, conversaciones persistentes
y autenticación Google OAuth 2.0.
No sustituye la revisión de un profesional ni certifica la vigencia de una norma.

**Estado documentado: rama `v8` · Actualización: 2026-10-18.**
`v8` identifica la rama de trabajo, no una release semántica. No hay tags de
release en el historial consultado. Los manifiestos conservan `1.0.0` (Node)
y `0.1.0` (Python); la API usa `APP_VERSION=v8` por defecto, configurable por entorno.

## Empezar en local

Necesitas Python **3.12–3.13** (`.python-version`: 3.12.10), UV, Node **24**,
pnpm **10.30.2** y Docker Compose o el equivalente de Podman para los servicios.
Los locks, no este documento, son la fuente de versiones reproducibles.

```powershell
# Desde la raíz; instalar backend y ambos paquetes Node
uv sync --frozen --extra dev --inexact
pnpm install --frozen-lockfile
pnpm --dir frontend install --frozen-lockfile

# Crear solo si aún no existen: no sobrescribir secretos/configuración
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
if (-not (Test-Path frontend/.env.local)) {
  Set-Content frontend/.env.local 'NEXT_PUBLIC_API_URL=http://localhost:8000'
}
```

Completa `backend/.env`: `COHERE_API_KEY`, secretos propios y conexión PostgreSQL.
El ejemplo es para desarrollo. Para cargar un corpus local existente activa
`LOAD_LOCAL_KG=true`; el checkout no garantiza un número fijo de documentos.
Si el corpus no está listo, `/ready` responde 503 y el launcher no anuncia éxito.

```powershell
pnpm dev:full
```

El launcher usa **Docker**, levanta PostgreSQL/Redis, espera su salud, inicia el
backend y comprueba `/ready` antes del frontend. Qdrant no es obligatorio para ese
arranque. Si usas Podman, arranca los servicios mediante tu proveedor Compose y
ejecuta backend/frontend por separado; no hay detección automática de Podman:

```powershell
docker compose up -d postgres redis
pnpm backend:dev:safe
# En otra terminal
pnpm frontend:dev
```

Interfaz: `http://localhost:3000`. API: `http://localhost:8000`.
Swagger/OpenAPI se habilitan por defecto en desarrollo, no en producción.
No ejecutes comandos que eliminen volúmenes para solucionar un arranque sin backup.

## Arquitectura que está activa

```text
Next App Router → ChatPage → useChat / useChatSessions / apiService
                 → Google OAuth 2.0 (autenticación opcional)
                 → FastAPI (cookies, propietario, límites)
                 → recuperación LightRAG + reranking
                 → generación Cohere → validación/corrección → traducción
                 → contenido final validado (JSON o NDJSON) → PostgreSQL
```


| Capa                 | Ubicación / contrato                                                                              |
| ---------------------- | ---------------------------------------------------------------------------------------------------- |
| Interfaz             | `frontend/app/`, `frontend/src/presentation/`; Next 16.3.8, React 19.3.0                           |
| Aplicación frontend | `frontend/src/application/legal/`; peticiones directas a `NEXT_PUBLIC_API_URL`, con cookies        |
| API                  | `backend/main.py`, `backend/modules/chat/routes/`, `backend/modules/auth/routes/`                  |
| Pipeline común      | `backend/services/legal_queries.py`; `/legal-query`, stream y chat comparten respuesta validada    |
| RAG e ingesta        | `backend/modules/rag/services/`, `backend/ingestion/`, `backend/context/`                          |
| Validación          | `backend/modules/validation/`; comprobaciones heurísticas, no verificación jurídica automática |
| Persistencia         | PostgreSQL para chat; Redis para caché/sesiones auxiliares y límites compartidos                 |
| Tests                | Solo `tests/<backend                                                                               |

El NDJSON transporta contenido **después** de la validación; no publica borradores
provisionales del modelo. Sin documentos recuperados se devuelve abstención explícita.
La caché de respuestas es exacta, con SHA-256 sobre consulta, idioma, propietario,
historial/contexto, conversación y revisión del corpus; no es una caché semántica.
`LegalAssistantPage`, `useBackendChat` y `usePersistentChat` son alternativas
heredadas, no el flujo de inicio actual.

## Pruebas y cobertura

```powershell
pnpm test                 # Python + Node + React, offline
pnpm test:coverage        # Mismo alcance + XML Python y LCOV frontend
pnpm deps:check           # Locks y requirements exportados
```

La [guía única de tests](tests/README.md) contiene comandos por componente,
catálogo por caso, E2E y limitaciones. Las pruebas de navegador son separadas:
`pnpm test:e2e` usa API simulada, no acredita integración real con modelos.

**Evaluaciones facturables requieren opt-in:**
`pnpm test:quality --run-model-evals` o `pnpm test:all --run-model-evals`.
No confundas pruebas unitarias de chunking con calidad RAG: RAGAS complementa
esas pruebas con evaluación del retrieval sobre un dataset de referencia.
Los casos reales actuales del generador utilizan DeepEval; no son un benchmark
comparativo RAGAS de estrategias de chunking.

Medición **2026-10-06**, mismo alcance/exclusiones antes y después:


| Componente     | Líneas antes → después | Ramas antes → después |
| ---------------- | --------------------------- | ------------------------- |
| Backend Python | 46,62 % →**57,24 %**     | 29,91 % →**45,25 %**   |
| Frontend       | 41,68 % →**80,52 %**     | 43,70 % →**72,51 %**   |

Validación: **302 Python**, **23 Node**, **94 React** y **5 E2E con API simulada**
aprobados; 3 evaluaciones reales omitidas y 2 xfail estrictos existentes.
TypeScript, build Next y locks verificados. No se ejecutó scanner SonarQube ni
evaluación facturable. Quedan áreas con poca cobertura, especialmente pantallas
heredadas y scripts operativos; los porcentajes no son garantía del Quality Gate.

## Seguridad y despliegue

- `/session/bootstrap` emite una identidad anónima firmada en cookie HttpOnly;
  consultas y conversaciones requieren esa identidad y validan propietario.
  Google OAuth 2.0 permite autenticación con cuenta de Google; los usuarios
  autenticados con Google tienen su información (nombre, foto) guardada en
  PostgreSQL. Los tokens JWT se almacenan en cookies httpOnly (más seguro que localStorage).
- Administración: `ADMIN_ENDPOINTS_ENABLED=true` y una `ADMIN_API_KEY` independiente.
  No hay bypass por estar en desarrollo. No pongas esa clave en el navegador.
- Producción: orígenes CORS explícitos, secretos aleatorios, HTTPS, cookies y
  límites compartidos entre workers. Consulta [seguridad](docs/SECURITY.md).
- Docker/Podman **no eliminan exposición de red**: `0.0.0.0` dentro del contenedor
  permite llegar al servicio; revisa puertos publicados, proxy y firewall del host.
  Compose de desarrollo limita sus servicios a loopback, pero usa PostgreSQL
  `trust` y credenciales de prueba: **no es configuración de producción**.
- Ingesta conserva PDF/Markdown y evidencia SHA-256. Un `evidence_id` o
  `graph_write_state=unverified` no acredita fuente oficial ni vigencia legal.

## Documentación por objetivo


| Quiero…                                        | Documento                                                                                                 |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Usar la API y entender errores/permisos         | [API](API_DOC.md)                                                                                         |
| Ejecutar y ampliar tests                        | [Guía única](tests/README.md)                                                                           |
| Entender el frontend activo                     | [Arquitectura frontend](frontend/README_ARCHITECTURE.md)                                                  |
| Preparar despliegue                             | [Render / checklist](DEPLOY_RENDER.md), [plantilla de entorno](env.production.example)                    |
| Cargar/revisar corpus y grafo                   | [Knowledge Graph](KNOWLEDGE_GRAPH_SETUP.md)                                                               |
| Entender validación y abstención              | [Pipeline](backend/VALIDATION_GUIDE.md)                                                                   |
| Configurar OAuth local                          | [OAuth](OAUTH_SETUP.md)                                                                                   |
| Diagnosticar PostgreSQL sin perder datos        | [Conexión PostgreSQL](POSTGRES_CONNECTION_ISSUES.md)                                                     |
| Importar cobertura a SonarQube                  | [SonarQube](docs/SONARQUBE.md)                                                                            |
| Consultar antecedentes, no capacidades actuales | [Migración Cohere](CHANGELOG_MIGRACION_COHERE.md), [auditoría 2026-10-01](docs/AUDITORIA-2026-10-01.md) |
| Revisar propuestas aún no implementadas        | [PDF cloud](CLOUD_PDF_PIPELINE.md), [plan SAT/Graph](docs/SAT-GRAPH-IMPLEMENTATION-PLAN.md)               |
| Seguir el plan del harness de evaluación        | [Plan del harness](docs/HARNESS-IMPLEMENTATION-PLAN.md)                                                   |
