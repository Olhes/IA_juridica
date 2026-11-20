# Corpus SAT-Graph en v8

SAT-Graph usa SurrealDB para guardar el corpus normativo versionado que consulta
el asistente. El corpus conserva documentos, estructura, relaciones y evidencia
para recuperar referencias a las fuentes.

## Inicializar el corpus

Desde la raíz del repositorio, `pnpm dev:full` levanta SurrealDB y Redis,
inicializa el corpus y espera a `/ready`. Para preparar únicamente los servicios
y el corpus:

```bash
docker compose up -d --wait surreal redis
uv run python backend/scripts/bootstrap_sat_corpus.py
```

El inicializador importa `backend/docs/sat_graph.surql.gz` si la base está
vacía y comprueba las siete tablas antes de confirmar la operación. Si ya hay
revisiones publicadas, usa el corpus existente. El runner de Azure aplica el
mismo flujo con un volumen persistente. [Operación en Azure](deploy/azure/README.md).

| Parámetro | Valor predeterminado |
| --- | --- |
| Motor | `RAG_ENGINE=sat` |
| Persistencia | `DATABASE_BACKEND=surrealdb` |
| Endpoint desde el host local | `ws://127.0.0.1:8010/rpc` |
| Endpoint dentro de la red de Azure Compose | `ws://surreal:8000/rpc` |
| Namespace y base del corpus | `ia_juridica` / `sat_graph` |

## Ingesta, revisión y recuperación

- `POST /upload-pdf` requiere acceso administrativo. Valida el archivo y registra
  evidencia SHA-256 para la revisión del corpus.
- `pnpm sat:review` abre el editor local. La publicación editorial incorpora las
  revisiones al corpus consultable. [Editor de SAT-Graph](docs/SAT_CORPUS_EDITOR.md).
- `/ready` verifica si el corpus está disponible. Si falta, devuelve HTTP 503.
- El asistente puede abstenerse cuando la consulta carece de evidencia recuperada.
  [Contratos de la API](API_DOC.md) · [Validación de respuestas](backend/VALIDATION_GUIDE.md).

Para recuperar un respaldo histórico de PostgreSQL, consulta el
[migrador de SAT](backend/scripts/migrate_postgres_to_surrealdb.py). La opción
`--apply --sat-only` importa a tablas vacías. La opción
`--verify-only --sat-only` compara datos sin escribir.
