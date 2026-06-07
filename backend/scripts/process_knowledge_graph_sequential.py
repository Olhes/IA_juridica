"""
Script para procesar knowledge graph (entidades y relaciones) uno por uno.

Este script:
1. Lista todos los archivos .md en docs/processed/
2. Procesa uno por uno con delays para evitar rate limit
3. SOLO genera entidades y relaciones (NO regenera embeddings)
4. Permite continuar desde donde se quedó

Uso:
    cd backend
    # Procesar todos los archivos uno por uno
    python -m scripts.process_knowledge_graph_sequential
    
    # Procesar archivo específico
    python -m scripts.process_knowledge_graph_sequential --file archivo.md
    
    # Continuar desde un índice específico
    python -m scripts.process_knowledge_graph_sequential --start 5
"""

import asyncio
import sys
import argparse
import time
from pathlib import Path

# Asegurar que backend/ esté en sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from loguru import logger
from rag.lightrag_engine import LegalRAGEngine


async def process_sequential(specific_file=None, start_index=0):
    """Procesa archivos uno por uno con delays (solo knowledge graph)"""
    processed_dir = BACKEND_DIR / "docs" / "processed"
    knowledge_graph_dir = BACKEND_DIR / "docs" / "knowledge_graph"
    
    if specific_file:
        # Procesar solo un archivo específico
        md_files = []
        file_path = Path(specific_file)
        if not file_path.is_absolute():
            file_path = processed_dir / file_path
        if file_path.exists() and file_path.suffix == ".md":
            md_files.append(file_path)
        else:
            logger.error(f"Archivo no encontrado o no es .md: {file_path}")
            return
    else:
        # Procesar todos los archivos
        md_files = sorted(processed_dir.glob("**/*.md"))
    
    if not md_files:
        logger.error("No se encontraron archivos .md para procesar")
        return
    
    # Filtrar por índice de inicio
    md_files = md_files[start_index:]
    
    logger.info(f"Encontrados {len(md_files)} documentos para procesar (solo knowledge graph)")
    logger.info(f"Procesando del índice {start_index} en adelante")
    logger.info("NOTA: Este script borrará y regenerará knowledge graph (entidades/relaciones)")
    
    # Borrar archivos de knowledge graph existentes para forzar regeneración
    logger.info("Borrando knowledge graph existente...")
    kg_files = [
        knowledge_graph_dir / "vdb_entities.json",
        knowledge_graph_dir / "vdb_relationships.json",
        knowledge_graph_dir / "graph_chunk_entity_relation.graphml",
        knowledge_graph_dir / "kv_store_full_entities.json",
        knowledge_graph_dir / "kv_store_full_relations.json",
        knowledge_graph_dir / "kv_store_entity_chunks.json",
        knowledge_graph_dir / "kv_store_relation_chunks.json",
        # También borrar estado de documentos para forzar reprocesamiento
        knowledge_graph_dir / "documents_store.json",
        knowledge_graph_dir / "kv_store_doc_status.json",
    ]
    
    for kg_file in kg_files:
        if kg_file.exists():
            kg_file.unlink()
            logger.info(f"  Borrado: {kg_file.name}")
    
    # Reinicializar engine con knowledge graph limpio
    engine = LegalRAGEngine(working_dir=str(knowledge_graph_dir))
    await engine.initialize_storages()
    
    logger.info(f"Documentos ya en memoria: {len(engine.documents)}")
    
    success = 0
    errors = 0
    
    for idx, md_file in enumerate(md_files, start=start_index):
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
                "source": "knowledge_graph_sequential",
            }
            
            logger.info(f"[{idx + 1}/{len(md_files) + start_index}] Procesando knowledge graph: {doc_id}")
            logger.info(f"  Tamaño: {len(content):,} caracteres")
            
            # Insertar documento (generará embeddings + knowledge graph)
            await engine.add_document(content, metadata, doc_id)
            success += 1
            
            # Delay entre archivos para evitar rate limit
            if idx < len(md_files) - 1:  # No delay después del último
                logger.info(f"  Esperando 10 segundos antes del siguiente archivo...")
                await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"Error con {doc_id}: {e}")
            errors += 1
            # Esperar más tiempo si hay error
            logger.info(f"  Esperando 30 segundos después del error...")
            await asyncio.sleep(30)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Procesamiento completado:")
    logger.info(f"  Exitosos: {success}")
    logger.info(f"  Errores:  {errors}")
    logger.info(f"  Docs en memoria: {len(engine.documents)}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Procesar knowledge graph uno por uno")
    parser.add_argument("--file", "-f", help="Archivo específico a procesar")
    parser.add_argument("--start", "-s", type=int, default=0, help="Índice de inicio para continuar")
    
    args = parser.parse_args()
    
    asyncio.run(process_sequential(args.file, args.start))
