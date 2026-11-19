# Pruebas y evaluación

Desde la raíz, con Python compatible con [pyproject.toml](../pyproject.toml), uv,
Node y `pnpm` instalados:

```powershell
uv sync --frozen --extra dev --inexact
pnpm install --frozen-lockfile
pnpm test
```

La suite predeterminada ejecuta Python, scripts Node y frontend sin arrancar
Docker ni llamar a modelos reales. Las evaluaciones con proveedores requieren
consentimiento explícito.

## Comandos por objetivo

La prueba `frontend/component/AuthModal.test.tsx`,
`modal de acceso ofrece Google y cierra por cancelación`, verifica la acción
de Google y el cierre nativo, sin mostrar el formulario de contraseña inactivo.

| Objetivo | Comando |
|---|---|
| Backend / frontend | `pnpm test:backend` / `pnpm test:frontend` |
| Scripts Python y Node / solo Node | `pnpm test:scripts` / `pnpm test:node` |
| Cobertura local | `pnpm test:coverage` |
| Publicar cobertura y resultados | `pnpm sonar` |
| Navegador con API simulada | `pnpm test:e2e` |
| Evaluador / harness offline | `pnpm test:quality:offline` / `pnpm test:harness` |

### Descubrir o seleccionar casos

La fuente del inventario son las suites, no una lista manual:

```powershell
pnpm test:python --collect-only
pnpm test:python tests/backend/unit -k translation
pnpm test:frontend -t "NDJSON"
pnpm test:e2e --list
```

Agrega las pruebas a `tests/backend/<tipo>/`, `tests/frontend/<tipo>/` o
`tests/scripts/unit/`. Usa nombres que indiquen el comportamiento y explica
solo el motivo de una simulación o restricción que no sea evidente. No ocultes
regresiones con skips o umbrales más laxos.

## Cobertura y SonarQube

`pnpm test:coverage` genera `coverage.xml`, `temp/sonar-reports/pytest.xml`
y `temp/sonar-reports/frontend-coverage/lcov.info`. `pnpm sonar` publica los
informes si pasan las suites. Consulta la [guía SonarQube](../docs/SONARQUBE.md)
para arranque, credenciales, permisos de Windows y Quality Gate.

## E2E de navegador: simulado y real

Instala Chromium con `pnpm exec playwright install chromium` o, en Windows,
usa `PLAYWRIGHT_CHANNEL=msedge` en el entorno. El modo simulado arranca Next
en `localhost:3100`; deja libre el puerto.

Para el modo real, arranca primero una instalación **local de prueba** con
frontend, backend, PostgreSQL y Redis. Configura `PLAYWRIGHT_TARGET_URL` y
`PLAYWRIGHT_API_URL` con direcciones loopback y ejecuta
`pnpm test:e2e:real --run-model-evals`. Puede facturar; no uses cuentas, datos
personales ni entornos de producción. Verifica el flujo HTTP, no la calidad jurídica.

## Calidad real del modelo

- **Calidad legacy:** `pnpm test:quality --run-model-evals` fue retirado.
  Usa el modo NVIDIA + Voyage sin juez indicado abajo.
- **Pipeline real:** `pnpm test:harness:real --run-model-evals` ejecuta
  respuesta jurídica, recuperación, traducción y streaming. Consulta el
  [gold y sus criterios](backend/fixtures/gold/README.md) y el
  [plan del harness](../docs/HARNESS-IMPLEMENTATION-PLAN.md) para el alcance.
  Para comparar dos revisiones, usa `pnpm test:harness:compare --base <ref> --head <ref>`.

- **NVIDIA + Voyage, sin juez:** con `NVIDIA_API_KEY` y `VOYAGE_API_KEY` en `backend/.env`, ejecuta desde PowerShell:
  ```powershell
  $env:PYTHONPATH='backend'
  uv run --frozen --extra dev --inexact --with ragas==0.4.3 --with 'langchain-community<0.4' --with rapidfuzz python -m evaluation.harness.runner legal_qa --provider nvidia-voyage --limit 2 --samples 1 --delay-seconds 20 --run-model-evals
  ```
  Usa un pipeline experimental, no el de producción; envía consultas y fragmentos del corpus a ambos proveedores. RAGAS compara texto con hechos de referencia sin LLM; no mide equivalencia semántica. El cassette y los informes quedan en `temp/harness/` y pueden contener información sensible. Si se agota la cuota, vuelve a ejecutar el comando tras el reinicio diario UTC para reutilizar lo grabado. `/evaluate-system?provider=nvidia-voyage&limit=2` reproduce el cassette, sin llamadas externas.

Los modos reales usan red y pueden facturar; el flag no fija un presupuesto.
Las puntuaciones no certifican exactitud jurídica ni calidad lingüística.
Compara solo resultados obtenidos con casos, modelos, métricas y versiones
compatibles. Los informes pueden incluir contexto y respuestas: trátalos como sensibles.

## Diagnósticos manuales

No forman parte de CI ni del informe de SonarQube:

| Archivo | Uso |
|---|---|
| `backend/manual/diagnose_connection.py` | Conectividad local PostgreSQL/Redis. |
| `backend/manual/diagnose_pg_connection.py` | Comparación heredada de conexiones psycopg. |
| `backend/manual/diagnose_postgres.py` | Comparación heredada de clientes PostgreSQL. |
| `backend/manual/diagnose_settings_connection.py` | Conexión con la configuración del backend. |
| `backend/manual/benchmark_optimized_pipeline.py` | No ejecutable: faltan módulos. |
| `backend/manual/benchmark_real_performance.py` | No ejecutar sobre datos reales: borra resultados y backups. |

Para investigar la ingesta y recuperación, consulta los
[experimentos SAT-Graph](../docs/SAT-GRAPH-EXPERIMENTS.md) y la
[guía de ingesta](../docs/SAT-GRAPH-INGESTION.md). Los inventarios y resultados
históricos de esta guía quedan en Git.
