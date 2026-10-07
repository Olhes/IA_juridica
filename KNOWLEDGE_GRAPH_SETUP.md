# Corpus y Knowledge Graph — rama v8

Actualización: **2026-10-06**. LightRAG recupera documentos y relaciones; su
presencia no garantiza respuestas correctas, fuentes oficiales ni vigencia normativa.
El número de documentos/chunks depende de tus artefactos, no de una cifra fija del README.

## Preparar un corpus local

En `backend/.env`: `LOAD_LOCAL_KG=true`, `NEO4J_ENABLED=false`.
El opt-in habilita carga de artefactos locales existentes; no genera por sí solo
un corpus nuevo ni asegura su compatibilidad con embeddings/modelos actuales.
Guarda backup antes de reprocesar o regenerar índices.

Rutas usadas por `main.py`, ancladas al directorio backend:

| Ruta | Contenido |
|---|---|
| `backend/docs/raw_pdfs/` | PDF de entrada |
| `backend/docs/processed/` | Markdown procesado |
| `backend/docs/source_evidence/` | Evidencia inmutable publicada por upload |
| `backend/docs/knowledge_graph/` | Artefactos LightRAG/document store |

Los nombres internos pueden incluir `documents_store.json`,
`kv_store_text_chunks.json`, `kv_store_full_docs.json`, archivos vectoriales
`vdb_*.json` y grafo `graph_chunk_entity_relation.graphml`.
No edites manualmente un solo artefacto suponiendo consistencia del resto.
Las variables de rutas de Settings no redirigen automáticamente todas las rutas
ancladas de la API; comprueba consumidores antes de mover datos.

## Ingesta y estados

`POST /upload-pdf` requiere admin habilitado y `X-API-Key` independiente.
Valida tipo, tamaño y firma, conserva Markdown/PDF con evidencia SHA-256 e intenta
ingesta RAG. El resultado `graph_write_state=unverified` significa que la escritura
del grafo no queda certificada por el recibo de fuente. `POST /batch-process`
procesa entradas locales; no implementa el pipeline cloud propuesto.

Comprueba `/health` para componentes y `/ready` para disponibilidad del corpus.
Durante carga/fallo no anuncies listo solo porque responde HTTP.
Cuando el retrieval falla la consulta devuelve 503; si no recupera documentos,
el pipeline produce abstención explícita y no inventa fuentes.

## Neo4j opcional

Settings expone `NEO4J_ENABLED`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` y
`NEO4J_DATABASE`. Configurar estas variables no es una migración automática de
los artefactos locales: verifica almacenamiento seleccionado, conectividad,
compatibilidad y corpus cargado. Guarda secretos fuera de Git.
No se promete mejor precisión o rendimiento solo por elegir Neo4j.

## Evaluar sin confundir objetivos

- Unitarios del chunker: estructura, orden, metadatos y errores, offline.
- Contratos RAG/HTTP: autoridad de evidencias, abstención, validación y errores.
- Evaluación de calidad: preguntas con referencias y fuentes identificables;
  comparar estrategias manteniendo constante retrieval/generador y presupuesto.
  [RAGAS Context Precision/Recall](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/) puede complementar las pruebas; no se obtiene
  esa evidencia de porcentajes de cobertura ni de mocks de embeddings.

Consulta [tests](tests/README.md), [validación](backend/VALIDATION_GUIDE.md),
[evaluación SAT/Graph](docs/SAT-GRAPH-EVALUATION-PLAN.md) y [API](API_DOC.md).
Los planes SAT/Graph siguen siendo propuestas salvo implementación demostrada;
ingesta exitosa no equivale a corpus jurídico auditado.
