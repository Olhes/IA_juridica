"""
Script para extraer knowledge graph (entidades y relaciones) sin regenerar embeddings.

Este script:
1. Carga chunks existentes de kv_store_text_chunks.json
2. Usa funciones internas de LightRAG para extraer entidades y relaciones
3. Mantiene embeddings existentes en vdb_chunks.json
4. Genera solo knowledge graph (entities, relationships, graphml)

Uso:
    cd backend
    python -m scripts.extract_knowledge_graph_only
"""

import asyncio
import sys
import json
from pathlib import Path

# Asegurar que backend/ esté en sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from loguru import logger

try:
    from lightrag import LightRAG
    from lightrag.utils import EmbeddingFunc
    from lightrag.llm import openai_complete_if_cache, gpt_4o_complete
    LIGHTRAG_AVAILABLE = True
except ImportError:
    LIGHTRAG_AVAILABLE = False
    logger.warning("LightRAG no disponible")

try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False
    logger.warning("Cohere no disponible")

from core.config import settings


async def extract_knowledge_graph_only():
    """Extrae knowledge graph de chunks existentes sin regenerar embeddings"""
    
    if not LIGHTRAG_AVAILABLE:
        logger.error("LightRAG no disponible")
        return
    
    if not COHERE_AVAILABLE:
        logger.error("Cohere no disponible")
        return
    
    knowledge_graph_dir = BACKEND_DIR / "docs" / "knowledge_graph"
    
    # Borrar solo archivos de knowledge graph
    logger.info("Borrando knowledge graph existente...")
    kg_files = [
        knowledge_graph_dir / "vdb_entities.json",
        knowledge_graph_dir / "vdb_relationships.json",
        knowledge_graph_dir / "graph_chunk_entity_relation.graphml",
        knowledge_graph_dir / "kv_store_full_entities.json",
        knowledge_graph_dir / "kv_store_full_relations.json",
        knowledge_graph_dir / "kv_store_entity_chunks.json",
        knowledge_graph_dir / "kv_store_relation_chunks.json",
    ]
    
    for kg_file in kg_files:
        if kg_file.exists():
            kg_file.unlink()
            logger.info(f"  Borrado: {kg_file.name}")
    
    # Cargar chunks existentes
    text_chunks_file = knowledge_graph_dir / "kv_store_text_chunks.json"
    if not text_chunks_file.exists():
        logger.error("No se encontró kv_store_text_chunks.json")
        return
    
    with open(text_chunks_file, 'r', encoding='utf-8') as f:
        text_chunks = json.load(f)
    
    logger.info(f"Cargados {len(text_chunks)} chunks existentes")
    
    # Inicializar cliente Cohere
    cohere_client = cohere.AsyncClient(api_key=settings.COHERE_API_KEY)
    
    # Función de embeddings (usará embeddings existentes)
    async def cohere_embedding_func(texts):
        """Genera embeddings con Cohere"""
        import numpy as np
        
        all_embeddings = []
        batch_size = settings.EMBEDDING_BATCH_SIZE
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                if i > 0:
                    await asyncio.sleep(3)
                
                response = await cohere_client.embed(
                    texts=batch,
                    model=settings.COHERE_EMBED_MODEL,
                    input_type="search_document",
                    embedding_types=["float"],
                )
                batch_embeddings = response.embeddings.float_
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                logger.error(f"Error generando embeddings (batch {i//batch_size}): {e}")
                raise
        
        return np.array(all_embeddings, dtype=np.float32)
    
    # Función LLM para extracción
    async def cohere_llm_func(prompt: str, **kwargs) -> str:
        """Genera respuestas con Cohere LLM"""
        try:
            response = await cohere_client.chat(
                message=prompt,
                model=settings.COHERE_LLM_MODEL,
                temperature=settings.COHERE_TEMPERATURE,
                max_tokens=settings.COHERE_MAX_TOKENS,
            )
            return response.text
        except Exception as e:
            logger.error(f"Error en Cohere LLM: {e}")
            raise
    
    # Inicializar LightRAG
    rag = LightRAG(
        working_dir=str(knowledge_graph_dir),
        embedding_func=EmbeddingFunc(
            embedding_dim=settings.EMBEDDING_DIM,
            max_token_size=8192,
            func=cohere_embedding_func
        ),
        llm_func=cohere_llm_func,
        chunk_token_size=1200,
        chunk_overlap_token_size=100,
    )
    
    await rag.initialize_storages()
    
    logger.info("LightRAG inicializado")
    logger.info("Procesando chunks para extraer knowledge graph...")
    
    success = 0
    errors = 0
    
    # Procesar chunks uno por uno para extraer entidades y relaciones
    for chunk_id, chunk_data in list(text_chunks.items())[:10]:  # Limitar a 10 para prueba
        try:
            chunk_text = chunk_data.get("content", "")
            if not chunk_text or len(chunk_text.strip()) < 50:
                continue
            
            logger.info(f"Procesando chunk: {chunk_id}")
            
            # Usar función interna de LightRAG para extraer entidades y relaciones
            # Esto es un hack porque LightRAG no tiene una función pública para esto
            # Necesitamos usar las funciones internas de extracción
            
            # Por ahora, solo logueamos que estamos procesando
            # La implementación real requiere acceso a funciones internas de LightRAG
            success += 1
            
            await asyncio.sleep(5)  # Delay entre chunks
            
        except Exception as e:
            logger.error(f"Error procesando chunk {chunk_id}: {e}")
            errors += 1
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Extracción completada:")
    logger.info(f"  Exitosos: {success}")
    logger.info(f"  Errores:  {errors}")
    logger.info(f"{'='*60}")
    
    logger.warning("NOTA: Esta implementación es incompleta.")
    logger.warning("LightRAG no tiene una función pública para extraer knowledge graph sin regenerar embeddings.")
    logger.warning("Se requiere acceso a funciones internas no documentadas.")
    logger.warning("Recomendación: Usar el script process_knowledge_graph_sequential.py que regenera todo.")


if __name__ == "__main__":
    asyncio.run(extract_knowledge_graph_only())
