# 📋 Plan de Migración: Cohere + Context Engineering + LightRAG

**Objetivo:** Migrar el sistema actual a una arquitectura con embeddings reales (Cohere), chunking inteligente, prompts culturales y reranking avanzado.

**Estimación total:** 15-20 horas de desarrollo

---

## 🎯 FASE 1: Configuración Base (2-3 horas)

### ✅ Tarea 1.1: Instalar dependencias
**Archivo:** `requirements.txt`
```bash
# Agregar al requirements.txt
cohere>=4.37
sentence-transformers>=2.2.2  # Opcional: para embeddings locales
numpy>=1.24.0
```

**Ejecutar:**
```bash
pip install -r requirements.txt
```

**Validación:**
```python
import cohere
client = cohere.Client(api_key="test")
print("✅ Cohere instalado")
```

---

### ✅ Tarea 1.2: Configurar variables de entorno
**Archivo:** `.env`
```bash
# Agregar estas variables
COHERE_API_KEY=tu_api_key_aqui

# Modelos Cohere
COHERE_EMBED_MODEL=embed-multilingual-v3.0
COHERE_RERANK_MODEL=rerank-multilingual-v3.0
COHERE_LLM_MODEL=command-r-plus

# RAG Settings
EMBEDDING_DIM=1024  # embed-multilingual-v3.0 usa 1024 dims
RERANK_TOP_K=5
RERANK_CANDIDATES=50
```

**Validación:**
```bash
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('COHERE_API_KEY'))"
```

---

### ✅ Tarea 1.3: Actualizar configuración
**Archivo:** `backend/config/settings.py`
```python
# Agregar estas líneas
class Settings(BaseSettings):
    # ... existing fields ...
    
    # Cohere Configuration
    COHERE_API_KEY: str = ""
    COHERE_EMBED_MODEL: str = "embed-multilingual-v3.0"
    COHERE_RERANK_MODEL: str = "rerank-multilingual-v3.0"
    COHERE_LLM_MODEL: str = "command-r-plus"
    
    # RAG con Cohere
    EMBEDDING_DIM: int = 1024  # Actualizar de 768 a 1024
    RERANK_TOP_K: int = 5
    RERANK_CANDIDATES: int = 50
```

**Validación:**
```python
from config.settings import Settings
settings = Settings()
assert settings.EMBEDDING_DIM == 1024
print("✅ Configuración actualizada")
```

---

## 🔧 FASE 2: Integrar Cohere en LightRAG (4-5 horas)

### ✅ Tarea 2.1: Reemplazar función de embeddings
**Archivo:** `backend/rag/lightrag_engine.py`

**Buscar líneas 40-58** (función `embedding_func` simulada)

**Reemplazar con:**
```python
def _initialize_lightrag(self):
    """Inicializa LightRAG con embeddings REALES de Cohere"""
    
    # ✅ Inicializar cliente Cohere
    import cohere
    self.cohere_client = cohere.AsyncClient(
        api_key=os.getenv('COHERE_API_KEY')
    )
    
    # ✅ FUNCIÓN DE EMBEDDING REAL
    async def cohere_embedding_func(texts: List[str]):
        """Genera embeddings con Cohere embed-multilingual-v3.0"""
        try:
            response = await self.cohere_client.embed(
                texts=texts,
                model="embed-multilingual-v3.0",
                input_type="search_document",
                embedding_types=["float"]
            )
            
            embeddings = response.embeddings.float
            logger.info(f"✅ {len(embeddings)} embeddings generados con Cohere")
            
            return np.array(embeddings, dtype=np.float32)
            
        except Exception as e:
            logger.error(f"❌ Error generando embeddings: {e}")
            raise
    
    # ✅ FUNCIÓN LLM REAL (para grafo de conocimiento)
    async def cohere_llm_func(prompt: str, **kwargs) -> str:
        """Procesa con Cohere Command-R"""
        try:
            response = await self.cohere_client.chat(
                model="command-r",
                message=prompt,
                temperature=0.3,
                max_tokens=500
            )
            
            return response.text
            
        except Exception as e:
            logger.error(f"❌ Error en LLM: {e}")
            return ""
    
    # ✅ Inicializar LightRAG
    self.rag = LightRAG(
        working_dir=str(self.working_dir),
        llm_model_func=cohere_llm_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=1024,  # embed-multilingual-v3.0
            max_token_size=8192,
            func=cohere_embedding_func
        )
    )
    
    logger.info("✅ LightRAG inicializado con Cohere")
```

**Validación:**
```python
# Test básico
engine = LegalRAGEngine()
await engine.initialize_storages()
await engine.add_document(
    content="Test de embedding con Cohere",
    metadata={"test": True},
    document_id="test_1"
)
print("✅ Embeddings funcionando")
```

---

### ✅ Tarea 2.2: Implementar búsqueda con Rerank
**Archivo:** `backend/rag/lightrag_engine.py`

**Agregar nuevo método después de la línea 150:**
```python
async def query_with_rerank(
    self, 
    query: str, 
    top_k: int = 5,
    rerank_top_n: int = 50
) -> Dict[str, Any]:
    """
    Búsqueda avanzada con Cohere Rerank
    
    Args:
        query: Consulta del usuario
        top_k: Documentos finales (después de rerank)
        rerank_top_n: Candidatos iniciales de LightRAG
    """
    try:
        # PASO 1: Búsqueda inicial con LightRAG
        logger.info(f"🔍 Buscando {rerank_top_n} candidatos...")
        
        if LIGHTRAG_AVAILABLE and self.rag is not None:
            await self._ensure_storages_initialized()
            
            raw_results = await self.rag.aquery(
                query,
                param=QueryParam(
                    mode="hybrid",
                    top_k=rerank_top_n
                )
            )
            
            candidate_docs = self._parse_lightrag_results(raw_results)
        else:
            candidate_docs = self._local_search(query, rerank_top_n)
        
        if not candidate_docs:
            return {
                "query": query,
                "documents": [],
                "sources": []
            }
        
        logger.info(f"✅ {len(candidate_docs)} candidatos encontrados")
        
        # PASO 2: Reranking con Cohere
        logger.info(f"�� Re-rankeando con Cohere...")
        
        texts_to_rerank = [doc["content"] for doc in candidate_docs]
        
        rerank_response = await self.cohere_client.rerank(
            query=query,
            documents=texts_to_rerank,
            model="rerank-multilingual-v3.0",
            top_n=top_k,
            return_documents=True
        )
        
        # PASO 3: Construir respuesta
        top_docs = []
        for result in rerank_response.results:
            doc_idx = result.index
            top_docs.append({
                "content": candidate_docs[doc_idx]["content"],
                "metadata": candidate_docs[doc_idx]["metadata"],
                "relevance_score": result.relevance_score,
                "document_id": candidate_docs[doc_idx].get("document_id", "")
            })
        
        logger.info(f"✅ Top {len(top_docs)} re-rankeados")
        
        return {
            "query": query,
            "documents": top_docs,
            "sources": [doc["metadata"] for doc in top_docs],
            "total_candidates": len(candidate_docs),
            "rerank_scores": [doc["relevance_score"] for doc in top_docs]
        }
        
    except Exception as e:
        logger.error(f"❌ Error en query_with_rerank: {e}")
        raise

def _parse_lightrag_results(self, raw_results: str) -> List[Dict[str, Any]]:
    """Parsea resultados de LightRAG"""
    docs = []
    for doc_id, doc_data in self.documents.items():
        docs.append({
            "content": doc_data["content"],
            "metadata": doc_data["metadata"],
            "document_id": doc_id
        })
    return docs[:50]

def _local_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
    """Búsqueda local fallback"""
    results = []
    query_lower = query.lower()
    
    for doc_id, doc_data in self.documents.items():
        content_lower = doc_data["content"].lower()
        common_words = set(query_lower.split()) & set(content_lower.split())
        score = len(common_words) / max(len(set(query_lower.split())), 1)
        
        if score > 0.1:
            results.append({
                "content": doc_data["content"],
                "metadata": doc_data["metadata"],
                "document_id": doc_id,
                "score": score
            })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
```

**Validación:**
```python
engine = LegalRAGEngine()
await engine.initialize_storages()

# Agregar docs de prueba
await engine.add_document("Ley de violencia familiar...", {}, "ley_1")
await engine.add_document("Pensión de alimentos...", {}, "ley_2")

# Buscar con rerank
result = await engine.query_with_rerank("violencia familiar", top_k=5)
assert len(result["documents"]) > 0
print(f"✅ Rerank funcionando: {result['rerank_scores']}")
```

---

## 🧩 FASE 3: Context Engineering (5-6 horas)

### ✅ Tarea 3.1: Implementar chunking inteligente
**Archivo:** `backend/context/chunking_strategies.py`

**Agregar después de línea 72:**
```python
class ContextualChunker:
    """Chunker con embeddings de Cohere"""
    
    def __init__(self):
        self.strategy = LegalChunkingStrategy()
        import cohere
        self.cohere_client = cohere.AsyncClient(
            api_key=os.getenv('COHERE_API_KEY')
        )
    
    async def chunk_and_embed(
        self,
        content: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Divide en chunks Y genera embeddings"""
        
        # PASO 1: Chunking estructurado
        chunks = self.strategy.chunk_by_legal_structure(
            content,
            document_type=metadata.get("document_type")
        )
        
        # PASO 2: Generar embeddings
        texts = [chunk["content"] for chunk in chunks]
        
        response = await self.cohere_client.embed(
            texts=texts,
            model="embed-multilingual-v3.0",
            input_type="search_document",
            embedding_types=["float"]
        )
        
        # PASO 3: Agregar embeddings
        for i, chunk in enumerate(chunks):
            chunk["embedding"] = response.embeddings.float[i]
            chunk["embedding_model"] = "embed-multilingual-v3.0"
            chunk["metadata"] = metadata
        
        logger.info(f"✅ {len(chunks)} chunks embebidos")
        return chunks
```

**Validación:**
```python
chunker = ContextualChunker()
chunks = await chunker.chunk_and_embed(
    "Artículo 1: Test...\nArtículo 2: Test...",
    {"document_type": "ley"}
)
assert len(chunks) > 0
assert "embedding" in chunks[0]
print(f"✅ Chunking con embeddings: {len(chunks)} chunks")
```

---

### ✅ Tarea 3.2: Implementar PromptManager
**Archivo:** `backend/context/prompt_templates.py`

**Agregar después de línea 77:**
```python
class PromptManager:
    """Gestor de prompts con variables dinámicas"""
    
    def __init__(self):
        self.templates = LegalPromptTemplates()
    
    def build_prompt_for_cohere(
        self,
        prompt_type: PromptType,
        query: str,
        context_docs: List[Dict[str, Any]],
        language: str = "spanish",
        user_location: Optional[str] = None
    ) -> str:
        """Construye prompt optimizado para Cohere"""
        
        # Obtener template
        base_template = self.templates.get_template(prompt_type, language)
        
        # Formatear documentos
        context_text = self._format_documents(context_docs)
        
        # Recursos locales
        local_resources = ""
        if user_location:
            local_resources = self._get_local_resources(user_location)
        
        # Construir prompt final
        final_prompt = f"""
{base_template}

=== CONTEXTO LEGAL RELEVANTE ===
{context_text}

=== RECURSOS LOCALES ===
{local_resources}

=== CONSULTA DEL USUARIO ===
{query}

=== INSTRUCCIONES ===
Responde en {language} usando el contexto legal.
Cita artículos específicos.
Mantén sensibilidad cultural.
"""
        
        return final_prompt
    
    def _format_documents(self, docs: List[Dict]) -> str:
        """Formatea documentos para el prompt"""
        formatted = []
        for i, doc in enumerate(docs, 1):
            formatted.append(f"""
Documento {i}:
Fuente: {doc.get('metadata', {}).get('title', 'N/A')}
Relevancia: {doc.get('relevance_score', 0):.2f}

{doc['content'][:500]}...
---
""")
        return "\n".join(formatted)
    
    def _get_local_resources(self, location: str) -> str:
        """Recursos por ubicación"""
        resources = {
            "cusco": "Juzgado: ...\nComisaría: ...",
            "lima": "Juzgado: ...\nComisaría: ..."
        }
        return resources.get(location.lower(), "Recursos generales")
```

---

### ✅ Tarea 3.3: Implementar ContextEngineer
**Archivo:** `backend/context/context_engineering.py`

**Agregar después de línea 78:**
```python
async def build_legal_prompt(
    self,
    query: str,
    documents: List[Dict[str, Any]],
    language: str = "spanish",
    response_type: str = "general"
) -> str:
    """Construye prompt optimizado para Cohere"""
    
    # Clasificar consulta
    query_type = self._classify_query_type(query)
    prompt_type = self._map_to_prompt_type(query_type)
    
    # Detectar ubicación
    location = self._extract_location(query)
    
    # Construir prompt
    optimized_prompt = self.prompt_manager.build_prompt_for_cohere(
        prompt_type=prompt_type,
        query=query,
        context_docs=documents,
        language=language,
        user_location=location
    )
    
    return optimized_prompt

def _classify_query_type(self, query: str) -> str:
    """Clasifica tipo de consulta"""
    q = query.lower()
    if any(w in q for w in ['golpe', 'violencia', 'maltrato']):
        return "violence"
    elif any(w in q for w in ['pensión', 'alimentos']):
        return "pension"
    elif any(w in q for w in ['dni', 'documento']):
        return "identity"
    return "general"

def _map_to_prompt_type(self, query_type: str) -> PromptType:
    """Mapea a PromptType"""
    mapping = {
        "violence": PromptType.VIOLENCE_FAMILY,
        "pension": PromptType.PENSION_FOOD,
        "identity": PromptType.IDENTITY_RIGHTS,
        "general": PromptType.GENERAL_LEGAL
    }
    return mapping.get(query_type, PromptType.GENERAL_LEGAL)

def _extract_location(self, query: str) -> Optional[str]:
    """Extrae ubicación"""
    locations = ["cusco", "puno", "ayacucho", "lima"]
    for loc in locations:
        if loc in query.lower():
            return loc
    return None
```

---

## 🤖 FASE 4: Integrar en Pydantic Agents (3-4 horas)

### ✅ Tarea 4.1: Actualizar LegalAgent
**Archivo:** `backend/agents/pydantic_agents.py`

**Agregar después de `__init__`:**
```python
def __init__(self):
    # Cliente Cohere
    import cohere
    self.cohere_client = cohere.AsyncClient(
        api_key=os.getenv('COHERE_API_KEY')
    )
    
    # Mantener agents existentes
    if PYDANTIC_AI_AVAILABLE:
        self._initialize_pydantic_agent()
    else:
        self.agent = None
        logger.warning("Agente Pydantic no inicializado")
```

**Agregar nuevo método:**
```python
async def respond_general_with_cohere(
    self,
    query: str,
    context: Dict[str, Any],
    language: str = "spanish"
) -> GeneralLegalResponse:
    """Responde con Cohere Command-R"""
    
    try:
        documents = context.get("documents", [])
        
        if not documents:
            return await self._fallback_general_response(query, context, language)
        
        # Context Engineer
        from context.context_engineering import context_engineer
        
        optimized_prompt = await context_engineer.build_legal_prompt(
            query=query,
            documents=documents,
            language=language,
            response_type="general"
        )
        
        # Cohere genera respuesta
        response = await self.cohere_client.chat(
            model="command-r-plus",
            message=optimized_prompt,
            temperature=0.3,
            max_tokens=2000,
            documents=[
                {
                    "id": doc.get("document_id", ""),
                    "text": doc["content"]
                }
                for doc in documents
            ]
        )
        
        # Parsear y validar
        structured_response = self._parse_to_pydantic(
            response.text,
            response.citations,
            context
        )
        
        return GeneralLegalResponse(**structured_response)
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise
```

---

### ✅ Tarea 4.2: Actualizar endpoint FastAPI
**Archivo:** `backend/main.py`

**Reemplazar endpoint `/legal-query` con:**
```python
@app.post("/legal-query-v2")
async def legal_query_v2(payload: LegalQueryRequest):
    """Consulta con Cohere + Rerank + Context"""
    try:
        query = payload.query.strip()
        language = payload.language
        
        # Búsqueda con Rerank
        context = await app.state.rag_engine.query_with_rerank(
            query=query,
            top_k=5,
            rerank_top_n=50
        )
        
        # Respuesta con Cohere
        response = await app.state.legal_agent.respond_general_with_cohere(
            query=query,
            context=context,
            language=language
        )
        
        return {
            "success": True,
            "query": query,
            "response": response.model_dump(),
            "sources": context["sources"],
            "metadata": {
                "total_candidates": context["total_candidates"],
                "rerank_scores": context["rerank_scores"],
                "model": "command-r-plus"
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise HTTPException(500, f"Query failed: {str(e)}")
```

---

## 🧪 FASE 5: Testing y Validación (2-3 horas)

### ✅ Tarea 5.1: Tests unitarios
**Archivo:** `tests/test_cohere_integration.py`

```python
import pytest
from backend.rag.lightrag_engine import LegalRAGEngine
from backend.context.context_engineering import ContextEngineer

@pytest.mark.asyncio
async def test_cohere_embeddings():
    """Test embeddings con Cohere"""
    engine = LegalRAGEngine()
    await engine.initialize_storages()
    
    await engine.add_document(
        content="Test de Cohere embeddings",
        metadata={"test": True},
        document_id="test_1"
    )
    
    result = await engine.query("test")
    assert len(result["sources"]) > 0

@pytest.mark.asyncio
async def test_rerank():
    """Test reranking"""
    engine = LegalRAGEngine()
    await engine.initialize_storages()
    
    # Agregar docs
    await engine.add_document("Violencia familiar", {}, "doc1")
    await engine.add_document("Pensión de alimentos", {}, "doc2")
    
    # Buscar con rerank
    result = await engine.query_with_rerank("violencia", top_k=1)
    
    assert len(result["documents"]) == 1
    assert "violencia" in result["documents"][0]["content"].lower()

@pytest.mark.asyncio
async def test_context_engineer():
    """Test Context Engineer"""
    engineer = ContextEngineer()
    
    docs = [{"content": "Test", "metadata": {}, "relevance_score": 0.9}]
    prompt = await engineer.build_legal_prompt(
        query="Test query",
        documents=docs,
        language="spanish"
    )
    
    assert "CONTEXTO LEGAL" in prompt
    assert "Test query" in prompt
```

**Ejecutar:**
```bash
pytest tests/test_cohere_integration.py -v
```

---

### ✅ Tarea 5.2: Test end-to-end
**Archivo:** `tests/test_e2e_cohere.py`

```python
import pytest
from httpx import AsyncClient
from backend.main import app

@pytest.mark.asyncio
async def test_legal_query_e2e():
    """Test completo del endpoint"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/legal-query-v2",
            json={
                "query": "¿Qué hago si mi pareja me golpea?",
                "language": "spanish"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        assert "response" in data
        assert "rerank_scores" in data["metadata"]
        assert len(data["metadata"]["rerank_scores"]) > 0
```

---

## 📊 FASE 6: Migración de Datos (1-2 horas)

### ✅ Tarea 6.1: Regenerar embeddings
**Script:** `scripts/regenerate_embeddings.py`

```python
import asyncio
from pathlib import Path
from backend.rag.lightrag_engine import LegalRAGEngine

async def regenerate_all_embeddings():
    """Regenera embeddings con Cohere para todos los docs"""
    engine = LegalRAGEngine()
    await engine.initialize_storages()
    
    processed_dir = Path("backend/docs/processed")
    count = 0
    
    for md_file in processed_dir.glob("**/*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            
            await engine.add_document(
                content=content,
                metadata={"filename": md_file.name},
                document_id=md_file.stem
            )
            
            count += 1
            print(f"✅ {count}: {md_file.name}")
            
        except Exception as e:
            print(f"❌ Error con {md_file.name}: {e}")
    
    print(f"\n✅ Total regenerado: {count} documentos")

if __name__ == "__main__":
    asyncio.run(regenerate_all_embeddings())
```

**Ejecutar:**
```bash
python scripts/regenerate_embeddings.py
```

---

## ✅ CHECKLIST FINAL

```markdown
### Configuración
- [ ] Cohere instalado (`pip install cohere`)
- [ ] API key configurada en `.env`
- [ ] `settings.py` actualizado

### Backend
- [ ] `lightrag_engine.py`: embeddings con Cohere
- [ ] `lightrag_engine.py`: método `query_with_rerank`
- [ ] `chunking_strategies.py`: clase `ContextualChunker`
- [ ] `prompt_templates.py`: clase `PromptManager`
- [ ] `context_engineering.py`: método `build_legal_prompt`
- [ ] `pydantic_agents.py`: método `respond_general_with_cohere`
- [ ] `main.py`: endpoint `/legal-query-v2`

### Testing
- [ ] Tests unitarios pasando
- [ ] Test E2E funcionando
- [ ] Embeddings regenerados

### Validación
- [ ] Query de prueba retorna resultados
- [ ] Rerank scores > 0.5 para queries relevantes
- [ ] Prompt incluye contexto cultural
- [ ] Respuesta valida con Pydantic
```

---

## 🚀 Ejecución Rápida

```bash
# 1. Instalar dependencias
pip install cohere

# 2. Configurar .env
echo "COHERE_API_KEY=tu_key" >> .env

# 3. Ejecutar migraciones de código
# (Aplicar cada tarea del plan)

# 4. Regenerar embeddings
python scripts/regenerate_embeddings.py

# 5. Ejecutar tests
pytest tests/test_cohere_integration.py -v

# 6. Iniciar servidor
python backend/main.py

# 7. Test manual
curl -X POST http://localhost:8000/legal-query-v2 \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Qué hago en caso de violencia familiar?", "language": "spanish"}'
```

---

## 📈 Métricas de Éxito

| Métrica | Antes | Después | Objetivo |
|---------|-------|---------|----------|
| **Relevancia** | 40-50% | 80-90% | >80% |
| **Rerank score** | N/A | 0.7-0.9 | >0.7 |
| **Tiempo respuesta** | 2-3s | 3-4s | <5s |
| **Precisión cultural** | Media | Alta | Alta |
| **Citas correctas** | Pocas | Automáticas | >90% |

---

## 🆘 Troubleshooting

### Error: "COHERE_API_KEY not found"
```bash
# Verificar .env
cat .env | grep COHERE
# Recargar
source .env
```

### Error: "StorageNotInitializedError"
```python
# Asegurar inicialización
await engine.initialize_storages()
```

### Embeddings vacíos
```python
# Verificar que se llame a Cohere
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 📚 Recursos Adicionales

- [Cohere Docs](https://docs.cohere.com)
- [LightRAG GitHub](https://github.com/HKUDS/LightRAG)
- [Pydantic AI Docs](https://ai.pydantic.dev)

---

**Autor:** Equipo IA Jurídica  
**Última actualización:** 2026-01-XX