# Configuración del Grafo de Conocimiento

## Visión General

IA Jurídica utiliza LightRAG para gestionar un grafo de conocimiento que permite respuestas más precisas y contextualizadas basadas en documentos legales procesados.

## Modos de Almacenamiento

### 1. Grafo Local (NetworkX) - Recomendado para Desarrollo

**Configuración en `backend/.env`:**
```env
LOAD_LOCAL_KG=true
NEO4J_ENABLED=false
```

**Ventajas:**
- ✅ No requiere dependencias externas
- ✅ Más rápido para desarrollo
- ✅ Incluye 18 documentos legales pre-procesados
- ✅ Almacenamiento en archivos JSON locales

**Estructura de archivos:**
```
backend/docs/knowledge_graph/
├── documents_store.json          # Metadatos de documentos
├── graph_chunk_entity_relation.graphml  # Grafo en formato GraphML
├── kv_store_doc_status.json      # Estado de procesamiento
├── kv_store_entity_chunks.json   # Entidades por chunk
├── kv_store_full_docs.json       # Documentos completos
├── kv_store_full_entities.json  # Entidades completas
├── kv_store_full_relations.json # Relaciones completas
├── kv_store_relation_chunks.json # Relaciones por chunk
├── kv_store_text_chunks.json     # Chunks de texto
├── vdb_chunks.json              # Embeddings de chunks
├── vdb_entities.json            # Embeddings de entidades
└── vdb_relationships.json       # Embeddings de relaciones
```

**Documentos incluidos:**
- Ley 30364 (violencia familiar)
- Pensión de alimentos (guías, normativa, jurisprudencia)
- Régimen de visitas y tenencia
- Manuales en quechua
- Constitución Política del Perú

### 2. Neo4j Aura - Opcional para Producción

**Configuración en `backend/.env`:**
```env
LOAD_LOCAL_KG=false
NEO4J_ENABLED=true
NEO4J_URI=neo4j+s://tu-instancia-aura.databases.neo4j.io
NEO4J_USER=tu_usuario
NEO4J_PASSWORD=tu_password
NEO4J_DATABASE=tu_database
```

**Ventajas:**
- ✅ Escalable para grandes volúmenes de documentos
- ✅ Almacenamiento en la nube
- ✅ Consultas más eficientes en grafos grandes
- ✅ Visualización con Neo4j Browser

**Configuración de Neo4j Aura:**
1. Crear cuenta en [Neo4j Aura](https://neo4j.com/cloud/aura/)
2. Crear instancia gratuita (Free tier)
3. Obtener URI, usuario y contraseña
4. Configurar variables de entorno

## Inicialización del Grafo

### Al iniciar el servidor:

El sistema carga automáticamente los documentos del grafo local si `LOAD_LOCAL_KG=true`:

```
2026-08-09 08:03:40 | INFO | Cargados 18 documentos desde docs\knowledge_graph\documents_store.json
2026-08-09 08:03:40 | INFO | LegalRAG Engine inicializado en ./docs/knowledge_graph (18 documentos cargados del disco)
```

### Proceso de carga de documentos:

1. **Carga de metadatos**: Lee `documents_store.json`
2. **Inicialización de LightRAG**: Configura el motor RAG
3. **Carga de embeddings**: Vectores pre-calculados
4. **Inicialización de storages**: Prepara para consultas

## Verificación del Funcionamiento

### Verificar logs de inicio:

```bash
# Deberías ver estos mensajes:
"LegalRAG Engine inicializado en ./docs/knowledge_graph (18 documentos cargados del disco)"
"LightRAG inicializado con Cohere (graph_storage=NetworkX (local))"
```

### Verificar conexión al grafo:

Al hacer una consulta legal, deberías ver en los logs:

```
INFO: Query nodes: [entidades relevantes]
INFO: Query edges: [relaciones relevantes]
INFO: Local query: X entites, Y relations
```

### Si no funciona correctamente:

**Problema: "No query context could be built"**
- El grafo no está inicializado correctamente
- Verifica que `LOAD_LOCAL_KG=true`
- Reinicia el servidor

**Problema: Respuestas genéricas sin usar documentos**
- LightRAG no está encontrando información relevante
- Verifica que los documentos estén en `backend/docs/knowledge_graph/`
- Revisa los logs de consultas

## Procesamiento de Nuevos Documentos

### Agregar documentos al grafo:

1. Coloca PDFs en `backend/docs/raw_pdfs/`
2. Usa el endpoint de ingestión:
```bash
curl -X POST http://localhost:8000/upload-pdf -F "file=@documento.pdf"
```

3. Los documentos se procesan automáticamente y se agregan al grafo

### Documentos procesados disponibles:

Los documentos procesados se encuentran en:
- `backend/docs/processed/` - Markdown procesados
- `backend/docs/knowledge_graph/` - Grafo de conocimiento

## Estilo de Respuestas

El sistema utiliza prompt templates configurados para respuestas conversacionales:

- **Estilo natural**: Similar a ChatGPT/Gemini
- **Sin formatos rígidos**: Evita listas estructuradas innecesarias
- **Contextual**: Adapta respuestas según cada situación
- **Empático**: Tono comprensivo y culturalmente sensible

Los templates se encuentran en `backend/context/prompt_templates.py` y pueden personalizarse según necesidades específicas.

## Solución de Problemas

### Cambiar entre modos:

**De local a Neo4j:**
```env
LOAD_LOCAL_KG=false
NEO4J_ENABLED=true
# Configurar credenciales Neo4j
```

**De Neo4j a local:**
```env
LOAD_LOCAL_KG=true
NEO4J_ENABLED=false
```

### Regenerar el grafo:

Si el grafo está corrupto o deseas reconstruirlo:

```bash
# Eliminar archivos del grafo
rm -rf backend/docs/knowledge_graph/*

# Reiniciar servidor
cd backend
uv run main.py
```

### Verificar integridad del grafo:

```bash
# Ver documentos cargados
cat backend/docs/knowledge_graph/documents_store.json

# Ver estadísticas
wc -l backend/docs/knowledge_graph/*.json
```

## Rendimiento

### Grafo Local:
- **Tiempo de carga**: ~1-2 segundos
- **Consulta**: ~2-5 segundos
- **Memoria**: ~100-200 MB

### Neo4j Aura:
- **Tiempo de carga**: ~2-3 segundos
- **Consulta**: ~1-3 segundos
- **Memoria**: Variable según tamaño del grafo

## Recursos Adicionales

- [LightRAG Documentation](https://github.com/HKUDS/LightRAG)
- [Neo4j Aura](https://neo4j.com/cloud/aura/)
- [Cohere API](https://docs.cohere.com/)
- Documentos legales procesados en `backend/docs/processed_backup/`
