"""
Script para regenerar todos los embeddings con Cohere.

Elimina los datos antiguos del knowledge graph (generados con embeddings
fake MD5 de 768d) y re-ingesta los documentos procesados usando embeddings
reales de Cohere (1024d).

Uso:
    cd backend
    python -m scripts.regenerate_embeddings          # re-ingestar todo
    python -m scripts.regenerate_embeddings --dry-run # solo listar archivos
"""

import asyncio
import argparse
import json
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime

# Asegurar import del backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from config.settings import settings

KNOWLEDGE_GRAPH_DIR = Path(settings.KNOWLEDGE_GRAPH_DIR)
PROCESSED_DIR = Path(settings.PROCESSED_DIR)

# Archivos del knowledge graph que se deben regenerar
KG_FILES = [
    "graph_chunk_entity_relation.graphml",
    "kv_store_doc_status.json",
    "kv_store_full_docs.json",
    "kv_store_llm_response_cache.json",
    "kv_store_text_chunks.json",
    "vdb_chunks.json",
    "vdb_entities.json",
    "vdb_relationships.json",
]


def list_processed_docs() -> list[Path]:
    """Retorna lista de documentos .md en processed/"""
    if not PROCESSED_DIR.exists():
        logger.warning(f"Directorio {PROCESSED_DIR} no existe")
        return []
    return sorted(PROCESSED_DIR.glob("*.md"))


def backup_knowledge_graph() -> Path | None:
    """Crea backup del knowledge graph actual"""
    if not KNOWLEDGE_GRAPH_DIR.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = KNOWLEDGE_GRAPH_DIR.parent / f"knowledge_graph_backup_{timestamp}"

    try:
        shutil.copytree(KNOWLEDGE_GRAPH_DIR, backup_dir)
        logger.info(f"Backup creado en {backup_dir}")
        return backup_dir
    except Exception as e:
        logger.error(f"Error creando backup: {e}")
        return None


def clear_knowledge_graph():
    """Elimina los archivos del knowledge graph para regeneración"""
    for fname in KG_FILES:
        fpath = KNOWLEDGE_GRAPH_DIR / fname
        if fpath.exists():
            fpath.unlink()
            logger.info(f"  Eliminado: {fname}")
        else:
            logger.debug(f"  No existe: {fname}")


async def reingest_all():
    """Re-ingesta todos los documentos procesados"""
    from rag.lightrag_engine import LegalRAGEngine

    docs = list_processed_docs()
    if not docs:
        logger.error("No hay documentos procesados para ingestar")
        return

    logger.info(f"Documentos a re-ingestar: {len(docs)}")

    engine = LegalRAGEngine()
    success = 0
    failed = 0

    for doc_path in docs:
        doc_name = doc_path.stem
        logger.info(f"Procesando: {doc_name}")

        try:
            content = doc_path.read_text(encoding="utf-8")
            if not content.strip():
                logger.warning(f"  ⚠ Documento vacío, saltando: {doc_name}")
                failed += 1
                continue

            await engine.add_document(
                content=content,
                metadata={
                    "source": doc_name,
                    "file": doc_path.name,
                    "regenerated": True,
                    "timestamp": datetime.now().isoformat(),
                },
                document_id=doc_name,
            )
            success += 1
            logger.info(f"  ✓ {doc_name}")

        except Exception as e:
            logger.error(f"  ✗ Error con {doc_name}: {e}")
            failed += 1

    logger.info(f"\nResultados: {success} OK, {failed} fallidos de {len(docs)} total")


def main():
    parser = argparse.ArgumentParser(description="Regenerar embeddings con Cohere")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo listar documentos sin procesar",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="No crear backup del knowledge graph",
    )
    args = parser.parse_args()

    docs = list_processed_docs()
    logger.info(f"Documentos procesados encontrados: {len(docs)}")
    for d in docs:
        logger.info(f"  - {d.name}")

    if args.dry_run:
        logger.info("Modo dry-run: no se realizan cambios")
        return

    # Validar que Cohere API key está configurada
    if not settings.COHERE_API_KEY:
        logger.error("COHERE_API_KEY no configurada. Abortando.")
        sys.exit(1)

    # Backup
    if not args.no_backup:
        backup_knowledge_graph()

    # Limpiar knowledge graph viejo
    logger.info("Limpiando knowledge graph antiguo...")
    clear_knowledge_graph()

    # Re-ingestar
    logger.info("Re-ingesta con Cohere embeddings (1024d)...")
    asyncio.run(reingest_all())
    logger.info("¡Regeneración completa!")


if __name__ == "__main__":
    main()
