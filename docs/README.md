# Documentación — IA Jurídica

Índice de la documentación Markdown del repo. `README.md` de raíz se queda donde está.
`backend/docs/` **no es documentación**: son datos de runtime (raw_pdfs, processed, knowledge_graph) que el código lee vía `DOCS_ROOT_DIR`/`RAW_PDF_DIR`/etc. — **no mover**.

| Documento | Qué explica | A quién le sirve |
|---|---|---|
| `docs/api/API_DOC.md` | Referencia completa de endpoints FastAPI (base URL, auth, `/legal-query`, `/upload-pdf`, streaming, esquemas) | Frontend y consumidores de la API |
| `docs/architecture/KNOWLEDGE_GRAPH_SETUP.md` | Setup del grafo LightRAG (local NetworkX vs Neo4j, vars `LOAD_LOCAL_KG`, regeneración, verificación) | Backend / quien levanta el RAG |
| `docs/architecture/CLOUD_PDF_PIPELINE.md` | Propuesta de pipeline PDF en la nube (object storage + API orquestadora, sin versionar PDFs) | Backend / DevOps |
| `docs/operations/DEPLOY_RENDER.md` | Despliegue en Render (RAM, `LOAD_LOCAL_KG=false`, Neo4j Aura en free tier) | DevOps / deploys |
| `docs/operations/POSTGRES_CONNECTION_ISSUES.md` | Bitácora de errores de conexión PostgreSQL (puerto 5433 vs 5432 local, adapters legacy) y soluciones | Backend / dev local con Docker |
| `docs/operations/SECURITY.md` | Modelo de seguridad (sesión anónima HMAC, cookies, uploads, migración manual segura) | Backend / seguridad |
| `docs/evaluations/CHANGELOG_MIGRACION_COHERE.md` | Changelog de migración a Cohere (`command-r7b`, `embed-multilingual-v3.0`, rerank, regeneración de vectores) | Backend / RAG |
| `backend/VALIDATION_GUIDE.md` _(en su sitio, junto al código)_ | Pipeline de validación de respuestas del LLM en `POST /legal-query` | Backend / QA |
| `frontend/README_ARCHITECTURE.md` _(en su sitio, junto al código)_ | Arquitectura Next.js (domain/application/infrastructure/presentation) | Frontend |

## Cambios de reorganización (2026-09-13)

- Cada MD suelto de raíz se movió a su categoría (ver tabla viejo→nuevo en el commit).
- `docs/SECURITY.md` → `docs/operations/SECURITY.md`.
- `docs/knowledge_graph/` (JSONs + GraphML, artefactos de runtime versionados por error) → `knowledge-graph/` en raíz, nombre honesto. **No es el grafo vivo**: el canónico que lee el código es `backend/docs/knowledge_graph/` (`BASE_DIR / "docs"` en `backend/main.py`, `KNOWLEDGE_GRAPH_DIR` en `backend/config/settings.py`). Ver `knowledge-graph/README.md`.
