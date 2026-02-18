"""
Script para regenerar los vector databases de LightRAG.

Los archivos vdb_chunks.json, vdb_entities.json y vdb_relationships.json
están vacíos, lo que impide que LightRAG devuelva resultados en sus queries.

Este script:
1. Lee los documentos procesados (.md) de docs/processed/
2. Los re-inserta en LightRAG con ainsert() → esto genera embeddings + grafo
3. Persiste el documents_store.json local para el fallback de reranking

Uso:
    cd backend
    python -m scripts.regenerate_vector_dbs
"""

import asyncio
import sys
from pathlib import Path

# Asegurar que backend/ esté en sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from loguru import logger
from rag.lightrag_engine import LegalRAGEngine


async def regenerate():
    processed_dir = BACKEND_DIR / "docs" / "processed"
    md_files = sorted(processed_dir.glob("**/*.md"))
    
    if not md_files:
        logger.error("No se encontraron archivos .md en docs/processed/")
        return
    
    logger.info(f"Encontrados {len(md_files)} documentos procesados")
    
    engine = LegalRAGEngine(working_dir=str(BACKEND_DIR / "docs" / "knowledge_graph"))
    await engine.initialize_storages()
    
    logger.info(f"Documentos ya en memoria: {len(engine.documents)}")
    
    success = 0
    errors = 0
    
    for md_file in md_files:
        doc_id = md_file.stem
        try:
            content = md_file.read_text(encoding="utf-8")
            if len(content.strip()) < 50:
                logger.warning(f"Saltando {md_file.name}: contenido muy corto")
                continue
            
            metadata = {
                "filename": md_file.name,
                "title": doc_id,
                "document_type": "legal_document",
                "source": "regeneration",
            }
            
            logger.info(f"[{success + errors + 1}/{len(md_files)}] Insertando: {doc_id}")
            await engine.add_document(content, metadata, doc_id)
            success += 1
            
        except Exception as e:
            logger.error(f"Error con {doc_id}: {e}")
            errors += 1
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Regeneración completada:")
    logger.info(f"  Exitosos: {success}")
    logger.info(f"  Errores:  {errors}")
    logger.info(f"  Docs en memoria: {len(engine.documents)}")
    logger.info(f"  Persistidos en: {engine._documents_store_path}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(regenerate())
