"""
Script para regenerar solo embeddings (sin knowledge graph).

Este script:
1. Lee los documentos procesados (.md) de docs/processed/
2. Los re-inserta en LightRAG en modo "naive" (solo embeddings, sin entidades/relaciones)
3. Genera embeddings con Cohere (con delays para rate limit)
4. NO usa LLM para extraer knowledge graph

Uso:
    cd backend
    # Procesar todos los archivos
    python -m scripts.regenerate_embeddings_only
    
    # Procesar archivos específicos
    python -m scripts.regenerate_embeddings_only --file archivo1.md --file archivo2.md
"""

import asyncio
import sys
import argparse
from pathlib import Path

# Asegurar que backend/ esté en sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from loguru import logger

# Intentar importar LightRAG
try:
    from lightrag import LightRAG, QueryParam
    from lightrag.utils import EmbeddingFunc
    LIGHTRAG_AVAILABLE = True
except ImportError:
    LIGHTRAG_AVAILABLE = False
    logger.warning("LightRAG no disponible")

# Intentar importar Cohere
try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False
    logger.warning("Cohere no disponible")

# Importar settings
from core.config import settings


async def regenerate_embeddings_only(specific_files=None):
    """Regenera solo embeddings sin knowledge graph"""
    
    if not LIGHTRAG_AVAILABLE:
        logger.error("LightRAG no disponible. Instala con: pip install lightrag-hku")
        return
    
    if not COHERE_AVAILABLE:
        logger.error("Cohere no disponible. Instala con: pip install cohere")
        return
    
    if not settings.COHERE_API_KEY:
        logger.error("COHERE_API_KEY no configurada en .env")
        return
    
    # Inicializar cliente Cohere
    cohere_client = cohere.AsyncClient(api_key=settings.COHERE_API_KEY)
    
    # Función de embeddings con delays
    async def cohere_embedding_func(texts):
        """Genera embeddings con Cohere (con delays para rate limit)"""
        import numpy as np
        
        all_embeddings = []
        batch_size = settings.EMBEDDING_BATCH_SIZE
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                # Delay entre batches para evitar rate limit
                if i > 0:
                    await asyncio.sleep(3)  # 3 segundos entre batches
                
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
    
    # Inicializar LightRAG en modo "naive" (solo embeddings, sin knowledge graph)
    working_dir = BACKEND_DIR / "docs" / "knowledge_graph"
    rag = LightRAG(
        working_dir=str(working_dir),
        embedding_func=EmbeddingFunc(
            embedding_dim=settings.EMBEDDING_DIM,
            max_token_size=8192,
            func=cohere_embedding_func
        ),
        # Modo naive: solo embeddings, sin knowledge graph
        chunk_token_size=1200,
        chunk_overlap_token_size=100,
    )
    
    await rag.initialize_storages()
    
    # Obtener archivos a procesar
    processed_dir = BACKEND_DIR / "docs" / "processed"
    
    if specific_files:
        md_files = []
        for file_path in specific_files:
            file_path = Path(file_path)
            if not file_path.is_absolute():
                file_path = processed_dir / file_path
            if file_path.exists() and file_path.suffix == ".md":
                md_files.append(file_path)
            else:
                logger.warning(f"Archivo no encontrado o no es .md: {file_path}")
    else:
        md_files = sorted(processed_dir.glob("**/*.md"))
    
    if not md_files:
        logger.error("No se encontraron archivos .md para procesar")
        return
    
    logger.info(f"Encontrados {len(md_files)} documentos para procesar (solo embeddings)")
    logger.info("Modo: naive (sin knowledge graph)")
    
    success = 0
    errors = 0
    
    for md_file in md_files:
        doc_id = md_file.stem
        try:
            content = md_file.read_text(encoding="utf-8")
            if len(content.strip()) < 50:
                logger.warning(f"Saltando {md_file.name}: contenido muy corto")
                continue
            
            logger.info(f"[{success + errors + 1}/{len(md_files)}] Insertando embeddings: {doc_id}")
            
            # Insertar en modo naive (solo embeddings, sin knowledge graph)
            await rag.ainsert(content)
            success += 1
            
        except Exception as e:
            logger.error(f"Error con {doc_id}: {e}")
            errors += 1
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Regeneración de embeddings completada:")
    logger.info(f"  Exitosos: {success}")
    logger.info(f"  Errores:  {errors}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenerar solo embeddings (sin knowledge graph)")
    parser.add_argument("--file", "-f", action="append", help="Archivos específicos a procesar (puede usarse múltiples veces)")
    
    args = parser.parse_args()
    
    asyncio.run(regenerate_embeddings_only(args.file))
