# Guía única de tests

Todas las pruebas del proyecto viven en **`tests/`**, separadas primero por
**backend**, **frontend** y **scripts**, y después por tipo. Este
documento es la referencia única de ejecución, alcance y catálogo de casos;
incluye Python, scripts Node, componentes/hooks del frontend, Playwright y calidad del
modelo. Las pruebas manuales heredadas se conservan separadas, nunca se ejecutan
como parte de la suite automática.

## Inicio rápido

Desde la raíz del repositorio, con Python compatible con `pyproject.toml`, UV,
Node **24** y pnpm instalados:

```powershell
uv sync --frozen --extra dev --inexact
pnpm install --frozen-lockfile
pnpm test
```

No se arranca Docker, la API ni un modelo real. Los tests HTTP no ejecutan el
lifespan: sustituyen PostgreSQL, Redis, Cohere y RAG remoto por dobles de prueba.
La ingesta usa archivos temporales; la comprobación PDF procesa bytes sintéticos
con parsers locales, sin OCR ni descarga de pesos. Los 3 casos reales del modelo
se muestran como **skipped**; los 2 escenarios temporales conocidos son
**xfail estricto**, no funcionalidades implementadas.

## Comandos por objetivo


| Objetivo | Comando desde raíz | Alcance/coste |
|---|---|---|
| Suite offline completa | `pnpm test` | Python + scripts Node + frontend React; sin proveedores |
| Solo Python / backend / scripts | `pnpm test:python` / `pnpm test:backend` / `pnpm test:scripts` | Offline |
| Backend + evaluaciones reales | `pnpm test:backend --run-model-evals` | Solo backend; Cohere + juez OpenAI, red/coste |
| Solo scripts Node | `pnpm test:node` | Sin React ni navegador |
| Frontend unitarios, componentes e integración | `pnpm test:frontend` | Vitest + jsdom + MSW; red no simulada rechazada |
| Cobertura frontend | `pnpm test:frontend:coverage` | LCOV, HTML no requerido y resumen JSON |
| Toda la suite + evaluación real del generador | `pnpm test:all --run-model-evals` | Cohere + juez OpenAI; red/coste |
| Solo calidad real | `pnpm test:quality --run-model-evals` | Tres casos sintéticos; red/coste |
| Solo evaluador offline | `pnpm test:quality:offline` | Sin proveedor |
| Harness de evaluación offline | `pnpm test:harness` | Gold, métricas, cassettes y umbrales; sin proveedor |
| Harness real | `pnpm test:harness:real --run-model-evals` | Pipeline real con `EVAL_MODE=1` (temperatura 0, sin caché, 3 muestras); red/coste |
| Cobertura Python + frontend | `pnpm test:coverage` | Cobertura/xUnit Python y LCOV frontend |
| Lo anterior + scanner y Quality Gate | `pnpm sonar` | Token desde backend/.env; solo tras éxito de todas las suites |
| Navegador con API simulada | `pnpm test:e2e` | Arranca Next en localhost:3100; sin backend ni modelos |
| Navegador con servicios reales | `pnpm test:e2e:real --run-model-evals` | Instalación local de prueba; una consulta puede facturar |
| Launcher de desarrollo | `pnpm test:dev-full` | Arranque simulado |

**Confirmación explícita:** `test:all` sin flag sigue offline. `test:quality` y
`test:e2e:real` sin `--run-model-evals` fallan antes de arrancar procesos.
El flag en `test:all` activa los casos Python de calidad, **no** los E2E reales:
estos tienen su propio comando porque necesitan navegador y servicios.
Las suites offline no leen credenciales de proveedores. El runner continúa las
otras suites aunque una falle y devuelve exit distinto de cero; el scanner se
omite ante cualquier fallo. No se cambian umbrales del Quality Gate.

### Backend y frontend por separado

Ejecuta estos comandos desde la raíz del repositorio:

```powershell
# Solo backend, sin modelos reales
pnpm test:backend

# Solo frontend: unitarios, componentes e integración, sin modelos reales
pnpm test:frontend

# Solo backend, incluyendo las evaluaciones reales (credenciales, red y coste)
pnpm test:backend --run-model-evals

# Frontend en navegador, con API simulada y sin modelos reales
pnpm test:e2e
```

El último comando requiere Chromium instalado o el canal Edge descrito en
[E2E de navegador](#e2e-de-navegador-simulado-y-real). Los E2E con servicios
reales son independientes y requieren `test:e2e:real --run-model-evals`.

### Seleccionar una carpeta, un caso o un marcador

En comandos Python/globales, las opciones adicionales se reenvían a **pytest**.
En `test:frontend`/`test:frontend:coverage` se reenvían a **Vitest**; en comandos
E2E se reenvían a **Playwright**. Ejemplos frontend:

```powershell
pnpm test:frontend tests/frontend/component/TerminalModal.test.tsx
pnpm test:frontend -t "NDJSON"
pnpm test:frontend --reporter=verbose
```

Selección Python:

```powershell
pnpm test:backend
pnpm test:frontend
pnpm test:scripts
pnpm test:python tests/backend/unit
pnpm test:python tests/backend/integration
pnpm test:python tests/backend/security
pnpm test:python tests/backend/http tests/backend/contract
pnpm test:python tests/backend/bdd tests/backend/benchmark
pnpm test:python tests/backend/unit/test_chat_response_persistence.py -v
pnpm test:python tests/backend/unit/test_source_evidence.py tests/backend/security/test_upload_security.py
pnpm test:python tests/backend/unit/test_file_utils.py::test_find_duplicate_files_returns_empty_for_empty_directory
pnpm test:python -m security
pnpm test:python --collect-only

# Alternativa directa (solo Python): configuración y lock explícitos
uv run --frozen --extra dev --inexact pytest -c pytest.ini tests/backend/unit -q
```

Las carpetas `unit`, `integration`, `security`, `http`, `contract`, `bdd` y
`benchmark` asignan su marcador automáticamente. `quality` conserva marcas
explícitas distintas: `quality` es offline; `model_quality` requiere opt-in.
`--collect-only` lista casos parametrizados sin ejecutarlos ni activar modelos.
Para scripts Node usa `pnpm test:node`; React usa `pnpm test:frontend`. El test del launcher requiere
`npm_execpath`, que pnpm proporciona (no ejecutes ese archivo directamente con
`node --test` desde una consola desnuda).

## Estructura y alcance

```text
tests/
  README.md                  # Guía única y catálogo de todos los componentes
  conftest.py                # Hooks comunes, temporales y opt-in de modelos
  backend/
    conftest.py              # Fixtures HTTP y RAG propias del backend
    fixtures/                # Datos sintéticos y helpers de backend
    unit/                    # Regresiones de servicios/validadores
    integration/             # Pipeline con dependencias simuladas
    security/                # Auth, privacidad y uploads
    http/                    # Rutas y eventos con FastAPI TestClient
    contract/                # Schemas y formatos
    bdd/                     # Comportamiento y limitaciones explícitas
    benchmark/               # Recuperación local
    quality/                 # Evaluador offline y casos reales opt-in
    harness/                 # Harness de evaluación offline: gold, métricas, cassettes (ver fases F0-F6)
    manual/                  # Diagnósticos heredados, fuera del discovery
  frontend/
    unit/                    # Mapeos y clientes API/auth con Vitest
    component/               # Componentes React y acciones de usuario
    integration/             # Hooks y pantalla con dependencias simuladas
    fixtures/                # Setup MSW, datos y API sintética de navegador
    vitest.config.mts        # React único, discovery y LCOV
    e2e/                     # Playwright y su configuración exclusiva
  scripts/
    unit/                    # Launchers, runner y controles de estructura
```

`pytest.ini` descubre solo `tests/`, configura `pythonpath = backend`, usa
`test_*.py` y excluye `backend/manual/`/`backend/fixtures/` del discovery recursivo.
`tests/conftest.py` centraliza hooks y opciones comunes y registra los fixtures
de validación de `backend/fixtures/validation.py`. Los fixtures HTTP y RAG se
limitan al backend mediante `tests/backend/conftest.py`. Los helpers reutilizados
por sus suites viven en `backend/fixtures/`, no se importan desde otro test.
Así se conserva la separación de componentes sin devolver los tests a las
carpetas de código de producto ni duplicar `pytest.ini`.
`backend/evaluation/model_quality.py` y `deepeval_tests.py` siguen siendo
**implementación**, no suites: la aplicación también usa el evaluador histórico.
Los casos del benchmark viven en `backend/fixtures/quality_cases.json`; el cuerpo JSON
de prueba HTTP heredado se conserva en `backend/fixtures/test_request.json`.

### Catálogo de suites

Los números dinámicos de casos parametrizados se consultan con `--collect-only`;
el inventario al final identifica **cada función/escenario base** sin prometer que
un skip es una prueba aprobada o que un test simulado certifica infraestructura.


| Suite (ruta relativa a`tests/`)                                                      | Qué verifica                                                                                                                                                  |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`backend/bdd/test_conflicting_rules.py`](backend/bdd/test_conflicting_rules.py)                     | Reglas contradictorias, fuentes y dos limitaciones conocidas de selección temporal y trazabilidad de modificaciones (xfail estricto).                         |
| [`backend/benchmark/test_local_retrieval.py`](backend/benchmark/test_local_retrieval.py)             | 25 recuperaciones locales sobre corpus de 2, 32 y 128 documentos; mide latencia con perf_counter, sin umbral de velocidad.                                     |
| [`backend/contract/test_shapes.py`](backend/contract/test_shapes.py)                                 | Entrada estricta, límites de consulta, idioma admitido, NDJSON Unicode y estructura RAG local.                                                                |
| [`backend/http/test_api.py`](backend/http/test_api.py)                                               | Bootstrap, autorización, caché de consulta/stream, validación 422 y barrera administrativa antes de tocar documentos.                                       |
| [`backend/integration/test_validation_pipeline.py`](backend/integration/test_validation_pipeline.py) | Pipeline de validación completo con corpus en memoria y Cohere simulado: fuentes, riesgo, confianza, corrección, opciones y tiempos.                         |
| [`backend/quality/test_evaluator.py`](backend/quality/test_evaluator.py)                             | Carga del dataset, dirección de métricas, fallos/timeout, generación no vacía, informes, privacidad, credenciales, juez explícito y opt-in; todo offline. |
| [`backend/quality/test_model_quality.py`](backend/quality/test_model_quality.py)                     | Tres casos sintéticos parametrizados de generación Cohere y juez DeepEval; se omiten salvo autorización explícita de red/coste.                            |
| [`backend/security/test_chat_security.py`](backend/security/test_chat_security.py)                   | Sesiones firmadas, caducidad, cookies, dueño en caché/BD, 404/503/429, salud degradada, redacción de errores/logs y reasignación segura.                   |
| [`backend/security/test_upload_and_auth.py`](backend/security/test_upload_and_auth.py)               | Clave administrativa, firma/MIME/tamaño PDF, rutas confinadas, limpieza, límites exactos y rechazo de sesiones ausentes o alteradas.                         |
| [`backend/security/test_upload_security.py`](backend/security/test_upload_security.py)               | Carga administrativa, evidencia por bytes, metadatos saneados, errores del procesador/almacén, colisiones y conservación de archivos existentes.             |
| [`backend/unit/test_anti_hallucination.py`](backend/unit/test_anti_hallucination.py)                 | Patrones legales sospechosos, respuestas vacías/cortas, score RAG, riesgo acotado, penalizaciones y umbrales.                                                 |
| [`backend/unit/test_audit_remediation.py`](backend/unit/test_audit_remediation.py)                   | Regresiones de auditoría: traducción completa, fallos sin caché parcial, contratos, dueño, contexto/historial, claves de caché privadas y logs sin PII.   |
| [`backend/unit/test_chat_response_persistence.py`](backend/unit/test_chat_response_persistence.py)   | Extracción por idioma, persistencia de respuestas generadas/cacheadas y fechas UTC aware/naive con offsets positivos y negativos.                             |
| [`backend/unit/test_cross_checker.py`](backend/unit/test_cross_checker.py)                           | Afirmaciones con soporte, corpus vacío, score de solapamiento, tipos, chunks, caché de tokens e invalidación.                                               |
| [`backend/unit/test_dependency_compatibility.py`](backend/unit/test_dependency_compatibility.py)     | PDF sintético real con ReportLab, pypdf y backend PDFium de Docling; sin descargar modelos ni ejecutar OCR.                                                   |
| [`backend/unit/test_dev_server_binding.py`](backend/unit/test_dev_server_binding.py)                 | Launcher local limitado a loopback y guard de importación, manteniendo el arranque independiente del contenedor.                                              |
| [`backend/unit/test_file_utils.py`](backend/unit/test_file_utils.py)                                 | SHA-256 de bytes completos, lectura por bloques, archivos ausentes y agrupación de duplicados.                                                                |
| [`backend/unit/test_llm_optimizer.py`](backend/unit/test_llm_optimizer.py)                           | Caché, TTL/invalidation, compresión de prompts, estimación/contabilidad de tokens y estadísticas.                                                          |
| [`backend/unit/test_pipeline_remediation.py`](backend/unit/test_pipeline_remediation.py)             | Recuperación sin corte en 50 candidatos, chunks reales, ausencia de evidencia, ciclo de vida/ready/reintentos/cierre y salidas JSON/stream coherentes.        |
| [`backend/unit/test_rag_fallback.py`](backend/unit/test_rag_fallback.py)                             | Fallback local ante falta/fallo de LightRAG o reranking; fuente explícita, corpus vacío, chunking por longitud y scores locales.                             |
| [`backend/unit/test_self_correction.py`](backend/unit/test_self_correction.py)                       | Corrección simulada, condición de activación, tipos, respuesta vacía, errores Cohere y máximo de reintentos.                                              |
| [`backend/unit/test_source_evidence.py`](backend/unit/test_source_evidence.py)                       | Identidad SHA-256, UTF-8 exacto, reintentos/tampering, consistencia carga/lote, fallos cerrados, colisiones y detección de caracteres de reemplazo.           |
| [`backend/unit/test_startup_safety.py`](backend/unit/test_startup_safety.py)                         | Neo4j desactivado selecciona NetworkX sin importarlo y salida de consola tolera caracteres no codificables.                                                    |
| [`backend/unit/test_utc_datetimes.py`](backend/unit/test_utc_datetimes.py) | Timestamps Redis independientes de la zona local, salud UTC, fechas de validación y archivos, y guard contra conversiones UTC sin zona. |
| [`scripts/unit/dev-full.test.mjs`](scripts/unit/dev-full.test.mjs)                   | Arranque Docker solo PostgreSQL/Redis, healthchecks, argumentos seguros en Windows, npm_execpath y espera del backend antes del frontend.                      |
| [`scripts/unit/run-tests.test.mjs`](scripts/unit/run-tests.test.mjs)                 | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner.          |
| [`scripts/unit/test_repository_layout.py`](scripts/unit/test_repository_layout.py)                   | Exigir componente y tipo dentro del árbol único, impedir suites dispersas y mantener catálogo por caso, configuración, dataset y manuales.                                   |
| [`frontend/unit/apiService.test.ts`](frontend/unit/apiService.test.ts) | Dos llamadas simultáneas comparten bootstrap; bootstrap y petición protegida incluyen cookies. También cubre los casos detallados en su inventario. |
| [`frontend/unit/authService.test.ts`](frontend/unit/authService.test.ts) | Login por formulario seguido de /auth/me marca autenticación sin escribir tokens en localStorage. También cubre los casos detallados en su inventario. |
| [`frontend/component/TerminalModal.test.tsx`](frontend/component/TerminalModal.test.tsx) | Cerrado no contiene entrada; al abrir enfoca el textbox. También cubre los casos detallados en su inventario. |
| [`frontend/component/HistoryPanel.test.tsx`](frontend/component/HistoryPanel.test.tsx) | Cerrado no se renderiza y vacío muestra un mensaje explícito. También cubre los casos detallados en su inventario. |
| [`frontend/component/ChatInput.test.tsx`](frontend/component/ChatInput.test.tsx) | No envía espacios; Shift+Enter introduce línea y Enter envía texto recortado. También cubre los casos detallados en su inventario. |
| [`frontend/component/ChatSidebar.test.tsx`](frontend/component/ChatSidebar.test.tsx) | Error muestra reintento; durante carga el botón está deshabilitado. También cubre los casos detallados en su inventario. |
| [`frontend/component/MarkdownRenderer.test.tsx`](frontend/component/MarkdownRenderer.test.tsx) | Renderiza encabezado, lista, tabla GFM y Unicode; enlaces nuevos protegen opener/referrer. También cubre los casos detallados en su inventario. |
| [`frontend/component/ChatMessage.test.tsx`](frontend/component/ChatMessage.test.tsx) | Error muestra fallo sin badge Validado. También cubre los casos detallados en su inventario. |
| [`frontend/component/AuthProvider.test.tsx`](frontend/component/AuthProvider.test.tsx) | Restaura estado desde cookie y retira flag de login, sin persistir tokens. También cubre los casos detallados en su inventario. |
| [`frontend/integration/useChatSessions.test.tsx`](frontend/integration/useChatSessions.test.tsx) | Montaje carga listado sin borrar ni seleccionar automáticamente la sesión activa. También cubre los casos detallados en su inventario. |
| [`frontend/integration/useChat.test.tsx`](frontend/integration/useChat.test.tsx) | NDJSON por byte conserva ñ/emoji y final reemplaza parcial; sidebar recibe título y conteo. También cubre los casos detallados en su inventario. |
| [`frontend/integration/ChatPage.test.tsx`](frontend/integration/ChatPage.test.tsx) | Monta pantalla/hooks/API real del frontend con red MSW: crea sesión antes de consultar y muestra final. También cubre los casos detallados en su inventario. |
| [`frontend/e2e/chat-persistence.spec.js`](frontend/e2e/chat-persistence.spec.js) | Chromium + API sintética: consulta/final, refresh a landing y selección restaura respuesta persistida. También cubre los casos detallados en su inventario. |
| [`frontend/e2e/chat.real.spec.js`](frontend/e2e/chat.real.spec.js) | Con flag y servicios locales, interrupción temporal de listado se recupera al reintentar. También cubre los casos detallados en su inventario. |
| [`frontend/unit/chatSessionMeta.test.mts`](frontend/unit/chatSessionMeta.test.mts) | Regresiones originales de metadata/hidratación conservadas al migrar a Vitest. |
| [`frontend/unit/useChatSessions.test.mts`](frontend/unit/useChatSessions.test.mts) | Regresiones originales de metadata/hidratación conservadas al migrar a Vitest. |

### Limitaciones explícitas

- `backend/bdd/test_conflicting_rules.py` mantiene dos `xfail(strict=True)`: la
  recuperación no selecciona vigencia temporal ni prueba una cadena de evidencia
  de la Action modificadora. Un XPASS falla para exigir revisar el contrato.
- Los controles de permisos y persistencia ahora son asserts ordinarios, no
  xfails de seguridad. La suite no certifica seguridad ni exactitud jurídica.
- El benchmark local es informativo; no existe un gate de rendimiento.
- La suite frontend monta React con jsdom y prueba acciones, hooks y errores.
  jsdom no certifica layout, CSS, canvas ni todos los aspectos de accesibilidad;
  estos se contrastan con los E2E Chromium. Axe es un control parcial, no una
  certificación de accesibilidad.
- Las pruebas facturables no se incluyen sin el flag explícito; los mocks no certifican persistencia o aislamiento real.

## Cobertura y SonarQube

```powershell
pnpm test:coverage
pnpm sonar
```

Se generan `coverage.xml` (Cobertura de backend) y
`temp/sonar-reports/pytest.xml` (xUnit Python legacy con archivo de test), además
de `temp/sonar-reports/frontend-coverage/lcov.info` y `coverage-summary.json`.
Sonar analiza `backend,frontend/src,frontend/app` como producto y `tests` como
pruebas; excluye manuales/fixtures, no módulos de producto sin cobertura.
`sonar.javascript.lcov.reportPaths` importa JS/TS; el XML Python se conserva.
Los scores de DeepEval y el número de tests **no** equivalen a cobertura.
La cobertura incluye archivos no importados; se documenta la línea base sin
prometer 80% ni bajar el gate. Las rutas `SF:` del LCOV deben resolver desde raíz.
[Referencia Sonar](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/test-coverage/javascript-typescript-test-coverage).

`SONAR_TOKEN` se lee del único `backend/.env` privado (o del entorno para CI),
sin pasarlo como argumento ni copiar las otras claves a los tests. Configuración,
arranque, permisos y advertencias del scanner: [guía SonarQube](../docs/SONARQUBE.md).

## E2E de navegador: simulado y real

```powershell
pnpm exec playwright install chromium
pnpm test:e2e --list
pnpm test:e2e
```

El modo predeterminado utiliza API sintética interceptada por Playwright, bloquea
destinos externos, arranca Next en **localhost:3100** y lo detiene al terminar.
No reutiliza un servidor existente: deja libre ese puerto. Usa movimiento reducido
para omitir la animación inicial y Chromium headless. No necesita PostgreSQL,
Redis, claves ni modelos. Los artefactos van a `temp/playwright-results/`.

Si prefieres Edge instalado en Windows (sin descargar Chromium):

```powershell
$env:PLAYWRIGHT_CHANNEL = 'msedge'
pnpm test:e2e
# Volver a Chromium:
Remove-Item Env:PLAYWRIGHT_CHANNEL -ErrorAction SilentlyContinue
```

El canal también se admite en el comando real. Si `playwright install` informa
un bloqueo `__dirlock`, no borres la caché mientras otra instalación esté activa;
espera a que termine o usa Edge. No se modifican instalaciones de otros proyectos.

Para servicios reales, primero arranca una instalación local **de prueba** con
backend/frontend/PostgreSQL/Redis y los modelos configurados en el único
`backend/.env`. No se arranca ni modifica infraestructura automáticamente:

```powershell
$env:PLAYWRIGHT_TARGET_URL = 'http://localhost:3000'
$env:PLAYWRIGHT_API_URL = 'http://localhost:8000'
pnpm test:e2e:real --run-model-evals --list
pnpm test:e2e:real --run-model-evals
# Solo una consulta real (el resto no llama al generador):
pnpm test:e2e:real --run-model-evals --grep "consulta real sintética"
```

Solo se admiten destinos loopback; el flag se consume en el runner y autoriza
`RUN_MODEL_EVALS=1` únicamente para este proceso. El entorno por sí solo no activa
el comando. Tres escenarios, un worker, cero retries y timeout de 180 s/caso.
La consulta sintética lleva ID temporal para evitar reutilizar una respuesta
cacheada; la conversación creada se elimina en `finally`. Si esa limpieza falla,
revisa la base de prueba. Los tests no borran conversaciones preexistentes.
No se guardan trazas, vídeo ni capturas de los casos reales. No usar datos
personales, cuentas reales de usuarios ni producción. El flag confirma coste,
**no impone un límite monetario**: configura presupuesto en los proveedores.

El E2E real verifica respuesta/persistencia/aislamiento HTTP, no calidad jurídica
ni garantiza qué proveedor interno respondió. Para medir el generador sin
fallback y un juez real usa `pnpm test:quality --run-model-evals`.

## Diagnósticos manuales heredados

Estos archivos se trasladaron sin convertirlos en pytest. No los ejecutan
`test`, `test:all`, cobertura ni Sonar: hacen IO real, varios imprimen errores en
vez de assertions y su código de salida no es un gate de calidad fiable.


| Archivo                                  | Función y requisitos                                                    | Estado/riesgo                                                                                                       |
| ------------------------------------------ | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `backend/manual/diagnose_connection.py`          | Prueba PostgreSQL y Redis en varios hosts con configuración del backend | Manual; servicios reales, no CI                                                                                     |
| `backend/manual/diagnose_pg_connection.py`       | Compara psycopg con contraseña, trust y URL                             | Heredado: configuración local fija, no garantía de entorno actual                                                 |
| `backend/manual/diagnose_postgres.py`            | asyncpg directo, SQLAlchemy async y URL sin contraseña                  | Heredado: configuración local fija, no usar con producción                                                        |
| `backend/manual/diagnose_settings_connection.py` | psycopg con settings actuales, sin imprimir URL con contraseña          | Manual; no muestra errores crudos del proveedor                                                                     |
| `backend/manual/benchmark_optimized_pipeline.py` | Procesamiento paralelo de PDF                                            | **No ejecutable actualmente**: faltan `ingestion.optimized_pipeline` y `config.performance_settings`                |
| `backend/manual/benchmark_real_performance.py`   | Reprocesamiento y restauración de PDFs                                  | **No ejecutar sobre datos reales**: borra `docs/processed` y el backup anterior; además faltan los mismos módulos |

Para un diagnóstico de conexión autorizado, ejecuta desde `backend/` para leer
el único `.env` y conservar rutas heredadas:

```powershell
Push-Location backend
try { uv run --frozen --extra dev --inexact python ../tests/backend/manual/diagnose_connection.py }
finally { Pop-Location }
```

No actives confianza sin contraseña ni ejecutes los scripts de rendimiento
destructivos para “pasar tests”. Esos scripts requieren modernización y un
directorio desechable aislado antes de habilitarse; no se ejecutaron aquí.

## Calidad real del modelo

### Configurar los proveedores una vez

En tu archivo privado `backend/.env`, añade o completa:

```dotenv
COHERE_API_KEY=tu_clave_de_cohere
OPENAI_API_KEY=tu_clave_del_proveedor_del_juez
EVAL_JUDGE_MODEL=identificador_de_modelo_openai_compatible_con_deepeval_4_2_8
```

- `COHERE_API_KEY`: genera las respuestas. El modelo, temperatura y máximo de tokens se toman de la configuración real del backend (`COHERE_LLM_MODEL`, `COHERE_TEMPERATURE`, `COHERE_MAX_TOKENS`).
- `OPENAI_API_KEY`: credencial del juez de DeepEval, **no** la suscripción de ChatGPT/Codex ni un token de SonarQube.
- `EVAL_JUDGE_MODEL`: sustituye el texto del ejemplo por el identificador de un modelo habilitado en tu cuenta y admitido por `GPTModel` de la versión instalada. Es obligatorio para que el juez no cambie silenciosamente al modelo predeterminado de DeepEval. No se elige ni se cobra un modelo por ti durante la configuración.

Solo el modo real carga este archivo explícitamente para comprobar las credenciales; las variables ya presentes en el proceso tienen prioridad. No pegues las claves en comandos, Markdown, capturas o chats. El `.env` queda fuera de Git por `.gitignore`, pero sigue siendo texto plano: restringe sus permisos y no lo compartas ni sincronices públicamente.

Si faltan variables, el modo real se detiene con los **nombres** de las variables faltantes. No ejecuta una evaluación simulada, no muestra sus valores y no omite silenciosamente los casos solicitados. Sin `--run-model-evals`, pytest omite los casos reales incluso si existen las claves.

### Qué se evalúa realmente

El dataset inicial de `tests/backend/fixtures/quality_cases.json` contiene tres escenarios con **fichas ficticias**, no legislación ni expedientes personales:

1. Alimentos: conservar los requisitos del contexto sin inventar otros.
2. Visitas: reconocer que el contexto no aporta un plazo.
3. Protección: responder sin exclusiones ni estereotipos sobre género o procedencia rural.

Cada caso sigue este flujo:

1. El generador de `LegalAgent` usa los prompts reales del backend con el contexto controlado del caso.
2. Cohere produce una **respuesta nueva**; una respuesta vacía, un error o falta de cliente falla, sin fallback.
3. La respuesta entra en `LLMTestCase`, con `context` y `retrieval_context` explícitos.
4. DeepEval ejecuta cinco métricas con el juez configurado.
5. El caso aprueba solo si **todas** las métricas aprueban y no hay errores. Un promedio alto no oculta una alucinación o un fallo del juez.


| Métrica            | Umbral en DeepEval**4.2.8** | Qué observa                                          |
| --------------------- | ----------------------------- | ------------------------------------------------------- |
| `relevancy`         | ≥ 0.7                      | Relevancia de la respuesta para la pregunta           |
| `faithfulness`      | ≥ 0.7                      | Apoyo de las afirmaciones en el contexto suministrado |
| `context_relevancy` | ≥ 0.7                      | Relevancia del contexto controlado                    |
| `bias`              | ≥ 0.7                      | Proporción sin sesgo según el juez                  |
| `hallucination`     | ≥ 0.7                      | Proporción coherente con el contexto de referencia   |

El código utiliza `metric.is_successful()`, no una comparación genérica. Las versiones más nuevas de DeepEval pueden cambiar la dirección o significado de una puntuación: la tabla describe **la versión fijada en este proyecto**, no “latest”. No compares scores entre versiones como si fueran equivalentes. [Introducción oficial a las métricas](https://deepeval.com/docs/metrics-introduction).

`expected_output` se conserva como referencia humana en el dataset y el informe; estas cinco métricas no hacen una comparación textual exacta ni una evaluación completa de corrección contra esa respuesta esperada.

#### Qué NO certifica

Este es un benchmark inicial del **generador con contexto controlado**, no una evaluación end-to-end de recuperación RAG, reranking, base de datos, HTTP, streaming o traducción. Los tres casos iniciales son en español. No certifica exactitud jurídica, seguridad clínica ni calidad de quechua: hacen falta un corpus jurídico fechado y revisado por especialistas, casos bilingües validados y más escenarios antes de hacer esas afirmaciones. El juez puede equivocarse y sus resultados pueden variar; revisa respuestas y razones, no solo el porcentaje final.

El endpoint administrativo `POST /evaluate-system` conserva los cinco casos históricos de respuestas fijas y devuelve `evaluation_scope = fixed_responses_not_model_generation`. **No equivale a `test:quality`** ni prueba el modelo actual. Se mantiene por compatibilidad y sigue dependiendo de la configuración/autorización administrativa de la aplicación.

### Informes y límites

Cada ejecución real crea una carpeta única en:

```text
temp/model-backend/quality/<fecha-UTC>-<id>/
  results.json
  report.md
```

El JSON conserva pregunta, contexto, referencia, respuesta generada, modelo generador/juez, versión de DeepEval, idioma, parámetros de generación, hash del prompt y del caso, puntuaciones, umbrales, razones y flags de aprobación. El Markdown ofrece el resumen por caso y métrica. Se escribe después de cada caso y al finalizar, incluso si un assert falla. Un fallo de preconfiguración antes de ejecutar casos no genera un informe de calidad.

Los mensajes crudos de excepciones de los SDK no se guardan; se registra su tipo para evitar exponer secretos. Si hay un fallo, distingue una métrica insuficiente de un error de proveedor/timeout. Los informes son locales e ignorados por Git bajo `temp/`, pero contienen respuestas y contexto: trata como sensibles cualquier dataset real que añadas.

Por defecto, cada caso tiene un límite de **180 segundos**, incluyendo generación y métricas. Los tres casos se ejecutan secuencialmente; cada métrica puede hacer varias llamadas al juez. No existe un presupuesto monetario automático: controla el gasto en los proveedores antes de ejecutar o repetir pruebas. Los prompts/contextos se envían a Cohere y al proveedor del juez; no uses datos personales sin autorización.

Puedes ajustar límites o destino:

```powershell
pnpm run test:quality --run-model-evals --model-eval-timeout 120 --quality-report-dir temp/mi-evaluacion
```

El runner desactiva la telemetría opcional de DeepEval con `DEEPEVAL_TELEMETRY_OPT_OUT=YES`. Usa las métricas directamente y genera informes locales, sin `evaluate()`/`assert_test()` ni integración de subida a Confident AI. [Ejecución individual de métricas](https://deepeval.com/docs/metrics-hallucination).

### Mantener y ampliar las evaluaciones

1. Añade casos con un `id` único, `input`, `expected_output`, una lista no vacía `context` y opcionalmente `language` a `tests/backend/fixtures/quality_cases.json`.
2. Mantén los controles offline de carga del dataset sincronizados si cambia el número de casos.
3. Revisa las referencias y el contexto con especialistas; no conviertas material sintético en afirmaciones sobre leyes vigentes.
4. Ejecuta `test:quality:offline`, luego `test:quality --run-model-evals` con el presupuesto autorizado.
5. Compara informes con los mismos casos, modelos, versión y parámetros. No reduzcas umbrales solo para conseguir verde ni ocultes errores con skips o simulaciones.

Los fallos existentes de otras suites seguirán visibles al ejecutar `test`/`test:all`; no son automáticamente una regresión del modelo. La suite de calidad puede ejecutarse por separado mientras se corrigen.

#### Migración de puntuaciones

DeepEval 4.2.8 invierte la dirección histórica de Bias/Hallucination: ahora mayor es mejor. Se exige ≥0.7 y se usa `metric.is_successful()`; no comparar directamente con informes de 3.8.4 (≤0.3). [Bias](https://deepeval.com/docs/metrics-bias), [Hallucination](https://deepeval.com/docs/metrics-hallucination).

## Problemas frecuentes


| Síntoma                                   | Acción                                                                                                                                                                                                          |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Import/fixture no encontrado               | Ejecuta desde raíz con`pnpm test:python`; no recrees `backend/pytest.ini` ni copies fixtures. Usa `uv sync --frozen --extra dev --inexact`                                                                      |
| Casos reales omitidos                      | Es intencional; añade `--run-model-evals` a `test:quality`/`test:all` solo con credenciales, red y presupuesto autorizados |
| Configuración del juez incompleta         | Completa variables de`backend/.env`; no sustituyas con una suscripción ChatGPT ni pegues claves en el chat                                                                                                      |
| Exit 1 tras subida Sonar                   | Revisa Quality Gate: no equivale a error de autenticación/importación                                                                                                                                          |
| AccessDenied de temporales en Windows      | Pytest usa directorios únicos en`temp/pytest-runs` y caché `temp/pytest-cache`; no cambia ACLs ni borra carpetas anteriores. El scanner puede encontrar cachés antiguos sin permisos: consulta la guía Sonar |
| Warning Node`MODULE_TYPELESS_PACKAGE_JSON` | Node 24 reinterpreta los helpers TS existentes como ESM; aviso no bloqueante, no se cambia el tipo global del frontend para no romper configs CommonJS                                                           |
| Warning deprecado Pydantic/SDK/datetime    | Son advertencias existentes, no skips nuevos; revisar en una corrección independiente                                                                                                                           |

Si pasas `--basetemp`, pytest **borra ese directorio**: no uses carpetas de datos,
la raíz del repositorio ni directorios compartidos. La ejecución directa de
pytest no aplica la variable de telemetría del runner; configura
`DEEPEVAL_TELEMETRY_OPT_OUT=YES` si necesitas el mismo comportamiento.

## Añadir o mantener pruebas

1. Elige primero el componente y después el tipo: `tests/backend/<tipo>/`,
   `tests/frontend/<tipo>/` o `tests/scripts/unit/`. No añadas suites a las
   carpetas de producto `backend/`, `frontend/` o `scripts/`. Python usa
   `test_*.py`, scripts Node `*.test.mjs`, frontend Vitest `*.test.ts`/`*.test.tsx`/`*.test.mts` y Playwright `*.spec.js`
   en `tests/frontend/e2e/`.
2. Reutiliza `tests/conftest.py`, `tests/backend/conftest.py` y
   `tests/backend/fixtures/` según su alcance; no importes helpers de otro test.
3. Usa corpus sintéticos, dobles de servicio y temporales. Nuevos tests reales
   deben ser opt-in explícito; no bajar umbrales ni ocultar fallos con skips.
4. Documenta el archivo, su alcance y **cada nombre de caso** en este catálogo.
   `scripts/unit/test_repository_layout.py` exige esa documentación y detecta suites
   dispersas, componentes/tipos incorrectos o una segunda configuración.
5. Ejecuta el tipo/caso afectado, luego `pnpm test` y `pnpm test:coverage` si
   afecta informes. No hace falta llamar a proveedores para validar el layout.

## Verificación histórica de la reorganización — 06/10/2026


| Comprobación               | Resultado                                                                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `pnpm test`                 | 238 Python aprobados, 3 modelos omitidos y 2 xfail estrictos; 25 Node/frontend aprobados                                               |
| `pnpm test:coverage`        | Exit 0; mismos casos y XML regenerados con rutas nuevas                                                                                |
| `pnpm test:quality:offline` | 24 controles aprobados, 3 casos reales deseleccionados                                                                                 |
| `pnpm test:e2e --list`      | Descubre exactamente 3 escenarios;**no** se ejecutó el navegador                                                                      |
| Validación de informes     | 243 casos xUnit con archivo existente bajo`tests/`, cero fallos/errores; 70 módulos Cobertura con `source=backend` y rutas existentes |
| Dependencias                | `pnpm deps:check` pasa, sin cambiar versiones ni locks                                                                                 |

Tras separar por componente se repitieron `pnpm test` y `pnpm test:coverage`:
mismos 243 casos Python, sin perder ninguna variante parametrizada ni sus
explicaciones. `pnpm test:scripts` aprueba 4 controles Python y 21 Node;
`pnpm test:frontend` aprueba 4 Node. `pnpm test:backend` aprueba 234 Python, con 3 modelos omitidos y 2 xfail
estrictos. El evaluador offline mantiene 24 aprobados.

Evidencia local: `temp/sonar-reports/tests-component-initial.log`,
`tests-component-coverage.log` y `tests-component-backend.log`. No se llamó a
proveedores, no se ejecutaron diagnósticos destructivos ni se subió un análisis
Sonar nuevo. La suite conserva las advertencias de deprecación existentes.

## Alcance de las pruebas de ingesta y carga

Las tablas de `backend/unit/test_source_evidence.py` y `backend/security/test_upload_security.py`
incluyen las explicaciones que antes figuraban en el plan SAT. `tmp_path` aísla
los archivos; `monkeypatch` cambia configuración, rutas y dependencias solo
durante cada prueba. Las cargas usan FastAPI `TestClient` con una sesión y un
procesador/motor RAG simulados; los lotes inyectan esos dobles y directorios
temporales. Los casos de colisión, directorios coincidentes y uso directo del
procesador utilizan un convertidor en memoria, no Docling real.

Estos casos verifican persistencia local, respuestas y orden de llamadas. **No**
verifican extracción real de PDF con Docling, oficialidad de fuentes, vigencia
jurídica ni escritura duradera en el grafo. `provenance_state: unverified` y
`graph_write_state: unverified` no son confirmaciones de verificación jurídica
o persistencia del grafo. La prueba independiente de compatibilidad de parsers
PDF se describe en `backend/unit/test_dependency_compatibility.py` y no amplía esas
garantías.

## Inventario completo de casos

### Backend

<details>
<summary>backend/bdd/test_conflicting_rules.py — 3 escenarios base</summary>

Reglas contradictorias, fuentes y dos limitaciones conocidas de selección temporal y trazabilidad de modificaciones (xfail estricto).


| Caso                                                                           | Comprobación                                                           |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `test_given_conflicting_rules_when_keyword_query_then_source_is_reported`      | given conflicting rules when keyword query then source is reported      |
| `test_given_newer_effective_rule_when_reranked_then_new_rule_should_win`       | given newer effective rule when reranked then new rule should win       |
| `test_given_rule_amended_by_action_when_retrieved_then_amendment_is_traceable` | given rule amended by action when retrieved then amendment is traceable |

</details>

<details>
<summary>backend/benchmark/test_local_retrieval.py — 1 escenarios base</summary>

25 recuperaciones locales sobre corpus de 2, 32 y 128 documentos; mide latencia con perf_counter, sin umbral de velocidad.


| Caso                                                                | Comprobación                                                |
| --------------------------------------------------------------------- | -------------------------------------------------------------- |
| `test_offline_keyword_retrieval_reports_elapsed_without_speed_gate` | offline keyword retrieval reports elapsed without speed gate |

</details>

<details>
<summary>backend/contract/test_shapes.py — 5 escenarios base</summary>

Entrada estricta, límites de consulta, idioma admitido, NDJSON Unicode y estructura RAG local.


| Caso                                                        | Comprobación                                        |
| ------------------------------------------------------------- | ------------------------------------------------------ |
| `test_query_request_forbids_unknown_fields_and_empty_query` | query request forbids unknown fields and empty query |
| `test_query_length_bounds_and_language_is_supported`        | query length bounds and language is supported        |
| `test_ndjson_event_has_single_line_and_unicode`             | ndjson event has single line and unicode             |
| `test_rag_result_contract_is_local_not_temporal`            | rag result contract is local not temporal            |
| `test_pdf_report_errors_are_documented_in_openapi` | OpenAPI documenta los errores 500 y 503 del reporte PDF y conserva las respuestas 200 y 422. |

</details>

<details>
<summary>backend/http/test_api.py — 7 escenarios base</summary>

Bootstrap, autorización, caché de consulta/stream, validación 422 y barrera administrativa antes de tocar documentos.


| Caso                                                               | Comprobación                                               |
| -------------------------------------------------------------------- | ------------------------------------------------------------- |
| `test_bootstrap_and_protected_query_gate`                          | bootstrap and protected query gate                          |
| `test_cached_query_does_not_call_external_dependencies`            | cached query does not call external dependencies            |
| `test_admin_gate_precedes_document_access`                         | admin gate precedes document access                         |
| `test_legal_query_rejects_invalid_input_before_retrieval`          | legal query rejects invalid input before retrieval          |
| `test_cached_stream_emits_chunk_then_final_without_external_calls` | cached stream emits chunk then final without external calls |
| `test_pdf_report_preserves_documented_errors` | La dependencia PDF ausente devuelve 503 y el fallo del generador devuelve 500 con sus detalles públicos, sin exponer el error interno. |
| `test_pdf_report_preserves_successful_download` | Éxito conserva bytes, MIME PDF, nombre de descarga y Cache-Control no-store con generador simulado. |

</details>

<details>
<summary>backend/integration/test_validation_pipeline.py — 11 escenarios base</summary>

Pipeline de validación completo con corpus en memoria y Cohere simulado: fuentes, riesgo, confianza, corrección, opciones y tiempos.


| Caso                                              | Comprobación                                                                  |
| --------------------------------------------------- | -------------------------------------------------------------------------------- |
| `test_good_response_passes_pipeline`              | Respuesta bien fundamentada debe pasar el pipeline con status PASSED o WARNED. |
| `test_hallucinated_response_triggers_correction`  | Respuesta con alucinaciones debe disparar self-correction y marcar status.     |
| `test_validated_response_has_all_required_fields` | ValidatedResponse debe tener todos los campos requeridos por el schema.        |
| `test_cross_check_summary_present`                | Con cross_check habilitado, debe haber un CrossCheckSummary en el report.      |
| `test_sources_propagated_from_rag`                | Las fuentes del RAG deben propagarse al ValidatedResponse.                     |
| `test_is_reliable_property`                       | La propiedad is_reliable debe reflejar el estado del report.                   |
| `test_disabled_cross_check`                       | Con enable_cross_check=False, cross_check debe ser None en el report.          |
| `test_disabled_self_correction`                   | Con enable_self_correction=False, no debe llamarse a Cohere para corrección.  |
| `test_quechua_language_accepted`                  | El pipeline debe aceptar language='quechua' sin errores.                       |
| `test_empty_documents_in_rag_result`              | RAG result sin documentos debe manejarse sin error.                            |
| `test_processing_time_recorded`                   | El tiempo de procesamiento debe ser registrado y ser positivo.                 |

</details>

<details>
<summary>backend/quality/test_evaluator.py — 15 escenarios base</summary>

Carga del dataset, dirección de métricas, fallos/timeout, generación no vacía, informes, privacidad, credenciales, juez explícito y opt-in; todo offline.


| Caso                                                                 | Comprobación                                                 |
| ---------------------------------------------------------------------- | --------------------------------------------------------------- |
| `test_metric_uses_its_own_success_direction`                         | metric uses its own success direction                         |
| `test_one_failed_metric_cannot_hide_behind_average`                  | one failed metric cannot hide behind average                  |
| `test_metric_error_is_failure_and_does_not_expose_exception_message` | metric error is failure and does not expose exception message |
| `test_dataset_is_nonempty_unique_and_has_controlled_context`         | dataset is nonempty unique and has controlled context         |
| `test_invalid_dataset_fails`                                         | invalid dataset fails                                         |
| `test_live_credentials_fail_clearly_without_reading_real_env`        | live credentials fail clearly without reading real env        |
| `test_live_pipeline_uses_generated_output_and_saves_report`          | live pipeline uses generated output and saves report          |
| `test_generation_failure_is_reported_without_fallback`               | generation failure is reported without fallback               |
| `test_generation_timeout_is_a_failed_evaluation`                     | generation timeout is a failed evaluation                     |
| `test_empty_generated_response_is_a_failure`                         | empty generated response is a failure                         |
| `test_judge_factory_receives_explicit_model_and_key`                 | judge factory receives explicit model and key                 |
| `test_missing_deepeval_never_silently_falls_back`                    | missing deepeval never silently falls back                    |
| `test_no_opt_in_marks_live_cases_skipped`                            | no opt in marks live cases skipped                            |
| `test_invalid_live_timeout_is_a_usage_error`                         | invalid live timeout is a usage error                         |
| `test_opt_in_without_credentials_is_an_error_not_skip`               | opt in without credentials is an error not skip               |

</details>

<details>
<summary>backend/quality/test_model_quality.py — 1 escenarios base</summary>

Tres casos sintéticos parametrizados de generación Cohere y juez DeepEval; se omiten salvo autorización explícita de red/coste.


| Caso                      | Comprobación      |
| --------------------------- | -------------------- |
| `test_live_model_quality` | live model quality |

</details>

<details>
<summary>backend/security/test_chat_security.py — 14 escenarios base</summary>

Sesiones firmadas, caducidad, cookies, dueño en caché/BD, 404/503/429, salud degradada, redacción de errores/logs y reasignación segura.


| Caso                                                            | Comprobación                                            |
| ----------------------------------------------------------------- | ---------------------------------------------------------- |
| `test_signed_sessions_are_distinct_expire_and_reject_tampering` | signed sessions are distinct expire and reject tampering |
| `test_session_cookie_is_http_only_and_secure_in_production`     | session cookie is http only and secure in production     |
| `test_production_configuration_rejects_insecure_defaults`       | production configuration rejects insecure defaults       |
| `test_cache_hit_and_database_fallback_both_enforce_owner`       | cache hit and database fallback both enforce owner       |
| `test_update_delete_stats_and_messages_forward_owner`           | update delete stats and messages forward owner           |
| `test_client_cannot_submit_user_id`                             | client cannot submit user id                             |
| `test_expensive_endpoint_returns_real_429`                      | expensive endpoint returns real 429                      |
| `test_bootstrap_is_rate_limited_by_ip`                          | bootstrap is rate limited by ip                          |
| `test_conversation_creation_returns_redacted_503`               | conversation creation returns redacted 503               |
| `test_backend_health_is_degraded_without_postgres`              | backend health is degraded without postgres              |
| `test_stream_rejects_foreign_conversation_before_persistence`   | stream rejects foreign conversation before persistence   |
| `test_public_errors_and_logs_are_redacted`                      | public errors and logs are redacted                      |
| `test_lightrag_provider_logs_are_disabled`                      | lightrag provider logs are disabled                      |
| `test_reassignment_invalidates_cache_and_fails_closed`          | reassignment invalidates cache and fails closed          |

</details>

<details>
<summary>backend/security/test_upload_and_auth.py — 8 escenarios base</summary>

Clave administrativa, firma/MIME/tamaño PDF, rutas confinadas, limpieza, límites exactos y rechazo de sesiones ausentes o alteradas.


| Caso                                                                | Comprobación                                                |
| --------------------------------------------------------------------- | -------------------------------------------------------------- |
| `test_upload_requires_admin_even_with_session`                      | upload requires admin even with session                      |
| `test_invalid_upload_is_rejected_and_cleaned`                       | invalid upload is rejected and cleaned                       |
| `test_upload_is_confined_and_passes_sanitized_metadata`             | upload is confined and passes sanitized metadata             |
| `test_oversized_upload_is_rejected_without_retaining_bytes`         | oversized upload is rejected without retaining bytes         |
| `test_pdf_size_exact_boundary_is_accepted_but_one_byte_more_is_not` | pdf size exact boundary is accepted but one byte more is not |
| `test_tampered_session_cookie_cannot_access_protected_query`        | tampered session cookie cannot access protected query        |
| `test_anonymous_chat_history_must_require_session`                  | anonymous chat history must require session                  |
| `test_anonymous_stream_must_require_session`                        | anonymous stream must require session                        |

</details>

<details>
<summary>backend/security/test_upload_security.py — 7 escenarios base</summary>

Carga administrativa, evidencia por bytes, metadatos saneados, errores del procesador/almacén, colisiones y conservación de archivos existentes.


| Caso                                                                   | Comprobación                                                                                   |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `test_admin_endpoints_disabled_without_key` | Si los endpoints administrativos están deshabilitados y no hay clave configurada, la carga devuelve HTTP 404. |
| `test_upload_generates_confined_name_and_preserves_sanitized_metadata` | Un nombre que intenta salir del directorio (`../../private.pdf`) se reduce a `private.pdf` en los metadatos; el PDF recibe un nombre generado y queda dentro de `raw`, sin crear archivos en el directorio padre. La carga responde HTTP 200, conserva un único registro de evidencia y declara `graph_write_state: unverified`. |
| `test_upload_rejects_size_mime_magic_and_wrong_admin_key` | Un archivo demasiado grande devuelve HTTP 413; MIME incorrecto, firma PDF inválida y clave administrativa incorrecta devuelven 400, 400 y 403, respectivamente. Ningún rechazo deja PDF en `raw` ni registros de evidencia. |
| `test_upload_cleans_up_when_processing_fails` | Una excepción simulada del procesador devuelve HTTP 500 sin revelar el mensaje interno del proveedor; elimina el PDF recibido y no crea registros de evidencia. |
| `test_upload_reuses_evidence_by_pdf_bytes_not_filename` | Dos cargas con los mismos bytes PDF y nombres distintos comparten `evidence_id`. Si cambian los bytes, el ID cambia y quedan exactamente dos registros JSON de evidencia. |
| `test_upload_fails_closed_when_evidence_store_is_unwritable` | Si un archivo ocupa la ruta del directorio de evidencia, la carga devuelve HTTP 500, no conserva PDF ni Markdown y no llama a `rag_engine.add_document`. |
| `test_upload_collision_preserves_existing_markdown_and_evidence` | Una colisión forzada del nombre generado, combinada con una conversión distinta, devuelve HTTP 500 con el mensaje público `PDF processing failed`. Conserva los bytes del Markdown y del registro de evidencia existentes, elimina el nuevo PDF recibido y no inserta contenido en RAG. |

</details>

<details>
<summary>backend/unit/test_anti_hallucination.py — 14 escenarios base</summary>

Patrones legales sospechosos, respuestas vacías/cortas, score RAG, riesgo acotado, penalizaciones y umbrales.


| Caso                                                     | Comprobación                                                             |
| ---------------------------------------------------------- | --------------------------------------------------------------------------- |
| `test_good_response_has_low_risk`                        | Respuesta bien fundamentada no debe superar el umbral de corrección.     |
| `test_hallucinated_response_exceeds_threshold`           | Respuesta con múltiples alucinaciones debe requerir corrección.         |
| `test_returns_hallucination_report_type`                 | El método siempre retorna un HallucinationReport, sin importar el input. |
| `test_empty_response_flagged`                            | Respuesta vacía debe retornar report con requires_correction=True.       |
| `test_very_short_response_flagged`                       | Respuesta de 1 palabra también debe generar report.                      |
| `test_low_rag_score_increases_risk`                      | Mismo texto → mayor riesgo cuando el RAG score es bajo.                  |
| `test_zero_rag_score_has_penalty`                        | RAG score = 0 debe generar la penalización máxima por RAG.              |
| `test_high_rag_score_no_penalty`                         | RAG score ≥ threshold no debe generar penalización RAG.                 |
| `test_individual_patterns_detected`                      | Cada patrón de alucinación debe ser detectado individualmente.          |
| `test_multiple_patterns_accumulate_penalty`              | Múltiples patrones deben acumular penalización hasta el máximo.        |
| `test_long_response_low_rag_triggers_structural_penalty` | Respuesta larga con RAG score bajo → penalización estructural.          |
| `test_long_response_high_rag_no_structural_penalty`      | Respuesta larga con buen RAG score → sin penalización estructural.      |
| `test_risk_score_bounded_0_to_1`                         | El risk_score siempre debe estar en [0, 1].                               |
| `test_custom_threshold_changes_requires_correction`      | Umbral personalizado debe cambiar el criterio de requires_correction.     |

</details>

<details>
<summary>backend/unit/test_audit_remediation.py — 15 escenarios base</summary>

Regresiones de auditoría: traducción completa, fallos sin caché parcial, contratos, dueño, contexto/historial, claves de caché privadas y logs sin PII.


| Caso                                                             | Comprobación                                             |
| ------------------------------------------------------------------ | ----------------------------------------------------------- |
| `test_long_translation_preserves_tail_structure_and_references`  | long translation preserves tail structure and references  |
| `test_translation_rejects_empty_truncated_or_missing_citation`   | translation rejects empty truncated or missing citation   |
| `test_translation_failure_does_not_cache_partial_success`        | translation failure does not cache partial success        |
| `test_missing_provider_is_not_successful_dictionary_translation` | missing provider is not successful dictionary translation |
| `test_input_contract_rejects_blank_or_unknown_language`          | input contract rejects blank or unknown language          |
| `test_foreign_conversation_is_404_before_generation`             | foreign conversation is 404 before generation             |
| `test_storage_failure_is_redacted_503`                           | storage failure is redacted 503                           |
| `test_invalid_query_http_422`                                    | invalid query http 422                                    |
| `test_context_and_history_budgets_are_explicit`                  | context and history budgets are explicit                  |
| `test_cache_is_private_contextual_and_revision_aware`            | cache is private contextual and revision aware            |
| `test_corpus_edit_changes_revision`                              | corpus edit changes revision                              |
| `test_second_turn_context_reaches_prompt_and_owner_check`        | second turn context reaches prompt and owner check        |
| `test_access_log_does_not_keep_oauth_code_or_ip`                 | access log does not keep oauth code or ip                 |
| `test_stream_error_and_logs_do_not_echo_query_or_request_id`     | stream error and logs do not echo query or request id     |
| `test_oauth_failure_is_redacted`                                 | oauth failure is redacted                                 |

</details>

<details>
<summary>backend/unit/test_chat_response_persistence.py — 6 escenarios base</summary>

Extracción por idioma, persistencia de respuestas generadas/cacheadas y fechas UTC aware/naive con offsets positivos y negativos.


| Caso                                                                  | Comprobación                                                  |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `test_conversation_stats_uses_aware_utc_and_accepts_legacy_dates`     | conversation stats uses aware utc and accepts legacy dates     |
| `test_conversation_stats_missing_conversation_does_not_read_messages` | conversation stats missing conversation does not read messages |
| `test_add_message_writes_aware_utc_activity_to_legacy_cache`          | add message writes aware utc activity to legacy cache          |
| `test_extract_response_text_uses_language_safe_fallbacks`             | extract response text uses language safe fallbacks             |
| `test_stream_persists_validated_spanish_response`                     | stream persists validated spanish response                     |
| `test_cached_stream_persists_response_with_same_extractor`            | cached stream persists response with same extractor            |

</details>

<details>
<summary>backend/unit/test_cross_checker.py — 13 escenarios base</summary>

Afirmaciones con soporte, corpus vacío, score de solapamiento, tipos, chunks, caché de tokens e invalidación.


| Caso                                         | Comprobación                                                                  |
| ---------------------------------------------- | -------------------------------------------------------------------------------- |
| `test_grounded_response_passes`              | Respuesta con términos del corpus → overlap alto → is_grounded=True.        |
| `test_hallucinated_response_has_low_overlap` | Respuesta con términos inventados → afirmaciones no fundadas.                |
| `test_empty_response_returns_result`         | Respuesta vacía → CrossCheckResult con is_grounded=False.                    |
| `test_empty_corpus_returns_optimistic`       | Sin documentos en el corpus → is_grounded=True (no podemos evaluar).          |
| `test_returns_cross_check_result_type`       | Siempre debe retornar CrossCheckResult independiente del input.                |
| `test_result_has_supporting_chunks`          | Los supporting_chunks deben provenir del corpus RAG.                           |
| `test_total_claims_count_is_correct`         | El total de afirmaciones debe ser >= grounded + ungrounded.                    |
| `test_ungrounded_claims_are_strings`         | Las afirmaciones no fundadas deben ser strings legibles.                       |
| `test_overlap_score_bounded`                 | El overlap_score siempre debe estar en [0.0, 1.0].                             |
| `test_corpus_cache_reused`                   | Dos llamadas seguidas deben usar el cache de tokens (mismo tamaño de corpus). |
| `test_cache_invalidated_on_update`           | Al actualizar el corpus, el cache de tokens debe invalidarse.                  |
| `test_custom_threshold_strict`               | Threshold alto (0.95) con texto que tiene overlap parcial → not grounded.     |
| `test_custom_threshold_permissive`           | Threshold bajo (0.10) → casi todo es grounded.                                |

</details>

<details>
<summary>backend/unit/test_dependency_compatibility.py — 1 escenarios base</summary>

PDF sintético real con ReportLab, pypdf y backend PDFium de Docling; sin descargar modelos ni ejecutar OCR.


| Caso                                               | Comprobación                               |
| ---------------------------------------------------- | --------------------------------------------- |
| `test_updated_pdf_stack_extracts_synthetic_source` | updated pdf stack extracts synthetic source |

</details>

<details>
<summary>backend/unit/test_dev_server_binding.py — 2 escenarios base</summary>

Launcher local limitado a loopback y guard de importación, manteniendo el arranque independiente del contenedor.


| Caso                                                        | Comprobación                                        |
| ------------------------------------------------------------- | ------------------------------------------------------ |
| `test_local_launcher_binding_and_import_guard`              | local launcher binding and import guard              |
| `test_container_entrypoint_keeps_container_network_binding` | container entrypoint keeps container network binding |

</details>

<details>
<summary>backend/unit/test_file_utils.py — 4 escenarios base</summary>

SHA-256 de bytes completos, lectura por bloques, archivos ausentes y agrupación de duplicados.


| Caso                                                          | Comprobación                                          |
| --------------------------------------------------------------- | -------------------------------------------------------- |
| `test_get_file_hash_returns_sha256_for_complete_content`      | get file hash returns sha256 for complete content      |
| `test_get_file_hash_preserves_empty_result_for_missing_file`  | get file hash preserves empty result for missing file  |
| `test_find_duplicate_files_groups_content_with_sha256_keys`   | find duplicate files groups content with sha256 keys   |
| `test_find_duplicate_files_returns_empty_for_empty_directory` | find duplicate files returns empty for empty directory |

</details>

<details>
<summary>backend/unit/test_llm_optimizer.py — 24 escenarios base</summary>

Caché, TTL/invalidation, compresión de prompts, estimación/contabilidad de tokens y estadísticas.


| Caso                                            | Comprobación                                                            |
| ------------------------------------------------- | -------------------------------------------------------------------------- |
| `test_cache_hit_returns_same_response`          | Mismo prompt → cache hit devuelve la respuesta guardada.                |
| `test_cache_miss_returns_none`                  | Prompt no guardado → cache miss devuelve None.                          |
| `test_different_prompts_independent_keys`       | Prompts distintos deben tener claves independientes.                     |
| `test_cache_expiry_after_ttl`                   | Entradas expiradas (TTL vencido) deben retornar None.                    |
| `test_cache_valid_within_ttl`                   | Entradas dentro del TTL deben seguir disponibles.                        |
| `test_eviction_at_max_size`                     | Al superar max_cache_size, la entrada más antigua debe ser eviccionada. |
| `test_invalidate_specific_key`                  | Invalidar una clave específica no debe afectar las demás.              |
| `test_invalidate_nonexistent_key_returns_false` | Invalidar clave inexistente retorna False (sin error).                   |
| `test_clear_cache_removes_all`                  | clear_cache() debe eliminar todas las entradas.                          |
| `test_short_prompt_not_compressed`              | Prompt corto no debe modificarse.                                        |
| `test_long_prompt_compressed`                   | Prompt largo debe comprimirse a max_chars aproximado.                    |
| `test_center_cut_preserves_marker`              | center_cut debe incluir el marcador de truncamiento.                     |
| `test_tail_cut_preserves_beginning`             | tail_cut debe preservar el inicio del prompt.                            |
| `test_compressed_result_fits_limit`             | El resultado comprimido no debe superar max_chars + marcador.            |
| `test_estimate_tokens_basic`                    | 4 chars ≈ 1 token.                                                      |
| `test_estimate_tokens_empty_string`             | String vacío → mínimo 1 token.                                        |
| `test_track_accumulates_usage`                  | Múltiples llamadas a track() deben acumular el total de tokens.         |
| `test_track_returns_call_metrics`               | track() debe retornar métricas de esa llamada específica.              |
| `test_reset_stats_clears_counters`              | reset_stats() debe poner todos los contadores a cero.                    |
| `test_cache_hit_increments_counter`             | Un cache hit debe incrementar el contador de cache_hits.                 |
| `test_cache_hit_rate_calculation`               | cache_hit_rate debe calcularse correctamente.                            |
| `test_update_accumulates_tokens`                | update accumulates tokens                                                |
| `test_estimated_cost_positive`                  | estimated cost positive                                                  |
| `test_to_dict_has_required_keys`                | to dict has required keys                                                |

</details>

<details>
<summary>backend/unit/test_pipeline_remediation.py — 14 escenarios base</summary>

Recuperación sin corte en 50 candidatos, chunks reales, ausencia de evidencia, ciclo de vida/ready/reintentos/cierre y salidas JSON/stream coherentes.


| Caso                                                                | Comprobación                                                |
| --------------------------------------------------------------------- | -------------------------------------------------------------- |
| `test_candidate_after_first_fifty_is_found_and_order_independent`   | candidate after first fifty is found and order independent   |
| `test_nonmatching_corpus_is_not_presented_as_evidence`              | nonmatching corpus is not presented as evidence              |
| `test_native_graph_candidates_are_real_chunks_not_generated_answer` | native graph candidates are real chunks not generated answer |
| `test_loader_retries_failure_without_false_ready`                   | loader retries failure without false ready                   |
| `test_lifespan_loads_once_and_finalizes`                            | lifespan loads once and finalizes                            |
| `test_shutdown_cancels_loading_and_closes_on_error`                 | shutdown cancels loading and closes on error                 |
| `test_readiness_and_first_query_fail_closed`                        | readiness and first query fail closed                        |
| `test_query_and_stream_return_same_validated_content`               | query and stream return same validated content               |
| `test_chat_uses_same_validator_before_assistant_persistence`        | chat uses same validator before assistant persistence        |
| `test_chat_provider_error_never_persists_fake_assistant`            | chat provider error never persists fake assistant            |
| `test_no_evidence_abstains_even_if_self_correction_invents`         | no evidence abstains even if self correction invents         |
| `test_provider_failure_is_redacted_not_success`                     | provider failure is redacted not success                     |
| `test_translation_provider_exception_does_not_leak_payload`         | translation provider exception does not leak payload         |
| `test_deepeval4_native_score_direction_without_judge`               | deepeval4 native score direction without judge               |

</details>

<details>
<summary>backend/unit/test_rag_fallback.py — 7 escenarios base</summary>

Fallback local ante falta/fallo de LightRAG o reranking; fuente explícita, corpus vacío, chunking por longitud y scores locales.


| Caso                                                        | Comprobación                                        |
| ------------------------------------------------------------- | ------------------------------------------------------ |
| `test_keyword_fallback_reports_matching_source`             | keyword fallback reports matching source             |
| `test_keyword_fallback_no_match_is_explicit`                | keyword fallback no match is explicit                |
| `test_local_rerank_returns_chunk_shape`                     | local rerank returns chunk shape                     |
| `test_chunking_is_sentence_length_based_not_hierarchical`   | chunking is sentence length based not hierarchical   |
| `test_empty_corpus_has_distinct_query_and_rerank_fallbacks` | empty corpus has distinct query and rerank fallbacks |
| `test_failed_lightrag_insert_still_stores_local_document`   | failed lightrag insert still stores local document   |
| `test_failed_cohere_rerank_uses_local_scores`               | failed cohere rerank uses local scores               |

</details>

<details>
<summary>backend/unit/test_self_correction.py — 8 escenarios base</summary>

Corrección simulada, condición de activación, tipos, respuesta vacía, errores Cohere y máximo de reintentos.


| Caso                                       | Comprobación                                                                    |
| -------------------------------------------- | ---------------------------------------------------------------------------------- |
| `test_no_correction_when_not_required`     | Cuando requires_correction=False, el engine retorna el original sin cambios.     |
| `test_correction_applied_when_required`    | Cuando requires_correction=True, se llama a Cohere y se retorna texto corregido. |
| `test_corrected_text_not_empty`            | El texto corregido nunca debe estar vacío.                                      |
| `test_returns_tuple_of_str_and_int`        | Siempre debe retornar (str, int) independiente del resultado.                    |
| `test_no_cohere_returns_original`          | Sin cliente Cohere, debe retornar el original sin lanzar excepción.             |
| `test_cohere_error_returns_original`       | Si Cohere lanza excepción, debe retornar el original sin propagar el error.     |
| `test_empty_cohere_response_uses_original` | Si Cohere retorna texto vacío, debe usar el original.                           |
| `test_max_retries_respected`               | El engine no debe llamar a Cohere más de max_retries veces.                     |

</details>

<details>
<summary>backend/unit/test_source_evidence.py — 10 escenarios base</summary>

Identidad SHA-256, UTF-8 exacto, reintentos/tampering, consistencia carga/lote, fallos cerrados, colisiones y detección de caracteres de reemplazo.


| Caso                                                                        | Comprobación                                                                                                                      |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `test_processing_validation_preserves_replacement_character_detection` | Parametriza Markdown válido en español con emojis, con y sin el carácter de reemplazo U+FFFD. Solo la variante con ese carácter informa `Caracteres de codificación detectados` y reduce la confianza de 1.0 a 0.8; el escape Unicode conserva la detección sin rechazar texto válido. |
| `test_pipeline_source_has_valid_utf8_without_literal_replacement_character` | Decodifica estrictamente como UTF-8 los bytes de `backend/ingestion/pipeline.py` y comprueba que no contengan un U+FFFD literal; el detector debe usar el escape sin introducir un carácter de corrupción en el código fuente. No ejecuta el scanner Sonar. |
| `test_evidence_retries_and_tampering` | Reintentos con los mismos PDF y Markdown reutilizan el registro JSON. La instancia de evidencia no permite reasignar atributos y mantiene `provenance_state: unverified`; una conversión distinta del mismo PDF produce un conflicto y un registro alterado se rechaza. No quedan archivos temporales `.evidence-*`. La instancia congelada no vuelve inmutable el archivo JSON en disco. |
| `test_evidence_requires_written_matching_markdown` | Si el Markdown todavía no existe en disco, se produce `FileNotFoundError`. Si sus bytes no corresponden a la conversión recibida, se produce `ValueError`; ninguno de los dos errores crea el almacén de evidencia. |
| `test_evidence_hashes_exact_multiline_utf8_bytes` | El SHA-256 registrado del Markdown coincide exactamente con sus bytes UTF-8 persistidos, incluidos el carácter acentuado de `Artículo` y el salto de línea final. |
| `test_batch_matches_upload_identity_and_keeps_legacy_result` | La carga HTTP y el procesamiento por lotes comparten un ID de evidencia para PDF con los mismos bytes aunque sus nombres sean distintos. El lote informa un procesado y cero fallidos, estado `success`, ruta Markdown dentro de la categoría y `graph_write_state: unverified`; llama una sola vez a inserción y reconstrucción de RAG y conserva un único registro JSON. |
| `test_batch_fails_closed_on_markdown_or_evidence_failure` | Bloquear con un archivo la ruta del directorio de procesados o del almacén de evidencia provoca un error del sistema de archivos antes de insertar en RAG. El lote informa cero procesados y un fallo, mueve el PDF a `failed` y no llama a `add_document` ni a `rebuild_index`. |
| `test_batch_divergent_retry_preserves_existing_markdown_and_evidence` | Tras un primer lote exitoso, un reintento que convierte el mismo PDF a otro Markdown falla y mueve el PDF original a `failed`. Conserva intactos los bytes del primer Markdown y su evidencia; la inserción y reconstrucción de RAG solo se realizaron durante el primer lote. |
| `test_batch_retry_with_processor_output_alias_preserves_original` | Aunque el directorio de salida del procesador sea el mismo directorio de procesados del lote, una conversión diferente en el reintento no sobrescribe el Markdown ni su evidencia. Informa el conflicto `Existing Markdown differs`, mueve el PDF a `failed`, conserva un solo registro JSON y no ejecuta una segunda inserción ni reconstrucción de RAG. |
| `test_standalone_processor_still_writes_output_by_default` | El uso directo de `LegalPDFProcessor.process_pdf`, con un convertidor simulado, devuelve el Markdown convertido y escribe por defecto `source.md` con ese mismo contenido. El cambio de publicación controlada en las rutas de ingesta no elimina este comportamiento independiente. |

</details>

<details>
<summary>backend/unit/test_startup_safety.py — 2 escenarios base</summary>

Neo4j desactivado selecciona NetworkX sin importarlo y salida de consola tolera caracteres no codificables.


| Caso                                                           | Comprobación                                           |
| ---------------------------------------------------------------- | --------------------------------------------------------- |
| `test_disabled_neo4j_selects_networkx_without_importing_neo4j` | disabled neo4j selects networkx without importing neo4j |
| `test_console_output_replaces_unencodable_characters`          | console output replaces unencodable characters          |

</details>

<details>
<summary>backend/unit/test_utc_datetimes.py — 5 escenarios base, 9 casos parametrizados</summary>

Fechas UTC explícitas sin depender de la zona horaria del equipo. No requiere Redis real ni llamadas a modelos.

| Caso | Qué verifica |
|---|---|
| `test_rate_limit_scores_use_real_epoch_in_any_host_timezone` | Scores, ventana y reset de Redis usan el epoch correcto bajo zonas simuladas UTC−5, UTC y UTC+5:30. |
| `test_redis_health_reports_explicit_utc_in_success_and_failure` | Timestamp UTC en éxito y fallos de ping/info, sin mezclar fechas aware/naive al medir la duración. |
| `test_validation_report_default_is_fresh_utc_for_each_instance` | Cada reporte genera su propia fecha UTC y la conserva al serializar a JSON. |
| `test_file_modification_time_is_serialized_as_utc` | El mtime del archivo se convierte a ISO 8601 con zona UTC explícita. |
| `test_backend_does_not_use_naive_utc_factories_or_timestamp_conversions` | Guard AST contra utcnow/utcfromtimestamp y fromtimestamp sin zona en código backend. |

</details>

### Frontend

<details>
<summary>frontend/component/AuthProvider.test.tsx — 3 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `provider restaura usuario por cookies y limpia flag sin guardar tokens` | Restaura estado desde cookie y retira flag de login, sin persistir tokens. |
| `provider sesión simulada ausente mantiene estado anónimo sin fallar render` | Ausencia de sesión conserva UI anónima sin fallar el montaje. |
| `provider desmontado con sesión simulada elimina suscripción y listener storage` | Desmontaje retira suscripción y listener storage para evitar revalidaciones tardías. |

</details>

<details>
<summary>frontend/component/ChatInput.test.tsx — 5 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `entrada no envía espacios y Enter recorta texto mientras Shift Enter crea línea` | No envía espacios; Shift+Enter introduce línea y Enter envía texto recortado. |
| `entrada limita 800 caracteres y muestra contador sin truncar silenciosamente` | Acepta 800 caracteres, contador cero y rechaza la entrada adicional. |
| `entrada no autenticada redirige sin enviar ni perder texto` | Sin autenticación navega a login sin enviar ni borrar la consulta escrita. |
| `entrada quechua selecciona ejemplo y enfoca sin enviar automáticamente` | Ejemplo quechua rellena y enfoca sin generar una consulta automática. |
| `entrada en carga bloquea cambios y permite abortar sin limpiar` | Carga bloquea input/limpieza y permite detener con callback de abort. |

</details>

<details>
<summary>frontend/component/ChatMessage.test.tsx — 3 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `mensaje de error es visible y no presenta una validación exitosa` | Error muestra fallo sin badge Validado. |
| `mensaje presenta validación advertencias y detalles sin inventar fuentes` | Badge warned y detalles muestran fuentes suministradas; no inventan evidencia. |
| `mensaje descarga solo al solicitarlo y bloquea botón durante generación` | Descarga solo por acción del usuario y deshabilita botón mientras genera PDF. |

</details>

<details>
<summary>frontend/component/ChatSidebar.test.tsx — 3 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `sidebar reintento muestra error y respeta bloqueo durante carga` | Error muestra reintento; durante carga el botón está deshabilitado. |
| `sidebar ordenar sesiones no muta datos y selección cierra panel` | Ordena por actividad sin mutar el array original; seleccionar también cierra el panel. |
| `sidebar borrar exige confirmar y cancelar no elimina ni selecciona` | Cancelar no elimina; solo confirmación elimina y no selecciona accidentalmente la fila. |

</details>

<details>
<summary>frontend/component/HistoryPanel.test.tsx — 3 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `historial cerrado no aparece y lista vacía tiene mensaje` | Cerrado no se renderiza y vacío muestra un mensaje explícito. |
| `historial selecciona por teclado y borrar no selecciona accidentalmente` | Enter selecciona el ID correcto; eliminar llama solo a borrado, sin burbujear selección. |
| `historial permite cerrar con botón y Escape` | Botón con nombre accesible y Escape notifican el cierre. |

</details>

<details>
<summary>frontend/component/MarkdownRenderer.test.tsx — 3 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `Markdown renderiza listas tablas enlaces y Unicode sin perder contenido` | Renderiza encabezado, lista, tabla GFM y Unicode; enlaces nuevos protegen opener/referrer. |
| `Markdown no ejecuta HTML scripts ni enlaces javascript del modelo` | Contenido del modelo no crea script/onerror ni enlace javascript ejecutable. |
| `Markdown tolera contenido vacío e incompleto durante streaming` | Contenido vacío o Markdown parcial en streaming no rompe el render. |

</details>

<details>
<summary>frontend/component/TerminalModal.test.tsx — 4 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `terminal cerrado no renderiza y abierto enfoca la entrada` | Cerrado no contiene entrada; al abrir enfoca el textbox. |
| `terminal envía texto recortado por Enter y no envía espacios` | Enter no envía espacios, recorta texto válido y limpia la entrada tras enviar. |
| `terminal cargando bloquea envío y representa mensajes y estado` | Carga bloquea el input y muestra mensajes como texto seguro e indicador de procesamiento. |
| `terminal Escape y cerrar notifican cierre y devuelven foco` | Escape y botón cierran el diálogo; el ciclo de apertura/cierre restaura foco. |

</details>

<details>
<summary>frontend/e2e/chat-persistence.spec.js — 5 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `interfaz actual envía consulta y conserva respuesta al recargar` | Chromium + API sintética: consulta/final, refresh a landing y selección restaura respuesta persistida. |
| `interfaz recupera listado después de caída temporal simulada` | Abort de primer listado produce alerta y reintento recupera historial. |
| `nueva consulta móvil no muestra mensajes de sesión anterior` | Viewport móvil: tras nueva sesión no se muestran mensajes de la anterior en el terminal. |
| `terminal accesible permite teclado Escape y devuelve foco` | Diálogo recibe foco, permite teclado y Escape lo cierra. |
| `pantalla y terminal no tienen violaciones axe serias o críticas` | Axe analiza landing y diálogo; cero impactos serious/critical, no certifica accesibilidad completa. |

</details>

<details>
<summary>frontend/e2e/chat.real.spec.js — 3 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `servicios reales recuperan historial después de caída temporal` | Con flag y servicios locales, interrupción temporal de listado se recupera al reintentar. |
| `consulta real sintética persiste al recargar y se limpia al terminar` | Una consulta sintética comprueba final no vacío y persistencia tras refresh; limpia solo su conversación. |
| `servicios reales aíslan principales anónimos en dos contextos` | Dos contextos tienen principales/cookies aislados; otro usuario recibe404 al leer la conversación ajena. |

</details>

<details>
<summary>frontend/integration/ChatPage.test.tsx — 3 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `pantalla principal crea sesión antes de enviar y muestra respuesta final` | Monta pantalla/hooks/API real del frontend con red MSW: crea sesión antes de consultar y muestra final. |
| `nueva sesión no conserva mensajes del terminal anterior` | Nueva sesión limpia mensajes del terminal anterior, sin confundir el preview persistido del sidebar. |
| `pantalla recupera historial tras fallo con reintento sin borrar datos` | API de listado 503 expone acción de reintento y al recuperarse elimina el alert. |

</details>

<details>
<summary>frontend/integration/useChat.test.tsx — 14 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `NDJSON fragmentado por byte conserva Unicode y usa respuesta final española` | NDJSON por byte conserva ñ/emoji y final reemplaza parcial; sidebar recibe título y conteo. |
| `final quechua selecciona idioma y transmite conversation_id con cookies` | Selecciona respuesta quechua; petición usa cookies, idioma e ID de conversación correctos. |
| `stream sin final vacíos y varios eventos conserva texto parcial` | Sin final conserva chunks UTF-8, ignora delta vacío y termina indicador streaming. |
| `evento de error y JSON malformado terminan carga sin éxito falso` | Evento error y JSON roto liberan loading sin fabricar payload exitoso. |
| `HTTP no exitoso y cuerpo ausente terminan con error recuperable` | HTTP 503 y cuerpo ausente producen respuesta recuperable, no éxito falso. |
| `envíos vacíos sin sesión y simultáneos no duplican solicitudes` | Espacios, sesión nula y dos envíos del mismo tick no generan solicitudes duplicadas. |
| `abort conserva respuesta parcial y libera bloqueo de envío` | Abort conserva parcial y libera el bloqueo; stream controlado, sin temporizadores del proveedor. |
| `carga antigua no reemplaza mensajes de la sesión nueva` | Carga antigua que responde después de B no reemplaza los mensajes de B. |
| `cambio de sesión cancela stream y no actualiza metadatos antiguos` | Cambiar sesión aborta y descarta final/metadata tardíos de la conversación anterior. |
| `desmontaje cancela stream sin notificar metadatos tardíos` | Desmontaje aborta y no notifica metadata tras resolver un fetch tardío. |
| `limpiar aborta y una carga tardía no repuebla la conversación` | Limpiar invalida carga pendiente, que no vuelve a poblar mensajes antiguos. |
| `health distingue saludable degradado y fallo de red` | Health healthy=true; degraded y fallo de red=false. |
| `PDF válido descarga blob y revoca URL incluso si click falla` | PDF crea URL Blob y siempre la revoca, incluso si el click de descarga falla. |
| `PDF ausente MIME inválido y fallo de red no descargan ni dejan carga` | Sin payload o con MIME inválido no descarga; termina el indicador de generación. |

</details>

<details>
<summary>frontend/integration/useChatSessions.test.tsx — 8 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `montaje carga historial sin borrar ni seleccionar una sesión automáticamente` | Montaje carga listado sin borrar ni seleccionar automáticamente la sesión activa. |
| `creación reutiliza consulta vacía y respeta idioma de una nueva` | Nueva consulta transmite idioma y una consulta vacía existente evita POST repetido. |
| `creación fallida no añade una sesión fantasma` | Creación fallida rechaza y no añade una conversación inexistente. |
| `reload fallido conserva historial y reintento recupera la lista` | Reload fallido conserva listado; un reintento exitoso retira el error. |
| `bootstrap fallido muestra error y no solicita historial` | Bootstrap fallido muestra error y evita pedir conversaciones. |
| `borrado fallido conserva sesión activa y borrado exitoso la elimina` | Borrado fallido conserva sesión activa; éxito elimina y deja active=null si era la última. |
| `metadatos locales y payload backend conservan preview conteo y título` | Patch local conserva título/preview/count y PUT lleva los mismos metadatos. |
| `reload antiguo no reemplaza una respuesta nueva` | Dos reloads con respuestas fuera de orden conservan la respuesta más reciente. |

</details>

<details>
<summary>frontend/unit/apiService.test.ts — 5 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `bootstrap concurrente comparte una solicitud y todas incluyen cookies` | Dos llamadas simultáneas comparten bootstrap; bootstrap y petición protegida incluyen cookies. |
| `bootstrap fallido se puede reintentar sin llamar al endpoint protegido` | Un bootstrap 503 no llama al endpoint protegido y la siguiente llamada puede recuperarse. |
| `API conserva detalle HTTP y tolera respuestas de error no JSON` | Conserva detail de un error JSON y usa HTTP/status cuando el error no es JSON. |
| `API JSON inválido y desconexión no producen un éxito falso` | JSON roto y desconexión devuelven success=false, nunca datos aprobados. |
| `API serializa idioma título y metadatos y codifica búsquedas` | Comprueba POST de idioma/título, PUT de metadata y codificación de ñ y & en búsquedas. |

</details>

<details>
<summary>frontend/unit/authService.test.ts — 7 escenarios</summary>

| Caso | Qué verifica |
|---|---|
| `login por cookie actualiza estado sin persistir tokens` | Login por formulario seguido de /auth/me marca autenticación sin escribir tokens en localStorage. |
| `usuario se recupera desde cookies tras nueva instancia sin token JS` | Una instancia sin token JavaScript restaura al usuario mediante cookies en /auth/me y notifica una vez a sus suscriptores. |
| `login inválido no autentica y conserva mensaje de error` | 401 conserva el mensaje y deja al usuario no autenticado. |
| `logout limpia estado y notifica aunque la red falle` | Logout limpia usuario/tokens incluso sin red; desuscribir impide notificaciones posteriores. |
| `401 refresca cookie una vez y reintenta conservando opciones` | Tras 401 hace exactamente un refresh y reenvía método/cuerpo de la solicitud. |
| `401 persistente no causa bucle de refresh y termina sesión` | Si el reintento sigue en 401, termina sesión sin renovación recursiva ilimitada. |
| `refresh fallido cierra sesión sin filtrar credenciales` | Refresh rechazado termina sesión con error controlado, sin exponer credenciales. |

</details>

<details>
<summary>frontend/unit/chatSessionMeta.test.mts — 2 escenarios base</summary>

Conversión de metadatos preserva message_count y usa cero si falta.


| Caso                                                            | Comprobación                                                        |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `preserves the API message count when mapping session metadata` | Conversión de metadatos preserva message_count y usa cero si falta. |
| `treats a missing API message count as an empty session`        | Conversión de metadatos preserva message_count y usa cero si falta. |

</details>

<details>
<summary>frontend/unit/useChatSessions.test.mts — 2 escenarios base</summary>

Hidratación sin borrar conversación ni sendBeacon; un fallo preserva sesiones y el reintento las reemplaza.


| Caso                                                                          | Comprobación                                                                                                 |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `initial session hydration has no clear-session call or unload beacon`        | Hidratación sin borrar conversación ni sendBeacon; un fallo preserva sesiones y el reintento las reemplaza. |
| `a failed session load preserves existing sessions and a retry replaces them` | Hidratación sin borrar conversación ni sendBeacon; un fallo preserva sesiones y el reintento las reemplaza. |

</details>

### Scripts y estructura

<details>
<summary>scripts/unit/dev-full.test.mjs — 8 escenarios base</summary>

Arranque Docker solo PostgreSQL/Redis, healthchecks, argumentos seguros en Windows, npm_execpath y espera del backend antes del frontend.


| Caso                                                               | Comprobación                                                                                                                             |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `development startup targets only PostgreSQL and Redis`            | Arranque Docker solo PostgreSQL/Redis, healthchecks, argumentos seguros en Windows, npm_execpath y espera del backend antes del frontend. |
| `host processes require running containers with healthy checks`    | Arranque Docker solo PostgreSQL/Redis, healthchecks, argumentos seguros en Windows, npm_execpath y espera del backend antes del frontend. |
| `Windows launches pnpm concurrently with an argument vector`       | Arranque Docker solo PostgreSQL/Redis, healthchecks, argumentos seguros en Windows, npm_execpath y espera del backend antes del frontend. |
| `Windows executes standalone pnpm without passing an exe to Node`  | Arranque Docker solo PostgreSQL/Redis, healthchecks, argumentos seguros en Windows, npm_execpath y espera del backend antes del frontend. |
| `Windows requires pnpm's entrypoint`                               | Arranque Docker solo PostgreSQL/Redis, healthchecks, argumentos seguros en Windows, npm_execpath y espera del backend antes del frontend. |
| `pnpm supplies the Windows launcher entrypoint to package scripts` | Arranque Docker solo PostgreSQL/Redis, healthchecks, argumentos seguros en Windows, npm_execpath y espera del backend antes del frontend. |
| `backend health retries transient failures until it succeeds`      | Arranque Docker solo PostgreSQL/Redis, healthchecks, argumentos seguros en Windows, npm_execpath y espera del backend antes del frontend. |
| `frontend is not started until backend health succeeds`            | Arranque Docker solo PostgreSQL/Redis, healthchecks, argumentos seguros en Windows, npm_execpath y espera del backend antes del frontend. |

</details>

<details>
<summary>scripts/unit/run-tests.test.mjs — 13 escenarios base</summary>

Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner.


| Caso                                                                                      | Comprobación                                                                                                                                         |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `offline incluye Python y Node sin activar modelos reales`                                | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `todos los modos Python usan configuración raíz y las suites Node viven en tests`       | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `all incluye evaluación real y continúa con Node`                                       | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `coverage produce Cobertura y xUnit compatible sin activar modelos reales`                | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `quality selecciona solo las pruebas del modelo y reenvía opciones`                      | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `quality-offline y modos inválidos no activan facturación`                              | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `fallos de una suite no ocultan las restantes y mantienen exit code`                      | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `error de arranque falla la ejecución y éxito retorna cero`                             | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `sonar lee SONAR_TOKEN de backend/.env con BOM, comillas y CRLF sin cargar otras claves`  | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `sonar permite SONAR_TOKEN del entorno para CI sin leer archivos`                         | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `sonar diagnostica archivo ausente, vacío, token MCP y multilínea sin revelar secretos` | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `sonar entrega el token del archivo solo al scanner, no a tests ni argumentos`            | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |
| `sonar ejecuta scanner solo después de todas las suites exitosas`                        | Selección de suites/modos, carpeta/configuración únicas, cobertura/xUnit, propagación de fallos y token Sonar desde backend/.env solo al scanner. |

</details>

<details>
<summary>scripts/unit/test_repository_layout.py — 4 escenarios base</summary>

Exigir componente y tipo dentro del árbol único, impedir suites dispersas y mantener catálogo por caso, configuración, dataset y manuales.


| Caso                                                         | Comprobación                                                               |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `test_test_suites_are_confined_to_single_tree`               | Exigir `tests/<backend|frontend|scripts>/<tipo>/` y no permitir suites Python/Node/Playwright en código de producto o scripts; frontend usa `.test.mts` y scripts `.test.mjs`. |
| `test_every_automated_case_is_catalogued_in_test_guide`      | Cada archivo y nombre de caso debe constar en el documento dedicado.        |
| `test_pytest_and_sonar_share_the_same_test_root`             | Pytest y Sonar reconocen tests y no conservan una segunda configuración.   |
| `test_manual_diagnostics_and_quality_dataset_are_documented` | Inventariar scripts manuales y mantener datos sintéticos dentro de tests.  |

</details>

## Evidencia histórica de la primera ampliación frontend — 06/10/2026

Vitest 5.0.3 / cobertura V8 5.0.3, jsdom 29.1.1 (Node local 24.13.1),
Testing Library React 16.3.3 y MSW 2.15.0. MSW 3 no satisface el peer del mocker
de Vitest; jsdom 30 requiere Node24.15+, por eso no se instalan esas versiones.
React de tests coincide en versión con producto y usa una instancia única;
Lucide usa su entrada ESM para respetar aliases. No se cambia el tipo global
del frontend ni sus configs CommonJS. Los cuatro casos antiguos se conservan.

Unidades de trabajo/rollback (sin commits creados):
1. Infraestructura y runner: configs/fixtures/tests de runner/package/locks/Sonar.
2. Regresiones de hooks/auth: fuentes y sus unit/integration tests juntos.
3. UI/accesibilidad: componentes y pruebas React/navegador juntas.
4. Esta guía y evidencia local de ejecución. No revertir cambios ajenos.

Verificación de la ampliación (los resultados históricos anteriores no cuentan
las suites nuevas):

| Comprobación | Resultado |
|---|---|
| Suite completa / cobertura | 238 Python aprobados, 3 modelos omitidos y 2 xfail estrictos; 23 scripts Node y 65 casos React aprobados |
| Navegador API simulada | 5/5 aprobados en Edge headless; incluye móvil, persistencia, reintento, Tab/Escape/foco y axe sin violaciones serias/críticas en landing/terminal |
| Solo evaluador offline | 24 aprobados; ningún proveedor llamado |
| TypeScript y build de Next | Aprobados |
| Locks | Instalación pnpm congelada y `pnpm deps:check` aprobados |
| Confirmación real | quality/e2e-real sin flag: exit 2 antes del spawn; discovery real con flag: 3 casos, sin ejecutarlos |
| Informes finales | 243 casos xUnit y 70 módulos Cobertura; 32 archivos frontend en LCOV, todas las rutas existentes y cero fallos/errores xUnit |

La cobertura frontend incluye archivos no ejercitados: **41.64 % de líneas**
y **43.70 % de ramas**, no 80 % ni una garantía del Quality Gate. Los E2E con API simulada
no prueban backend/modelo ni se suman al LCOV de Vitest. No se ejecutaron los
casos facturables al implementar estas pruebas. La descarga de Chromium encontró
un bloqueo externo de caché; se verificó con el canal `msedge`, sin borrarlo.
Evidencia local ignorada por Git: `temp/sonar-reports/` (logs, XML y LCOV).

### Regresiones adicionales del runner

En `scripts/unit/run-tests.test.mjs`:

| Caso | Qué verifica |
|---|---|
| `modelos reales requieren flag explícito y frontend offline nunca lo hereda` | quality/real rechazan ausencia de flag antes del spawn; all por defecto offline; E2E simulado/React fuerzan RUN_MODEL_EVALS=0. |
| `coverage frontend usa LCOV separado y conserva opciones Vitest` | Modo cobertura frontend añade --coverage, modo normal no; ambos usan config explícita y preservan opciones del usuario. |

## Ampliación transversal — v8, 2026-10-06

Cobertura de código no equivale a calidad RAG. Los unitarios de chunking verifican
estructura, orden, metadatos y errores con documentos sintéticos y embeddings simulados.
Para comparar calidad semántica se requiere un dataset con referencias y un benchmark
del retrieval (p. ej. [RAGAS Context Precision/Recall](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/)).
Los casos actuales de calidad real evalúan el generador con DeepEval;
**no son una evaluación RAGAS comparativa del chunker**. No se ejecutaron proveedores
en esta ampliación.

Las nuevas pruebas conservan fuentes y exclusiones de cobertura. PDF usa
ReportLab/pypdf reales, canvas simula frames/2D, hooks usan API simulada y SQL
prueba el adaptador real con cursor simulado. No acreditan rendering físico,
PostgreSQL remoto ni calidad jurídica. Las tablas siguientes explican las
comprobaciones concretas; los casos parametrizados ejecutan varias variantes
bajo un mismo nombre (`%s` identifica la variante en los tests frontend).


### `backend/unit/test_pdf_generator.py`

**Objetivo:** generar PDFs reales con contenido sintético y volver a leerlos con
pypdf para detectar pérdida de contenido y errores de formato. No se invoca al
modelo ni se evalúa la calidad de la traducción; los textos de ambos idiomas
ya vienen suministrados en el fixture.

| Caso | Qué comprueba |
|---|---|
| `test_real_pdf_preserves_bilingual_content_and_report_sections` | Genera el PDF tanto desde respuesta directa como desde payload anidado; al extraer el texto conserva consulta, español/quechua, pasos, documentos, recursos, advertencias, fuentes y aviso. Comprueba el tema del payload anidado y que no se modifique la respuesta original. |
| `test_pdf_markdown_renders_structural_blocks_and_escapes_markup` | Comprueba flowables de títulos, tablas, código y separadores, y su contenido en un PDF real con citas/listas/enlaces/imágenes. Verifica que `x < y` no termine doblemente escapado y que etiquetas HTML de entrada se escapen. |
| `test_pdf_accepts_empty_or_legacy_payload_without_crashing` | Prueba respuesta vacía, metadatos nulos, formato anidado vacío y `None`; el PDF sigue siendo legible, incluye encabezado de consulta y tema general, y omite la sección de respuesta inexistente. |
| `test_pdf_file_output_is_unique_and_confined_to_requested_directory` | Genera dos informes en un directorio temporal nuevo; comprueba nombres distintos, ubicación en el directorio solicitado y contenido correspondiente a cada consulta. |
| `test_invalid_markdown_table_is_not_rendered_as_table` | Comprueba que filas ausentes, una sola fila o separadores inválidos devuelvan `None` en el parser de tabla, en lugar de construir una tabla inválida. |


### `backend/unit/test_chunking_strategies.py`

**Objetivo:** verificar invariantes del chunker sobre documentos sintéticos:
estructura, contenido, orden y metadatos. Las respuestas de embeddings se
simulan; estos tests **no miden calidad semántica ni sustituyen un benchmark RAGAS**.

| Caso | Qué comprueba |
|---|---|
| `test_legal_chunking_detects_structure_and_preserves_order` | Detecta código, demanda, manual y texto general; valida posiciones, IDs secuenciales, contenido tomado del documento y recuento de palabras. En los formatos estructurados comprueba números de artículo, niveles de título y campos de formulario. |
| `test_chunking_falls_back_to_paragraphs_and_skips_empty_content` | Con tipos en mayúsculas verifica que texto vacío produzca cero chunks y que un documento sin la estructura esperada use párrafos como fallback, conservando dos párrafos de 700 caracteres en orden. |
| `test_chunk_metadata_records_theme_urgency_and_cultural_indicators` | Con frases controladas comprueba las etiquetas de urgencia alta/media/baja; verifica tema y entidad de violencia, detección de término quechua y puntuaciones culturales nulas cuando no hay indicadores. No acredita precisión del clasificador con textos reales. |
| `test_contextual_chunker_attaches_document_metadata_and_computes_stats` | Comprueba que los chunks conserven metadatos del documento y que estadísticas de cantidad, palabras, promedio, tipos y temas correspondan a sus contenidos; incluye el resultado del conjunto vacío. |
| `test_embeddings_are_batched_and_provider_failure_preserves_chunks` | Simula proveedor ausente, exitoso y fallido. En éxito comprueba lotes de 2+1, `input_type=search_document` y asignación de vectores a cada chunk; sin proveedor o con fallo preserva los chunks sin embeddings inventados. |
| `test_document_processing_propagates_failure_without_partial_result` | Provoca un error en la estrategia de fragmentación y comprueba que `process_document` propague la excepción, sin devolver un resultado parcial como si hubiera funcionado. |


### `backend/unit/test_settings_contract.py`

**Objetivo:** comprobar las reglas de Settings con valores sintéticos, sin leer
el archivo `.env` ni crear directorios. Validar configuración no demuestra que
un despliegue real aplique correctamente todos sus controles.

| Caso | Qué comprueba |
|---|---|
| `test_default_app_identity_is_branch_not_invented_release` | Comprueba que el valor predeterminado declarado de `APP_VERSION` sea `v8`, sin identificarlo con las versiones semánticas de los paquetes. |
| `test_production_rejects_insecure_or_incomplete_settings` | En siete variantes comprueba rechazo y diagnóstico correspondiente: secreto anónimo corto, orígenes CORS wildcard, métodos CORS wildcard, límites en memoria, administración sin clave, SameSite inválido y Cohere sin clave. |
| `test_production_config_preserves_secure_cookies_and_hides_docs_by_default` | Con configuración válida comprueba validación exitosa, cookie anónima Secure y documentación deshabilitada en producción; también verifica el opt-in explícito de documentación. |
| `test_development_samesite_none_requires_explicit_secure_cookie` | Comprueba que desarrollo habilite docs pero rechace `SameSite=None` sin Secure, y que la misma configuración sea válida al activar Secure explícitamente. |
| `test_provider_config_exports_and_embedding_warning_match_settings` | Comprueba que los diccionarios exportados de Cohere, OpenAI heredado y RAG reflejen Settings. Una dimensión de embedding 512 produce advertencia, no un error que invalide toda la configuración. |


### `backend/unit/test_postgres_adapter.py`

**Objetivo:** ejecutar métodos del adaptador real con conexión/cursor simulados
para inspeccionar SQL, parámetros, serialización y transacciones. No hay servidor
PostgreSQL: estas pruebas no verifican schemas, migraciones o permisos reales.

| Caso | Qué comprueba |
|---|---|
| `test_conversation_read_scopes_owner_and_normalizes_nullable_fields` | Comprueba que el SELECT filtre por conversación y propietario con parámetros separados; normaliza metadatos nulos y fecha de actualización ausente, y devuelve `None` cuando el cursor no encuentra una fila. |
| `test_message_insert_scopes_owner_serializes_dates_and_rolls_back` | En éxito, fila ausente y excepción comprueba INSERT condicionado por propietario, serialización JSON de fechas anidadas y resultado normalizado. Solo el éxito confirma la transacción; los otros casos hacen rollback y no commit. |
| `test_message_and_conversation_listing_use_owner_and_pagination` | Comprueba filtro del historial por propietario y parámetros de límite/offset del listado; normaliza metadatos, contador de mensajes y fecha de actualización ausentes en las filas simuladas. |
| `test_conversation_update_and_delete_preserve_owner_and_return_result` | Comprueba que una actualización vacía no ejecute SQL; con un modelo Pydantic valida título, metadatos con fecha y `is_active=False`. UPDATE/DELETE incluyen propietario y devuelven verdadero o falso según la fila retornada, con commit. |
| `test_conversation_update_rolls_back_database_error` | Simula fallo al ejecutar UPDATE y comprueba propagación del error, rollback y ausencia de commit para no presentar una actualización fallida como confirmada. |
| `test_disconnected_adapter_never_returns_fabricated_conversations` | Sin conexión comprueba lecturas vacías, actualización/eliminación falsas y `DatabaseUnavailableError` al crear conversación; no se devuelve persistencia ficticia. |
| `test_create_user_persists_google_profile_picture` | Verifica que `create_user` acepte la foto de perfil recibida de Google, la incluya en los parámetros del INSERT, la devuelva en el usuario creado y confirme la transacción. Evita la regresión del parámetro `picture` no admitido; usa un cursor simulado y no comprueba migraciones ni el login real con Google. |


### `frontend/component/SandAnimation.test.tsx`

**Objetivo:** comprobar el lifecycle de la animación con un contexto 2D y una
cola de `requestAnimationFrame` (RAF) controlados. Se avanzan frames manualmente;
no se evalúa apariencia, rendimiento gráfico ni física en un navegador real.

| Caso | Qué comprueba |
|---|---|
| `movimiento reducido termina una vez sin canvas ni RAF` | Simula preferencia de movimiento reducido y comprueba finalización única sin programar frames de animación. |
| `canvas no disponible permite continuar sin bloquear la interfaz` | Hace que `getContext('2d')` devuelva `null`; comprueba finalización única y ausencia de RAF para no bloquear el acceso a la interfaz. |
| `ciclo simulado dibuja cae reforma y termina una sola vez` | Avanza hasta 700 frames sobre una máscara sintética; comprueba dibujo de partículas y texto de bienvenida, una sola llamada de finalización y cola de frames vacía al terminar. |
| `desmontar cancela el frame pendiente y libera resize` | Tras un frame desmonta el componente; comprueba cancelación del siguiente RAF y cola vacía. Emitir resize después no vuelve a transformar el canvas ni llama a finalización. |
| `resize cambia dimensiones sin reconstruir la máscara inicial` | Cambia el ancho de la ventana y emite resize; comprueba dimensiones físicas del canvas según DPR y que la máscara inicial se lea una sola vez. |
| `animación sin callback también se detiene tras un ciclo` | Ejecuta el ciclo sin `onComplete` y comprueba que la cola quede vacía: la parada no depende de que el consumidor proporcione callback. |


### `frontend/component/FloatingRadialHub.test.tsx`

**Objetivo:** comprobar interacción y estado accesible del dial en jsdom.
Las coordenadas se simulan; no se prueba captura real de micrófono/cámara ni
subida de archivos, únicamente la invocación de los callbacks correspondientes.

| Caso | Qué comprueba |
|---|---|
| `dial controla acciones y no expone adjuntos cerrados al teclado` | Verifica la ref del botón terminal, ausencia de adjuntos en la consulta de roles accesibles cuando están cerrados, `aria-expanded` y tabIndex al abrirlos. Archivo/cámara cierran el menú; terminal, historial y micrófono invocan sus callbacks. |
| `rotación por ratón y tacto se detiene al soltar y al desmontar` | Con un rectángulo simulado comprueba rotaciones por mouse y touch, ausencia de cambios al mover el mouse después de soltar y cursor normal al terminar touch; ejercita desmontaje seguido de un movimiento adicional. No compara posición visual real. |


### `frontend/component/navigationPages.test.tsx`

**Objetivo:** comprobar las decisiones de navegación y la composición de rutas
con router/estado de autenticación simulados. La página de chat se sustituye por
un marcador, pues tiene su propia suite. No se valida autenticación de servidor,
intercambio OAuth con Google ni exactitud jurídica de las consultas sugeridas.

| Caso | Qué comprueba |
|---|---|
| `ruta protegida espera hidratación redirige invitados y permite autenticados` | Antes de montar no muestra contenido ni navega; montado como invitado redirige a `/login` y sigue ocultándolo; con autenticación simulada permite mostrar los hijos. |
| `callback OAuth guarda indicador UI no token y vuelve a inicio` | Comprueba que el callback guarde `auth_just_logged_in=true`, no escriba un valor en la clave `token` y use `router.replace('/')`. No prueba validación de estado OAuth ni cookies del backend. |
| `registro redirige al flujo login existente` | Comprueba mensaje de redirección y `router.push('/login')`, documentando que esta pantalla no implementa un formulario de registro. |
| `login inicia OAuth y deshabilita reenvío durante navegación` | Con `window.location` simulado comprueba la URL local actual `/auth/google`, cambio del botón a estado de conexión y deshabilitación tras el clic; no abre Google ni verifica URL de producción. |
| `bienvenida %s ofrece seis consultas seleccionables` | En español y quechua comprueba seis botones, invocación del callback al seleccionar cada uno y consultas de texto no triviales. No juzga la traducción ni el contenido legal de esos textos. |
| `entrypoints y layout conservan idioma proveedores y metadatos` | Inspecciona el árbol del layout (`html lang=es`, envoltorios y contenido), metadatos de layout/inicio y wrappers de login/registro; comprueba que Home renderice el marcador de ChatPage. No ejecuta los providers reales en este caso. |

### `frontend/component/ThemeProvider.test.tsx`

**Objetivo:** ejercitar el provider real de next-themes con preferencias y
media queries simuladas; comprueba clases del documento, no estilos/píxeles.

| Caso | Qué comprueba |
|---|---|
| `tema guardado aplica clase oscura sin esconder hijos` | Con preferencia `dark` en localStorage comprueba clase oscura del documento, conservación de la preferencia y visibilidad del contenido hijo. |
| `tema del sistema sigue cambios y libera listener al desmontar` | Con tema `system` simula cambio de media query de claro a oscuro y comprueba las clases correspondientes; al desmontar verifica eliminación del listener registrado. |


### `frontend/integration/legacyChatHooks.test.tsx`

**Objetivo:** ejercitar `useBackendChat` y `usePersistentChat` reales, simulando
solo su dependencia `apiService`. Comprueba estado y argumentos entre operaciones;
no acredita persistencia remota, aislamiento entre usuarios ni el flujo principal
actual, que utiliza `useChat`/`useChatSessions` y tiene suites independientes.

| Caso | Qué comprueba |
|---|---|
| `backend chat conserva historial fecha e identidad de conversación entre envíos` | Comprueba estado online inicial, trim e idioma al enviar, conservación del ID en el siguiente envío y mapeo de contenido/fecha. Prueba fallback a mensaje único sin historial, carga, creación con título, limpieza de mensajes y reset del ID. |
| `backend chat %s maneja fallo API y excepciones sin dejar loading` | Para enviar, cargar y crear simula respuesta API fallida, excepción Error y valor rechazado no Error; comprueba error visible, `isLoading=false` y limpieza posterior con `clearError`. |
| `backend chat rechaza entradas vacías y solapadas y limpia sondeo al desmontar` | Comprueba que texto vacío no llame a API y que, con un envío pendiente, el segundo no se envíe; resuelve el primero con fallo y verifica cancelación de un intervalo al desmontar. |
| `backend chat listado y salud reportan fallo sin inventar datos` | Comprueba listado exitoso y retorno `null` ante fallo API/excepción; estados de salud no saludable o excepción dejan `isOnline=false` sin fabricar un listado. |
| `chat persistente carga envía continúa y crea con notificación y metadatos` | Comprueba carga automática y notificación de conversación, fecha del mensaje, argumentos de envío y resultado; continuar recarga historial, crear conserva conversación y vacía mensajes, y reset elimina la conversación del estado. |
| `chat persistente %s propaga errores controlados y recupera estado` | Para enviar, cargar, crear y continuar comprueba manejo de respuesta fallida, Error y rechazo no Error, liberación de loading y limpieza explícita del error. |
| `chat persistente sin id omite continuación y tolera historial metadatos y fechas ausentes` | Sin ID no continúa y con texto vacío no envía; con mensaje sin fecha/metadatos aplica Date y objeto vacío. Si falta historial usa lista vacía, y un fallo de health deja offline. |


### Caso adicional en `backend/http/test_api.py`

**Objetivo:** comprobar coherencia de metadata HTTP con el fixture offline de
la API; el fixture no ejecuta el lifespan ni necesita servicios externos.

| Caso | Qué comprueba |
|---|---|
| `test_api_version_metadata_uses_single_configured_identity` | Consulta raíz y health mediante el cliente HTTP y genera el esquema OpenAPI; verifica que los tres usen el mismo `settings.APP_VERSION`, evitando textos de versión discordantes. No inspecciona un despliegue remoto. |

### `scripts/unit/test_documentation_contract.py`

**Objetivo:** contrastar guías activas con manifiestos y fuentes locales para
evitar contratos documentados inexistentes. No navega enlaces externos, valida
anclas internas ni comprueba por completo toda la documentación del proyecto.

| Caso | Qué comprueba |
|---|---|
| `test_current_guides_identify_branch_date_and_existing_local_links` | En las ocho guías seleccionadas comprueba identidad `v8`, fecha documentada `2026-10-06` y existencia de los destinos de enlaces relativos. Ignora URLs externas y anclas; no mide automáticamente frescura frente a la fecha actual. |
| `test_documented_frontend_versions_and_root_commands_match_manifests` | Comprueba presencia de versiones Next/React/pnpm de los manifiestos en la guía frontend y que los comandos pnpm raíz detectados existan en scripts o sean install. Omite comandos cuyo primer argumento es una opción, como `--dir`; no ejecuta esos comandos. |
| `test_api_documented_explicit_routes_exist_in_current_source` | Extrae decoradores GET/POST/PUT/DELETE de main y chat mediante AST y comprueba las rutas explícitas con ese formato en API_DOC. No importa la app, verifica llamadas HTTP ni audita todas las rutas OAuth. |

### Verificación de las explicaciones del catálogo

Revisión documental del **2026-10-06**: los 49 nombres de pruebas nuevos tienen
una explicación en tabla (10 archivos nuevos y un caso HTTP adicional), con
objetivo y límites por grupo. Pasaron los 7 tests de catálogo y contratos de
documentación, y `git diff --check` no encontró errores de whitespace.
No se volvió a ejecutar la suite completa para esta corrección de texto:
harness de producto **N/A**, porque no cambia comportamiento ni código de tests.
Rollback de esta corrección: solo los bloques explicativos de este README;
preserva el catálogo, los tests y la ampliación previa.

## Resultado actual de la ampliación transversal

Verificado el **2026-10-06** con `pnpm test:coverage` (exit 0):

| Medida | Baseline al iniciar esta tarea | Resultado actual |
|---|---|---|
| Python aprobados | 252 | **302** |
| Node aprobados | 23 | **23** |
| React aprobados | 65 | **94** |
| Backend: líneas | 46,62 % (2716/5826) | **57,24 % (3335/5826)** |
| Backend: ramas | 29,91 % (466/1558) | **45,25 % (705/1558)** |
| Frontend: líneas | 41,68 % (579/1389) | **80,52 % (1125/1397)** |
| Frontend: ramas | 43,70 % (368/842) | **72,51 % (612/844)** |

Se mantienen las mismas fuentes/exclusiones: 70 módulos Python y 32 archivos
frontend. El denominador frontend crece por el control de lifecycle añadido,
no por retirar archivos. El 55 % combinado que imprime pytest mezcla statements
y ramas: no es el 57,24 % de líneas del XML. Los 3 casos reales siguen omitidos,
y los 2 xfail estrictos son los ya existentes. Hay 20 warnings de dependencias.

También pasaron **5/5 E2E** con API simulada en Edge headless, `tsc --noEmit`,
build de Next, `pnpm deps:check` y catálogo/enlaces/comandos documentados.
No se ejecutó scanner/Quality Gate ni llamadas facturables a modelos.
Se corrigieron dos errores descubiertos por los tests: doble escape de código
inline en PDF real, y finalización/cleanup RAF de la animación.

Pendientes de cobertura: pantallas heredadas y ramas de servicios/auth/contexto,
scripts operativos y más comprobaciones con PostgreSQL real. La cobertura no
demuestra precisión jurídica ni calidad de retrieval/traducción.

Unidades de trabajo revisables/rollback, aún **sin commits nuevos**:
1. Documentación/identidad v8/plantillas: guías, Settings, metadata API y contratos de docs/HTTP.
2. PDF: escape inline y pruebas ReportLab/pypdf reales juntos.
3. Backend: chunker/Settings/SQL con pruebas offline; no modifica estrategias ni proveedor.
4. Frontend: lifecycle animación y sus pruebas, radial hub, hooks heredados, rutas/providers.

Evidencia local ignorada: `coverage.xml`, `temp/coverage-baseline.xml`,
`temp/frontend-coverage-baseline.json`, `temp/sonar-reports/` y trazas Playwright.
El harness de ejecución es pnpm/pytest/Vitest/Playwright; no se requiere un
servicio de modelos real para estas unidades ni se revierten datos del corpus.

## Google OAuth: regresiones HTTP y sesiones simuladas

### Ejecutar y entender el alcance

```bash
pnpm test:python tests/backend/http/test_google_oauth.py
pnpm test:frontend tests/frontend/component/AuthProvider.test.tsx
```

`backend/http/test_google_oauth.py` contiene **25 escenarios parametrizados**:
ejecuta las rutas FastAPI reales, el intercambio HTTP mediante `MockTransport`
y firma/decodificación JWT reales con claves sintéticas. PostgreSQL usa dobles
asíncronos; Google, credenciales, cuentas y avatares son ficticios. No inicia el
backend completo, toca tu cuenta, lee cookies de tu navegador ni requiere red.

| Caso | Qué comprueba |
|---|---|
| `test_google_login_redirect_contains_oauth_parameters` | Redirección al proveedor configurado, client ID, callback, scopes y parámetros de consentimiento; no consulta proveedor ni base de datos. |
| `test_google_login_requires_client_id` | Configuración incompleta devuelve 500 sin iniciar el intercambio con Google. |
| `test_google_callback_exchanges_code_and_issues_real_jwts` | Usuario nuevo y existente: código con caracteres especiales correctamente codificado, POST del grant y GET con Bearer; creación/actualización de perfil y avatar; redirección frontend, cookies HttpOnly/SameSite/path/vigencia y JWT de acceso/refresh con identidad, tipo, firma y expiración correctos. |
| `test_google_callback_handles_optional_profile_fields` | Perfil sin nombre/avatar: crea valores vacíos para usuario nuevo y conserva los valores existentes en la actualización. |
| `test_google_callback_requires_configuration` | Ausencia de client ID o secret aborta antes de llamadas al proveedor y sin emitir tokens/cookies. |
| `test_google_callback_rejects_missing_or_empty_code` | Código omitido produce 422 de FastAPI; código vacío produce 400 de la ruta. Ninguno consulta Google ni inicializa la base. |
| `test_google_callback_provider_failures_do_not_issue_session` | HTTP 401, timeout y JSON inválido, tanto en token como en perfil: devuelve solo el error genérico, no inicializa PostgreSQL ni crea sesión; verifica que no continúe el intercambio fallido y que el logger OAuth no incluya secretos, mensajes privados ni traceback. |
| `test_google_callback_requires_provider_token_and_email` | Falta de access token o email impide crear/actualizar usuarios y emitir sesión. |
| `test_google_callback_database_failures_do_not_issue_session` | Fallos en inicialización, búsqueda, creación o actualización terminan con error genérico sin JWT ni cookies; los primeros fallos tampoco escriben usuarios. |
| `test_google_callback_preserves_explicit_http_exception` | Un HTTPException 503 conserva código y detalle, en vez de convertirse en 500; no emite sesión. |
| `test_google_callback_cannot_issue_session_without_created_user` | Si la creación devuelve None, no firma tokens ni emite cookies. |
| `test_google_session_can_read_profile_and_logout` | Callback exitoso, cookies aceptadas por `/auth/me`, perfil/avatar/roles correctos, logout elimina ambas cookies y la siguiente consulta devuelve 401; no vuelve a llamar a Google. |

### Por qué los logs de los tests no describen tu cuenta

En `frontend/component/AuthProvider.test.tsx`, `getCurrentUser` está simulado:
los casos anónimos devuelven deliberadamente `null`, aunque estés conectado con
Google en tu navegador. jsdom tiene su propio storage y no comparte esa sesión.
Los mensajes de depuración `console.log` del componente se capturan **solo en
este archivo de pruebas**, con restauración después de cada caso; no se ocultan
fallos de tests, warnings ni errores, y los logs de la aplicación no cambian.

| Caso adicional | Qué comprueba |
|---|---|
| provider callback Google simulado revalida sesión por storage y muestra usuario | Partiendo de sesión anónima simulada, el evento storage de callback dispara una segunda consulta, propaga el usuario Google ficticio hasta la UI, elimina el flag y no guarda access/refresh tokens en localStorage. No abre Google ni prueba el callback Next completo. |

**Límites de seguridad:** estos tests describen el contrato actual, no certifican
OAuth para producción. No validan CSRF/state (el callback aún no lo verifica),
verificación de email, ID token, PKCE ni `Secure` de las cookies OAuth; tampoco
ejecutan PostgreSQL real, TLS/CORS ni navegación real a Google. No sustituir
estos escenarios por pruebas que usen tu sesión personal.

**Unidad de rollback:** el archivo HTTP nuevo, las mejoras locales de
`AuthProvider.test.tsx` y este bloque/corrección de nombres del catálogo.
Incluye la corrección puntual del logger OAuth: conserva tipo de error e ID de
petición, sin texto de excepción ni traceback que puedan filtrar credenciales.
La suite detectó esta regresión mediante `test_oauth_failure_is_redacted`;
no se cambian contratos OAuth ni se revierten migraciones o datos de usuarios.

### Verificación de esta ampliación (2026-10-06)

- Google OAuth HTTP: **25/25** escenarios aprobados.
- AuthProvider: **4/4** casos aprobados, sin mensajes de sesión ambiguos.
- Suite Python completa (`pnpm test:python`): **328 aprobados**, 3 omitidos de
  evaluaciones reales opt-in, 2 xfail previos y 20 warnings de dependencias.
- Suite React completa (`pnpm test:frontend`): **95 aprobados**, 19 archivos.
- `pnpm --dir frontend exec tsc --noEmit` y `git diff --check`: sin errores.

No se recalculó cobertura ni se ejecutaron E2E contra Google: las cifras de
cobertura de la ampliación transversal anterior siguen siendo históricas.
El harness HTTP usa las rutas reales de auth con dependencias externas simuladas.

## Harness de evaluación — v8, 2026-10-22

Plan completo y orden de fases: [plan del harness](../docs/HARNESS-IMPLEMENTATION-PLAN.md).
Las secciones siguientes catalogan los tests que añade cada fase.

### F0 — Contrato NDJSON v1 y tiempos por etapa

El stream emite `meta`, `stage`, `chunk`, `final`, `error` y `done`, todos con
`{v, seq, request_id, type}`. Los tests solo usan estados simulados: no llaman a
Cohere, Google ni OpenAI. El contrato se exporta con
`uv run python backend/scripts/export_stream_contract.py` a
`backend/contracts/stream_event.v1.schema.json` y a
`frontend/src/domain/legal/streamEvents.generated.ts`; un test falla si quedan
desactualizados.

| Archivo | Qué verifica |
|---|---|
| [`backend/contract/test_stream_contract.py`](backend/contract/test_stream_contract.py) | Eventos válidos e inválidos del contrato v1, códigos de error con mensaje fijo y archivos exportados al día. |
| [`backend/unit/test_stream_pipeline.py`](backend/unit/test_stream_pipeline.py) | Tiempos por etapa de `answer_query`, caché sin tiempos, errores con `code`, orden del stream, timeout, cancelación y fallo de persistencia. |
| [`frontend/component/PipelineStatus.test.tsx`](frontend/component/PipelineStatus.test.tsx) | Etapas en vivo, errores por `code` con Reintentar, "Respondió en X s" con desglose, en español y quechua. |

| Caso | Qué verifica |
|---|---|
| `test_valid_events_round_trip` | Cada tipo de evento válido se parsea y se serializa sin cambios. |
| `test_invalid_events_are_rejected` | Se rechazan eventos sin `v`/`seq`, con campos extra, etapa o código desconocido, versión distinta o `seq` negativo. |
| `test_every_error_code_has_fixed_message_and_retry_policy` | Todo `code` tiene mensaje fijo y política de reintento; `INTERNAL_ERROR` no es reintentable. |
| `test_exported_schema_and_typescript_are_up_to_date` | El JSON Schema y los tipos TypeScript coinciden con el modelo Pydantic. |
| `test_timer_records_stage_and_notifies_start_and_end` | El temporizador acumula milisegundos por etapa, avisa inicio y fin y rechaza etapas desconocidas. |
| `test_answer_query_reports_every_stage_in_order_and_timings` | `answer_query` notifica retrieval, generation y validation en orden y devuelve `metadata.timings`. |
| `test_cache_hit_has_timings_and_timings_are_not_cached` | Un acierto de caché marca `cache_hit` y los tiempos nunca se guardan en la caché. |
| `test_pipeline_errors_carry_stable_code` | Fallos de recuperación y generación llevan `code` estable y no filtran el texto de la excepción. |
| `test_stream_emits_stages_before_validated_text_then_done` | `meta` y `stage` preceden al texto, que solo sale validado; `seq` consecutivo, un solo `request_id`, termina en `done`. |
| `test_stream_failures_become_a_single_error_event_with_code` | Un fallo posterior a abrir el stream produce un único `error` con `code` y `retryable`, sin eco del texto privado. |
| `test_stream_times_out_and_cancels_the_pipeline` | El timeout emite `TIMEOUT` reintentable y cancela el pipeline en curso. |
| `test_persistence_failure_is_an_error_not_a_final` | Si no se puede persistir la respuesta no se entrega `final`, sino `error`. |

| Caso | Qué verifica |
|---|---|
| `etapas en vivo marcan la activa y las terminadas, en español y quechua` | La etapa en curso tiene `aria-current`, las terminadas se marcan y los textos cambian de idioma. |
| `la traducción de entrada y salida se muestra como un único paso` | `translate_in` y `translate_out` se presentan como un solo "Traduciendo". |
| `error muestra texto según code, sin eco del servidor, y reintenta solo si es reintentable` | El texto sale de `translations.ts` según `code`; el botón Reintentar solo aparece si `retryable`. |
| `tiempo de respuesta muestra segundos y desglose por etapa` | "Respondió en X s", desglose por etapa y variante de caché. |
| `la terminal integra etapas, error con reintento y tiempos del asistente` | `TerminalModal` muestra etapas, error con reintento y tiempos de los mensajes del asistente. |
| `contrato v1: etapas en vivo, texto validado y tiempos en el payload final` | `useChat` actualiza la etapa en vivo y conserva `metadata.timings` del `final`. |
| `contrato v1: error con code se conserva y reintentar reenvía la misma consulta` | `useChat` guarda `errorInfo` y `retry` reenvía la consulta sin duplicar mensajes locales. |

**Cambio de comportamiento:** los fallos posteriores a la autorización y a la
comprobación de la conversación (401/404) dejan de ser un HTTP 5xx y salen como
evento `error` dentro de un stream 200. `test_stream_error_and_logs_do_not_echo_query_or_request_id`
documenta ese caso.

### F1 — Gold y métricas contra alucinaciones

El gold (`tests/backend/fixtures/gold/legal_qa.v1.jsonl`) contiene 37 casos **candidatos**
(`status: "candidate"`, `reviewers: []`) extraídos de `backend/docs/processed/`; cada hecho
cita un fragmento textual de su segmento y el cargador lo comprueba contra el corpus. Lo que
el gold llama "hecho" es lo que el corpus afirma, no verdad jurídica verificada. Se regenera
con `uv run python -m evaluation.harness.seed_legal_qa` (desde `backend/`). Los tests no llaman a
Cohere, Google ni OpenAI.

| Archivo | Qué verifica |
|---|---|
| [`backend/harness/test_gold.py`](backend/harness/test_gold.py) | Esquema estricto del gold, procedencia de los 37 casos semilla (`candidate`), citas textuales verificadas contra el corpus y rechazo de casos incoherentes. |
| [`backend/harness/test_metrics.py`](backend/harness/test_metrics.py) | Regla `n/a`, agregación macro/micro, legal factuality, precisión de citas, abstención, calibración y faithfulness como diagnóstico. |
| [`backend/harness/test_pipeline_eval.py`](backend/harness/test_pipeline_eval.py) | Evaluación del gold con respuestas sintéticas, errores sin ceros falsos, jueces, cassettes, umbrales prerregistrados y metadatos del resultado. |
| [`backend/unit/test_citation_verifier.py`](backend/unit/test_citation_verifier.py) | Extracción de Ley/artículo/Casación/D.S. con su código, coincidencia por número y verificación contra evidencia, también con OCR espaciado. |
| [`frontend/component/EvidencePanels.test.tsx`](frontend/component/EvidencePanels.test.tsx) | Tarjeta de evidencia insuficiente con recursos, chips de citas ✓/⚠ con extracto y panel "¿Por qué confiar en esta respuesta?". |

**`backend/harness/test_gold.py`**

| Caso | Qué verifica |
|---|---|
| `test_segmenter_is_deterministic_and_drops_page_noise` | El segmentador produce los mismos segmentos con LF o CRLF y descarta imágenes, URLs, contadores de página y sellos de fecha. |
| `test_document_ids_are_unique_and_stable` | Los `doc_id` salen del nombre de archivo, son únicos y la revisión del corpus es estable entre cargas. |
| `test_seed_cases_are_candidates_without_reviewers` | Los casos semilla son `candidate`, sin revisores: ninguno se presenta como verdad. |
| `test_seed_covers_all_strata_splits_and_topics` | La semilla cubre positivo/límite/negativo, dev/holdout y los cinco temas más `fuera_de_corpus`. |
| `test_every_fact_and_contradiction_quotes_the_corpus` | Cada hecho y cada contradicción cita un fragmento que existe en su segmento de origen. |
| `test_checked_in_jsonl_matches_the_seed_definition` | El JSONL versionado coincide con lo que genera `seed_legal_qa`; no se edita a mano. |
| `test_each_fact_text_satisfies_its_own_anchors` | Un hecho escrito con sus propias palabras cuenta como cubierto: las anclas no son más estrictas que el hecho. |
| `test_forbidden_patterns_detect_their_example_but_not_the_facts` | Cada patrón prohibido detecta su ejemplo y no se activa con los hechos correctos. |
| `test_negative_cases_are_out_of_corpus_and_require_abstention` | Los negativos exigen abstención, no tienen segmentos y sus términos ausentes no están en el corpus. |
| `test_loader_filters_splits_and_adjudicated` | El cargador filtra por split y por casos adjudicados (hoy ninguno). |
| `test_gold_hash_ignores_line_endings` | El hash del gold es el mismo con LF o CRLF. |
| `test_schema_rejects_inconsistent_cases` | Se rechazan campos extra, revisores en un candidato, adjudicación incompleta, abstención con hechos, estrato o split inválidos e IDs mal formados. |
| `test_negative_with_segments_or_without_absent_terms_is_rejected` | Un negativo sin `absent_terms` o con un tema del corpus no es válido. |
| `test_two_blind_approvals_make_a_case_adjudicated` | Dos revisores distintos, ciegos y que aprueban habilitan `adjudicated`. |
| `test_verification_detects_invented_quote_changed_text_and_corpus_leaks` | La verificación detecta una cita inventada, un segmento cambiado, un patrón `unsupported` presente en el corpus, un término ausente que sí aparece y una cita aceptable inexistente. |
| `test_loader_reports_every_problem_with_its_line` | Un JSON roto y un `id` repetido se informan juntos, con el número de línea. |

**`backend/harness/test_metrics.py`**

| Caso | Qué verifica |
|---|---|
| `test_na_is_never_a_silent_zero_in_macro_or_micro` | Un `n/a` no entra en macro ni micro y se cuenta aparte. |
| `test_macro_and_micro_differ_when_cases_have_different_sizes` | Macro (media por caso) y micro (suma de numeradores/denominadores) se calculan por separado. |
| `test_all_na_reports_reason_instead_of_a_number` | Si todo es `n/a` el resultado es `null` con la razón, no 0. |
| `test_zero_denominator_is_na_and_samples_are_merged` | Denominador cero es `n/a`; las muestras de un caso se unen por media y suma. |
| `test_fact_recall_counts_covered_facts_and_is_na_when_abstention_is_required` | Recall de hechos exigidos; `n/a` cuando el caso exige abstenerse. |
| `test_legal_factuality_zeroes_out_when_a_forbidden_claim_is_made` | Una afirmación prohibida pone la factualidad en 0 aunque los hechos estén cubiertos. |
| `test_negated_forbidden_claim_is_not_flagged` | "No pierdes el derecho" no dispara la afirmación "pierdes el derecho". |
| `test_forbidden_claim_is_na_when_the_case_defines_none` | Sin afirmaciones prohibidas definidas la métrica es `n/a`, no 0. |
| `test_oracle_answers_are_fully_factual_for_every_answerable_case` | La respuesta ideal de cada caso cubre todos sus hechos sin afirmar nada prohibido. |
| `test_citation_precision_uses_the_corpus_and_the_acceptable_list` | Precisión de citas contra el corpus y contra las citas aceptables del caso. |
| `test_citation_metrics_are_na_without_citations_or_acceptable_list` | Sin citas o sin lista aceptable, la métrica es `n/a`. |
| `test_citation_index_finds_citations_in_spaced_ocr_documents` | El índice encuentra Casación y artículo en documentos con OCR espaciado. |
| `test_citation_grounded_reads_runtime_statuses` | La precisión contra evidencia recuperada lee `metadata.citations` del runtime. |
| `test_abstention_metrics_are_complementary_and_semantic_markers_count` | Recall de abstención y abstención innecesaria son complementarias; una no-respuesta explícita cuenta. |
| `test_calibration_perfect_overconfident_and_empty` | ECE y Brier para confianza perfecta, sobreconfiada y sin datos. |
| `test_faithfulness_is_a_diagnostic_with_na_when_missing` | Faithfulness es diagnóstico: `n/a` si el validador o el juez no lo midieron. |
| `test_answer_from_payload_reads_the_pipeline_contract` | `Answer` se construye desde el payload de `answer_query` (texto, estado, confianza, citas, tiempos). |

**`backend/harness/test_pipeline_eval.py`**

| Caso | Qué verifica |
|---|---|
| `test_oracle_answers_score_perfectly_on_every_applicable_metric` | Con respuestas ideales todas las métricas aplicables son perfectas y los estratos/splits se agregan. |
| `test_degraded_answers_lower_factuality_and_expose_missing_facts` | Respuestas degradadas bajan la factualidad, exponen los hechos faltantes y la calibración lo refleja. |
| `test_forbidden_claim_in_an_otherwise_correct_answer_is_reported` | Una afirmación prohibida se informa por caso aunque el hecho correcto esté presente. |
| `test_errors_are_counted_not_converted_into_zeros` | Un error al responder se cuenta como error, sin texto de la excepción y sin ceros falsos. |
| `test_samples_are_merged_per_case` | Con N muestras cada caso promedia sus muestras y se conservan todas las respuestas. |
| `test_judge_metrics_are_na_without_a_judge_and_present_with_one` | Sin juez las métricas del juez son `n/a`; con juez se registran su nombre, modelo y disponibilidad. |
| `test_judge_factory_registers_availability_without_calling_models` | El juez `deepeval` informa si está disponible sin llamar a ningún modelo ni revelar claves. |
| `test_cassette_replays_records_and_refuses_unrecorded_requests` | El cassette reproduce, graba solo en modo de grabación y falla ante una solicitud no grabada. |
| `test_result_file_carries_reproducibility_metadata` | El resultado en disco lleva sha, `prompt_digest`, corpus, hash del gold, modelos, juez y su disponibilidad. |
| `test_thresholds_are_unregistered_by_default_and_never_pass_silently` | Sin umbrales prerregistrados el veredicto es `unregistered`, nunca `pass`. |
| `test_registration_requires_a_baseline_measurement_and_adjudicated_gold` | Registrar umbrales exige un baseline medido, métricas aplicables y gold adjudicado (o marcarlo provisional). |
| `test_registered_thresholds_pass_fail_and_go_stale_with_the_gold` | Umbrales registrados: pass, fail, n/a como fallo y `stale` si cambia el gold. |

**`backend/unit/test_citation_verifier.py`**

| Caso | Qué verifica |
|---|---|
| `test_extracts_normalised_citation_keys` | Claves normalizadas para Ley, artículo (con su código), Casación y Decreto Supremo, incluidas variantes del OCR. |
| `test_extraction_keeps_the_original_text_of_each_citation` | Cada cita conserva el texto original, con mayúsculas y tildes. |
| `test_code_is_not_borrowed_from_a_later_citation` | Un artículo no toma el código de la cita siguiente. |
| `test_codeless_article_matches_by_number_but_different_codes_do_not` | Un artículo sin código coincide por número; códigos distintos no coinciden. |
| `test_despace_joins_letter_spaced_ocr_runs` | Se unen las rachas de letras sueltas del OCR espaciado. |
| `test_verification_marks_traceable_and_untraceable_citations_with_excerpt` | Citas trazables a la evidencia con extracto y citas no halladas marcadas `unverified`. |
| `test_verification_reads_spaced_ocr_evidence` | La verificación lee evidencia con OCR espaciado. |
| `test_verification_without_evidence_leaves_everything_unverified` | Sin evidencia ninguna cita queda verificada. |
| `test_answer_includes_verified_citations_and_evidence_excerpts` | `answer_query` agrega `metadata.citations` verificadas y `metadata.evidence` con extractos del corpus. |
| `test_answer_without_documents_has_no_citations_or_evidence` | Sin documentos hay abstención formal, sin citas ni evidencia. |

**`frontend/component/EvidencePanels.test.tsx`**

| Caso | Qué verifica |
|---|---|
| evidencia insuficiente muestra la tarjeta con recursos de ayuda y teléfonos | Línea 100, CEM y Defensoría con enlaces `tel:`. |
| tarjeta de evidencia insuficiente existe en quechua y reemplaza chips y panel | Existe en quechua y sustituye a los chips y al panel de confianza. |
| chips de citas distinguen verificadas y no verificadas y muestran el extracto del corpus | ✓/⚠ accesibles y extracto del corpus al abrir el chip. |
| sin citas no se dibuja el bloque de citas | Sin citas no se renderiza nada. |
| panel de confianza resume solo lo medido: fuentes, validador, riesgo, citas y aviso | Fuentes, validador, riesgo, citas verificadas, fiabilidad y aviso. |
| panel de confianza advierte cuando no es fiable y no inventa datos ausentes | Sin fuentes ni citas lo dice; si no es fiable lo advierte. |
| la terminal muestra tarjeta, chips y panel solo en respuestas finales del asistente | La terminal no muestra estos bloques mientras la respuesta aún se transmite. |

**`scripts/unit/run-tests.test.mjs`**

| Caso | Qué verifica |
|---|---|
| harness es offline y harness-real exige --run-model-evals con EVAL_MODE=1 | `harness` es offline; `harness-real` falla sin el flag y fuerza `EVAL_MODE=1`. |

### F2 — Recuperación de jurisprudencia

`backend/evaluation/harness/retrieval_eval.py` evalúa **por separado** cada etapa: LightRAG puro
(`naive`, `local`, `global`, `hybrid`, `mix`), solo léxico (BM25), la mezcla actual antes del
rerank, el resultado tras el rerank con umbral 0.1 y el mismo rerank sin umbral. Los fragmentos
se mapean a segmentos con la regla de solapamiento de `overlap.py` (n-gramas de 10 caracteres; el
fragmento contiene ≥ 60 % del segmento o es ≥ 60 % parte de él; lo no mapeado se conserva como
`unmapped:<huella>`). Los sistemas que dependen de LightRAG o de Cohere son `n/a` sin
`--run-model-evals` o sin cassette; los tests no llaman a ningún proveedor.

Comando sin red: `uv run python -m evaluation.harness.runner retrieval` (desde `backend/`). El gold de
recuperación `retrieval.v1.jsonl` se deriva de `legal_qa` y hereda su estado `candidate`.

| Archivo | Qué verifica |
|---|---|
| [`backend/harness/test_retrieval.py`](backend/harness/test_retrieval.py) | Regla de solapamiento, recall/precisión de evidencia, MRR, nDCG, jurisprudencia, `no_match`, fallback, pérdida por umbral, auditoría del índice y trazas del motor. |

| Caso | Qué verifica |
|---|---|
| `test_overlap_rule_maps_containing_inside_and_unrelated_chunks` | Un fragmento que contiene el segmento, que es casi todo parte de él o que no se parece a nada se mapea como corresponde. |
| `test_overlap_rule_is_insensitive_to_spacing_and_accents` | Mayúsculas, tildes y espacios no cambian el mapeo; un texto demasiado corto no genera n-gramas. |
| `test_a_long_chunk_maps_to_every_segment_it_contains` | Un fragmento largo corresponde a todos los segmentos que contiene. |
| `test_recall_precision_mrr_ndcg_follow_the_sat_definitions` | Recall y precisión de evidencia con IDs distintos, precisión por fragmento, MRR y nDCG binario. |
| `test_every_retrieval_metric_is_na_without_a_denominator` | Sin evidencia exigida, sin resultados o sin método la métrica es `n/a`, no 0 ni 1. |
| `test_empty_result_and_jurisprudence_flags` | Resultado vacío (indebido o deseable), acierto de jurisprudencia y uso de fallback. |
| `test_threshold_loss_counts_relevant_evidence_scored_under_the_minimum` | Fracción de evidencia relevante del reranker que el umbral mínimo descarta. |
| `test_retrieval_gold_is_derived_from_legal_qa_and_matches_the_checked_in_file` | El gold de recuperación sale de `legal_qa` y el JSONL coincide con la derivación. |
| `test_jurisprudence_is_detected_by_casacion_citations_and_casacion_documents` | La jurisprudencia se detecta por citas de Casación o por documentos sobre una Casación. |
| `test_oracle_retrieval_is_perfect_and_unavailable_systems_are_na_with_reason` | Un recuperador ideal puntúa 1; un sistema no disponible es `n/a` con su razón. |
| `test_irrelevant_results_score_zero_recall_but_are_not_empty` | Resultados irrelevantes dan recall 0 sin contarse como vacíos. |
| `test_threshold_loss_is_measured_from_the_rerank_scores` | La pérdida por umbral se calcula con las puntuaciones del reranker. |
| `test_retrieved_round_trips_through_json` | `Retrieved` se serializa y deserializa sin pérdida (cassettes). |
| `test_index_audit_reports_segments_no_indexed_chunk_can_reach` | La auditoría del índice informa los segmentos que ningún fragmento indexado alcanza. |
| `test_corpus_quality_flags_spaced_ocr_documents_and_gold_dependence` | Se marcan los cuatro documentos con OCR espaciado y cuántos segmentos del gold dependen de ellos. |
| `test_offline_engine_runs_lexical_mix_and_fallback_rerank_without_network` | El motor local ejecuta léxico, mezcla y rerank de respaldo sin red, de forma determinista. |
| `test_trace_exposes_every_rerank_score_without_changing_the_selection` | `trace` expone todas las puntuaciones del rerank sin cambiar los documentos seleccionados. |
| `test_trace_without_reranker_marks_the_fallback` | Sin Cohere la traza marca el rerank de respaldo. |
| `test_evidence_reports_retrieval_origin_and_cited_jurisprudence` | `metadata.evidence` informa el origen (grafo o léxico) y las Casaciones citadas. |
| jurisprudencia relacionada muestra relevancia y camino de recuperación solo de fragmentos con Casación | La UI lista solo fragmentos con Casación, con relevancia y camino. |
| jurisprudencia relacionada tolera relevancia ausente, método desconocido y quechua | Relevancia ausente, método desconocido y versión en quechua. |

### F3 — Traducción es→qu

`tests/backend/fixtures/gold/translation.v1.jsonl` reúne 319 pares **candidatos** extraídos de textos
impresos: los manuales del Ministerio de Cultura (quechua cusco-collao y chanka) y la edición
quechua-castellano de la Ley 30364 (por artículo; la variante exacta no consta y se marca
`sureno-sin-confirmar`). Cada par guarda su origen y el cargador comprueba que el español y el quechua
aparecen en ese archivo. Todos esperan a dos hablantes nativos (`reviewers: []`); no son verdad
lingüística. Se regeneran con `uv run python -m evaluation.harness.translation_seed` (desde `backend/`).

Métricas (`metrics/translation.py`): chrF++ (principal), BLEU y TER sin desplazamientos, adherencia al
glosario, referencias legales conservadas, marcadores `ZXQREF` filtrados, idioma del resultado,
tasa de copia, cobertura y round-trip con embeddings (precalculado al grabar el cassette). El sistema
real (Google Translate) solo se mide con `--run-model-evals` o desde un cassette; sin ellos la suite
mide la línea base "copiar el español".

| Archivo | Qué verifica |
|---|---|
| [`backend/harness/test_translation.py`](backend/harness/test_translation.py) | Gold paralelo y su procedencia, chrF++/BLEU/TER, señales de contrato, glosario, round-trip y la suite con cassette. |
| [`backend/unit/test_translation_qe.py`](backend/unit/test_translation_qe.py) | Estimación de calidad sin referencia y `metadata.translation` (aviso fuera del texto, calidad, fallback al español). |

| Caso | Qué verifica |
|---|---|
| `test_seed_pairs_are_candidates_with_native_review_pending` | Los pares son `candidate`, sin revisores, de tres variantes y cuatro tipos. |
| `test_every_pair_is_found_in_its_printed_source` | El español y el quechua de cada par aparecen en su archivo de origen. |
| `test_verification_rejects_invented_text_and_missing_sources` | Un quechua inventado, un español ausente o un origen inexistente se rechazan. |
| `test_pairs_need_two_blind_native_reviewers_to_be_adjudicated` | `adjudicated` exige dos hablantes nativos distintos, ciegos y que aprueban; el resto de combinaciones inválidas falla. |
| `test_loader_reports_broken_lines_and_duplicates` | Una línea rota y un `id` repetido se informan juntos. |
| `test_loader_filters_kinds_splits_and_adjudicated` | El cargador filtra por tipo, split y adjudicación. |
| `test_page_noise_is_removed_from_sources` | Se quitan los marcadores de página de la maquetación. |
| `test_chrf_matches_hand_computed_values_and_ignores_whitespace_in_characters` | chrF++ coincide con valores calculados a mano; los espacios no cuentan en los n-gramas de caracteres. |
| `test_chrf_rewards_recall_more_than_precision` | Con β = 2 el recall pesa más que la precisión. |
| `test_bleu_and_ter_follow_their_definitions` | BLEU de 4-gramas con suavizado y TER por edición de palabras con la mejor referencia. |
| `test_corpus_bleu_sums_statistics_instead_of_averaging_sentences` | BLEU de corpus suma estadísticas, no promedia oraciones. |
| `test_contract_signals_references_placeholders_language_copy_and_coverage` | Referencias legales conservadas, marcadores filtrados, idioma, copia y cobertura. |
| `test_glossary_adherence_counts_only_terms_present_in_the_source` | Solo cuentan los términos del glosario presentes en el original. |
| `test_round_trip_is_a_cosine_over_injected_embeddings` | Round-trip es un coseno sobre embeddings inyectados (sin red). |
| `test_the_identity_baseline_is_the_floor_and_is_flagged_as_low_quality` | Copiar el español da el piso de las métricas y la estimación de calidad lo marca `baja`. |
| `test_references_used_as_output_score_perfectly_and_qe_separates_good_from_bad` | Las referencias como salida puntúan perfecto; la estimación separa originales largos y cortos. |
| `test_missing_and_failed_outputs_are_errors_not_zeros` | Una salida ausente o fallida es un error, no un 0. |
| `test_precomputed_round_trip_enters_the_report` | El coseno precalculado entra en el informe. |
| `test_language_id_heuristic_is_measured_on_the_gold_itself` | La heurística de idioma se mide sobre el propio gold. |
| `test_translation_suite_writes_offline_baseline_and_replays_a_recorded_cassette` | La suite escribe la línea base offline y reproduce un cassette grabado sin llamar al proveedor. |
| `test_language_heuristic_separates_quechua_spanish_and_short_text` | La heurística distingue quechua, español y textos demasiado cortos. |
| `test_copy_rate_length_and_references` | Tasa de copia, razón de longitud y referencias protegidas. |
| `test_quality_is_high_only_when_every_automatic_check_passes` | `alta` solo si pasan todas las comprobaciones automáticas. |
| `test_quality_is_low_for_untranslated_lost_references_failures_and_absurd_length` | `baja` ante español sin traducir, referencias perdidas, fallos o longitud absurda. |
| `test_quality_is_medium_when_the_language_cannot_be_confirmed` | `media` si no se puede confirmar que sea quechua. |
| `test_quechua_answer_keeps_the_notice_out_of_the_text_and_adds_quality` | El aviso ya no se pega al texto; vive en `metadata.translation` con la calidad. |
| `test_failed_translation_falls_back_to_spanish_without_a_pasted_notice` | Si falla la traducción se conserva el español, sin aviso pegado y sin guardar en caché. |
| aviso de traducción muestra la calidad estimada, el aviso de revisión y alterna el original | Badge de calidad, aviso de revisión y "Ver original en español". |
| aviso de traducción informa cuando se muestra el español por falla y no promete calidad | Si se muestra el español por una falla no se anuncia calidad. |
| aviso de traducción existe en quechua y no aparece sin traducción | Existe en quechua y no se dibuja sin traducción. |

**Limitaciones:** la estimación de calidad exige las referencias legales *literales* (como las produce el
servicio); una traducción humana que las reescribe obtendría `baja`. En frases de menos de cuatro palabras
no puede confirmar el idioma y devuelve `media`.

### F4 — QA del stream

Servidor: `StreamGuard` (`services/stream_guard.py`) envuelve el generador del stream y garantiza
esquema válido, `seq` consecutivo, `request_id` único, **un solo** terminal (`final` o `error`) seguido de
un único `done`, `chunk` igual al texto del `final` (se retiene hasta verlo) y un watchdog que emite
`TIMEOUT` si el origen se queda mudo. Cliente: `ndjsonParser.ts` es una función pura (reloj inyectado)
que tolera BOM, CRLF y líneas partidas, repara o descarta contando, deduplica y ordena por `seq`, usa el
`chunk` si falta el `final` (`degraded`) y mide los tiempos. `POST /telemetry/stream` recibe solo números.

Los streams rotos de `tests/backend/fixtures/gold/ndjson_broken/` se generan con
`uv run python -m evaluation.harness.stream_fixtures` (desde `backend/`) y los usan pytest, vitest y
Playwright. Playwright necesita un navegador: con `npx playwright install` o, si ya tienes Edge,
`PLAYWRIGHT_CHANNEL=msedge pnpm test:e2e`. La suite `stream` del harness (`python -m evaluation.harness.runner
stream`) informa validez y latencia p50/p95 por etapa; sin `--run-model-evals` usa un pipeline simulado y
mide solo el costo propio del stream.

| Archivo | Qué verifica |
|---|---|
| [`backend/unit/test_stream_guard.py`](backend/unit/test_stream_guard.py) | Contrato garantizado por `StreamGuard`, violaciones, watchdog y fuzzing con mutaciones. |
| [`backend/harness/test_stream.py`](backend/harness/test_stream.py) | Fixtures rotos reproducibles, validez del contrato, p50/p95 por etapa, suite `stream` y esquema de telemetría. |
| [`backend/http/test_stream_telemetry.py`](backend/http/test_stream_telemetry.py) | `POST /telemetry/stream` (solo números), resumen administrativo y stream HTTP real bajo el guardián. |
| [`frontend/unit/ndjsonParser.test.ts`](frontend/unit/ndjsonParser.test.ts) | Analizador del cliente: fixtures, cortes en cualquier byte, fuzzing, tiempos y telemetría. |
| [`frontend/e2e/stream-resilience.spec.js`](frontend/e2e/stream-resilience.spec.js) | Navegador con streams rotos: la interfaz muestra la respuesta, el aviso parcial o un error recuperable. |

| Caso | Qué verifica |
|---|---|
| `test_a_valid_stream_passes_through_unchanged` | Un stream válido pasa sin cambios. |
| `test_chunk_is_held_until_its_final_and_dropped_if_the_texts_differ` | El `chunk` espera a su `final`; si el texto difiere no se entrega. |
| `test_violations_are_reported_and_the_client_gets_a_single_error_then_done` | Cada violación se registra y el cliente recibe un solo `error` y `done`. |
| `test_events_after_the_terminal_are_dropped_but_the_delivered_final_is_kept` | El ruido tras el `final` se descarta sin perder lo entregado. |
| `test_the_client_always_sees_meta_first_even_if_the_source_never_sent_it` | El cliente ve `meta` primero aunque el origen falle antes de enviarlo. |
| `test_garbage_lines_and_missing_terminal_are_closed_with_an_error` | Líneas basura o ausencia de terminal se cierran con `error`. |
| `test_an_upstream_error_is_passed_on_and_its_done_is_kept` | Un `error` del origen se reenvía con su `done`. |
| `test_seq_is_renumbered_by_the_guard_not_trusted_from_upstream` | El `seq` lo asigna el guardián. |
| `test_fuzz_mutated_streams_always_satisfy_the_contract` | 400 streams mutados al azar siempre cumplen el contrato. |
| `test_guard_stream_delivers_valid_streams_and_closes_short_ones` | El generador entrega streams válidos y cierra los cortos. |
| `test_watchdog_emits_a_retryable_timeout_when_the_source_goes_silent` | El watchdog emite `TIMEOUT` reintentable. |
| `test_the_source_is_closed_when_the_guard_stops_early` | El origen se cierra cuando el guardián termina antes. |
| `test_broken_stream_fixtures_match_their_generator_byte_for_byte` | Los fixtures coinciden byte a byte con su generador. |
| `test_fixtures_cover_the_failure_modes_the_client_must_survive` | Los fixtures cubren BOM, CRLF, líneas rotas, truncado, duplicados, versión y más. |
| `test_the_reference_valid_stream_satisfies_the_contract_and_broken_ones_do_not` | El stream de referencia cumple el contrato y los rotos no. |
| `test_contract_checker_names_each_kind_of_problem` | El verificador nombra cada tipo de problema. |
| `test_percentiles_use_nearest_rank_and_are_na_without_data` | Percentiles por rango más cercano; `n/a` sin datos. |
| `test_streams_over_the_real_generator_are_valid_and_report_latency_per_stage` | Streams reales del generador: válidos y con latencia por etapa. |
| `test_pipeline_failures_still_produce_valid_error_streams` | Un fallo del pipeline sigue produciendo un stream válido de error. |
| `test_summary_is_na_for_an_empty_run` | Sin streams, el resumen es `n/a`. |
| `test_stream_suite_writes_a_report_with_reproducibility_metadata` | La suite escribe su informe con metadatos de reproducibilidad. |
| `test_client_telemetry_schema_is_numbers_only` | El esquema de telemetría rechaza texto, ids inválidos y rangos absurdos. |
| `test_stream_metrics_aggregate_percentiles_outcomes_and_lines_and_stay_bounded` | Agregación acotada de p50/p95, resultados y líneas inválidas. |
| `test_valid_telemetry_is_accepted_without_a_session_and_with_plain_text_bodies` | Acepta telemetría válida sin sesión y con cuerpo `text/plain`. |
| `test_telemetry_with_text_or_invalid_numbers_is_rejected_and_never_stored` | Rechaza y no guarda telemetría con texto o números inválidos. |
| `test_oversized_telemetry_is_rejected_with_413` | Rechaza cuerpos de más de 4 KB. |
| `test_summary_requires_the_admin_key_and_reports_p50_p95_per_stage` | El resumen exige clave de administración e informa p50/p95. |
| `test_the_http_stream_is_contract_valid_and_shares_the_request_id_header` | El stream HTTP cumple el contrato y comparte `X-Request-ID`. |
| cada stream de referencia produce lo que declara su manifiesto | Cada fixture produce lo declarado en `manifest.json`. |
| tolera BOM y CRLF y entrega el mismo resultado que el stream limpio | BOM y CRLF no cambian el resultado. |
| el resultado no depende de dónde se parta el stream, ni siquiera en medio de un carácter UTF-8 | Cortes en cualquier byte dan el mismo resultado. |
| un CRLF partido entre dos lecturas no genera líneas fantasma | Un CRLF partido no crea líneas fantasma. |
| fuzz: cortes aleatorios en cualquier stream de referencia dan el mismo resultado | Fuzzing de cortes sobre todos los fixtures. |
| fuzz: corrupción aleatoria nunca lanza y las cuentas son coherentes | Fuzzing de corrupción: nunca lanza y las cuentas cuadran. |
| fuzz: mezclar líneas y duplicarlas conserva el contenido y cuenta los duplicados | Fuzzing de orden y duplicados. |
| ordena por seq dentro de cada lectura y cuenta como desordenado lo que llega tarde | Orden por `seq` y cuenta de eventos tardíos. |
| sin final usa el chunk y marca la respuesta como degradada | Sin `final` se usa el `chunk` y se marca `degraded`. |
| un error terminal se informa con su código y si es reintentable, sin degradar | Error terminal con código y reintento. |
| los eventos antiguos sin v ni seq se aceptan; los de otra versión se descartan contados | Compatibilidad con eventos antiguos; versiones ajenas descartadas. |
| extractObjects separa objetos pegados, ignora basura exterior y respeta las cadenas | Reparación de objetos pegados. |
| un evento de otra petición no se mezcla con el resultado | Aislamiento por `request_id`. |
| mide los tiempos con el reloj inyectado: primer byte, primer chunk, terminal, total y etapas | Tiempos medidos con reloj inyectado. |
| la telemetría del cliente contiene solo números y el request_id, y nada de texto | La telemetría no contiene texto. |
| la telemetría usa sendBeacon con text/plain y nunca lanza ni envía sin datos | `sendBeacon` con `text/plain`, sin lanzar. |
| stream sin final marca la respuesta como degradada y conserva el texto recibido | `useChat` marca `degraded` sin `final`. |
| una línea corrupta ya no tira la respuesta: se descarta y el final se conserva | Una línea corrupta ya no tira la respuesta. |
| al terminar envía telemetría solo numérica con sendBeacon cuando el servidor informa request_id | `useChat` envía telemetría numérica. |
| aviso de respuesta parcial se muestra en la terminal solo cuando el mensaje es degradado | Aviso de respuesta parcial en la terminal. |
| stream con BOM y CRLF se muestra completo con el tiempo de respuesta | Navegador: BOM y CRLF. |
| una línea corrupta, un prefijo data: y eventos pegados no tiran la respuesta | Navegador: líneas rotas y reparables. |
| eventos duplicados o desordenados muestran la respuesta una sola vez | Navegador: duplicados y desorden. |
| sin evento final se muestra el texto recibido con aviso de respuesta parcial | Navegador: aviso de respuesta parcial. |
| un error con código se explica en español y permite reintentar | Navegador: error con código y reintento. |
| un stream vacío o de otra versión termina con un mensaje recuperable | Navegador: stream vacío o de otra versión. |
| la telemetría del stream viaja sin texto de la consulta ni de la respuesta | Navegador: la telemetría no lleva texto. |

**Mantenimiento de tests previos:** `ChatPage.test.tsx` y el mock de Playwright asumían que se podía chatear sin
sesión, pero `ChatPage` exige autenticación desde antes de este harness; ahora simulan un usuario autenticado
(`authenticated: true`).

### F5 — Comparación entre commits, feedback y calidad

`pnpm test:harness:compare --base v8 --head HEAD [--run-missing] [--ab]` compara los resultados del harness de dos
refs (`temp/harness/<sha>/<suite>.json`). Con `--run-missing` crea un `git worktree` temporal por ref (en una ruta corta
de `%TEMP%`), le superpone el harness **actual** —el código bajo prueba no cambia— y ejecuta solo las suites offline
(`retrieval`, `translation`, `stream`); `legal_qa` y los modelos reales exigen `--run-model-evals`. El informe
(`temp/harness/compare/<base>..<head>/report.{md,json}`) trae el delta macro y micro con IC por bootstrap pareado,
los casos que empeoraron o mejoraron, qué cambió (`prompt_digest`, corpus, modelos, juez), el A/B ciego con orden
invertido y el veredicto `MEJORÓ`/`IGUAL`/`EMPEORÓ`; una afirmación prohibida nueva o un caso fuera del corpus que
deja de abstenerse bloquean aunque el promedio mejore. La interfaz suma 👍/👎 con motivo (`POST /feedback`), la
página pública `/calidad` y `/calidad/admin` (solo rol admin).

| Archivo | Qué verifica |
|---|---|
| [`backend/harness/test_compare.py`](backend/harness/test_compare.py) | Bootstrap pareado, veredicto, bloqueos, A/B ciego y orquestación con `git worktree`. |
| [`backend/harness/test_publish.py`](backend/harness/test_publish.py) | Solo se publica lo medido con un sistema real, sin texto de casos. |
| [`backend/http/test_quality_feedback.py`](backend/http/test_quality_feedback.py) | Feedback, cola de candidatos, métricas publicadas y panel de administración. |
| [`frontend/component/FeedbackBar.test.tsx`](frontend/component/FeedbackBar.test.tsx) | Barra de opinión 👍/👎 con motivo y consentimiento explícito. |
| [`frontend/component/QualityPages.test.tsx`](frontend/component/QualityPages.test.tsx) | Páginas `/calidad` y `/calidad/admin`. |
| [`frontend/e2e/quality.spec.js`](frontend/e2e/quality.spec.js) | Navegador: calidad pública, administración y feedback. |

| Caso | Qué verifica |
|---|---|
| `test_digest_matches_the_cache_key_digest` | La huella del código del harness coincide con la de la clave de caché. |
| `test_paired_bootstrap_detects_a_consistent_improvement_and_a_consistent_regression` | El bootstrap pareado detecta una mejora y una regresión consistentes, respetando si menos es mejor. |
| `test_noise_is_not_reported_as_a_change_and_small_samples_make_no_claim` | El ruido no se informa como cambio y con pocos casos no se afirma nada. |
| `test_bootstrap_is_deterministic_for_a_seed_and_pairs_cases_by_id` | Con la misma semilla el IC es idéntico y solo se parean casos presentes en ambos. |
| `test_micro_pools_numerators_and_denominators_while_macro_averages_cases` | Micro suma numeradores y denominadores; macro promedia casos. |
| `test_case_changes_lists_the_cases_that_moved_most` | Lista los casos que más empeoraron y mejoraron. |
| `test_a_new_unsupported_claim_blocks_even_if_everything_else_is_unchanged` | Una afirmación prohibida nueva bloquea aunque nada más cambie. |
| `test_an_out_of_corpus_case_that_stops_abstaining_blocks` | Un caso fuera del corpus que deja de abstenerse bloquea. |
| `test_verdict_rules` | Reglas del veredicto MEJORÓ/IGUAL/EMPEORÓ, bloqueos y errores nuevos. |
| `test_meta_diff_reports_what_changed_and_flags_incomparable_measurements` | Se informan los cambios de digest, corpus y modelos; gold o juez distintos son no comparables. |
| `test_stream_validity_drop_blocks_and_latency_is_reported` | Una caída de validez del stream bloquea y se informa la latencia p95. |
| `test_end_to_end_one_hallucination_blocks_while_a_general_improvement_is_recognised` | Con informes reales del gold: una alucinación bloquea y una mejora general se reconoce. |
| `test_trials_are_blinded_crossed_and_skip_identical_answers` | Los ensayos A/B son ciegos, cruzan el orden y omiten respuestas idénticas. |
| `test_blind_ab_recognises_a_consistent_judge_and_exposes_position_bias` | El A/B distingue un juez consistente de uno con sesgo de posición. |
| `test_sign_test_matches_exact_binomial_values` | La prueba del signo coincide con valores binomiales exactos. |
| `test_results_are_reused_and_missing_ones_run_in_a_temporary_worktree_with_the_new_harness` | Los resultados se reutilizan y los faltantes se ejecutan en un worktree temporal con el harness actual. |
| `test_a_failing_run_still_removes_the_worktree` | Si la ejecución falla el worktree se elimina igual. |
| `test_unknown_refs_fail_with_a_clear_message` | Un ref inexistente falla con un mensaje claro. |
| `test_synthetic_baselines_are_published_as_not_measured_never_as_quality` | Las líneas base sintéticas se publican como no medidas. |
| `test_real_systems_publish_aggregates_without_any_case_text` | Los sistemas reales publican agregados sin texto de casos. |
| `test_published_file_round_trips_and_a_missing_file_is_reported_as_unpublished` | El archivo publicado se lee y escribe sin pérdida; si falta se informa como sin publicar. |
| `test_the_checked_in_published_file_is_honest_about_what_was_measured` | El archivo publicado en el repositorio solo declara medido lo medido con un sistema real. |
| `test_latest_comparison_picks_the_newest_report_and_ignores_broken_files` | El panel toma la comparación más reciente e ignora archivos rotos. |
| `test_feedback_requires_an_anonymous_session` | El feedback exige una sesión. |
| `test_a_thumbs_up_stores_only_labels_and_numbers` | Un 👍 guarda solo etiquetas y números. |
| `test_text_is_stored_only_when_the_person_shares_it_with_a_thumbs_down` | El texto solo se guarda con 👎 y autorización expresa. |
| `test_a_foreign_or_unreadable_conversation_never_leaks_text` | Una conversación ajena o ilegible nunca filtra texto. |
| `test_invalid_feedback_is_rejected` | Se rechaza feedback sin motivo, con campos extra o valores inválidos. |
| `test_one_vote_per_person_and_request_the_latest_wins` | Un voto por persona y petición; el último prevalece. |
| `test_the_queue_requires_admin_and_decisions_never_touch_the_gold` | La cola exige administración y aceptar no toca el gold. |
| `test_the_store_survives_a_restart_and_summarises_reasons` | El almacén sobrevive a un reinicio y resume los motivos. |
| `test_published_metrics_are_public_and_default_to_unpublished` | Las métricas publicadas son públicas y por defecto indican que no hay publicación. |
| `test_admin_overview_gathers_comparison_gold_queue_and_stream_without_secrets` | El panel reúne comparación, gold, cola y stream sin secretos. |
| `test_an_admin_user_without_the_api_key_is_accepted_and_others_are_not` | Una persona con rol admin entra sin la clave; el resto no y un fallo nunca concede acceso. |
| un pulgar arriba se envía de inmediato con el contexto numérico y sin motivo | El 👍 se envía de inmediato. |
| un pulgar abajo exige un motivo y por defecto no comparte el texto de la consulta | El 👎 exige motivo y no comparte texto por defecto. |
| compartir el texto es una casilla explícita y la cola de revisión se avisa | Compartir el texto es una casilla explícita y se avisa de la cola. |
| si el envío falla se explica y se puede reintentar sin perder lo escrito | Si falla el envío se explica y se conserva lo escrito. |
| cancelar cierra el formulario y la barra existe en quechua | Cancelar cierra el formulario; existe en quechua. |
| la terminal muestra la opinión solo con respuesta final, request_id y manejador | La terminal muestra la opinión solo con respuesta final, request_id y manejador. |
| la página pública muestra avisos, lo medido con sus valores y lo no medido con su razón | /calidad muestra avisos, lo medido y lo no medido. |
| la página pública cambia a quechua y se recupera de un error con un reintento | /calidad cambia a quechua y reintenta tras un error. |
| el panel de administración muestra regresiones, bloqueos, colas de revisión, feedback y latencia | /calidad/admin muestra regresiones, bloqueos, colas, feedback y latencia. |
| aceptar un candidato llama a la decisión y recarga el panel | Aceptar un candidato llama a la decisión y recarga. |
| sin sesión o sin rol admin el panel no pide datos y explica el acceso | Sin sesión o sin rol admin no se piden datos. |
| si el servidor responde 403 aunque el rol local diga admin, se muestra acceso restringido | El 403 del servidor prevalece sobre el rol local. |
| un fallo del servidor ofrece reintentar y el panel existe en quechua | Un fallo ofrece reintentar; el panel existe en quechua. |
| el request_id del evento meta queda en el mensaje para poder calificar la respuesta | El `request_id` del evento `meta` queda en el mensaje. |
| la página pública /calidad muestra avisos, lo medido y lo no medido, y cambia de idioma | Navegador: /calidad. |
| /calidad/admin muestra regresiones y colas a un administrador | Navegador: /calidad/admin para un administrador. |
| /calidad/admin niega el acceso a quien no es administrador | Navegador: acceso restringido. |
| el 👎 con motivo viaja a /feedback sin el texto de la consulta salvo que se autorice | Navegador: el 👎 viaja sin texto privado. |
| harness-compare pasa --base y --head al comparador sin activar modelos reales | `harness-compare` pasa `--base` y `--head` al comparador sin activar modelos reales. |

**Límites:** la comparación `legal_qa` necesita resultados de `harness-real` (o un cassette) en ambos refs; sin ellos el
informe lo declara faltante y no inventa un veredicto. Los candidatos del feedback no entran al gold: los redactan y
revisan abogados. El almacén de feedback es un archivo local (`FEEDBACK_DIR`); con disco efímero se pierde al reiniciar.

### F6 — CI

- **GitHub Actions** (`.github/workflows/`): `ci.yml` corre en cada pull request `pnpm test`, `pnpm test:harness` y los E2E
  con API simulada, sin secretos ni proveedores; `harness-real.yml` corre `pnpm test:harness:real --run-model-evals` y
  `pnpm test:harness:compare ... --ab` cada noche, con la etiqueta `eval` en un PR del propio repositorio o a mano.

| Archivo | Qué verifica |
|---|---|
| [`scripts/unit/test_harness_automation_contract.py`](scripts/unit/test_harness_automation_contract.py) | Los workflows cumplen las reglas del plan: sin proveedores en los PR y evaluación real con puerta explícita. |

| Caso | Qué verifica |
|---|---|
| `test_pull_request_ci_runs_the_offline_suites_and_never_touches_providers` | El CI de los PR ejecuta las suites offline y no usa secretos ni `--run-model-evals`. |
| `test_real_evaluation_is_gated_by_schedule_label_or_manual_dispatch_and_always_confirms_cost` | La evaluación real solo corre por cron, etiqueta `eval` de un PR propio o a mano, siempre con `--run-model-evals`. |

**Estado del CI:** `pnpm test` incluye hoy 4 pruebas de `test_google_oauth.py` y `dev-full.test.mjs` que fallan en la base
(v8) por causas ajenas al harness; el CI las mostrará en rojo hasta que se corrijan.
