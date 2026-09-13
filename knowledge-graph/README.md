# knowledge-graph/ — exportación histórica (no es el grafo vivo)

Esta carpeta viene de `docs/knowledge_graph/` (movida aquí el 2026-09-13 porque `docs/` debe contener solo documentación Markdown, no artefactos de runtime).

- **Contenido**: JSONs (`vdb_*`, `kv_store_*`, `documents_store.json`) + `graph_chunk_entity_relation.graphml` — exportación del grafo LightRAG.
- **Canónico**: el código **no lee esta carpeta**. Lee `backend/docs/knowledge_graph/` (ver `BASE_DIR / "docs"` en `backend/main.py` y `KNOWLEDGE_GRAPH_DIR` en `backend/config/settings.py`).
- **Regla**: no agregar documentación aquí; si se necesita una exportación fresca, regenerar desde el backend y no mezclarla con `docs/`.
