"""
Script para regenerar el knowledge graph de LightRAG localmente
Costo estimado: ~$0.30-0.50 USD para 18 documentos
"""
import asyncio
from pathlib import Path
from modules.rag.services.lightrag_engine import LegalRAGEngine
from config.settings import settings
from loguru import logger

async def regenerate_knowledge_graph():
    """Regenera el knowledge graph desde documentos procesados"""
    
    logger.info("🔄 Iniciando regeneración del knowledge graph...")
    
    # Hacer backup del knowledge graph actual
    kg_dir = Path(settings.KNOWLEDGE_GRAPH_DIR)
    backup_dir = kg_dir.parent / f"knowledge_graph_backup_before_regenerate"
    if backup_dir.exists():
        import shutil
        shutil.rmtree(backup_dir)
    
    import shutil
    shutil.copytree(kg_dir, backup_dir)
    logger.info(f"💾 Backup creado en: {backup_dir}")
    
    # Limpiar knowledge graph actual
    for file in kg_dir.glob("*"):
        if file.name != ".gitkeep":
            file.unlink()
    logger.info("🗑️ Knowledge graph limpiado")
    
    # Inicializar RAG engine
    rag_engine = LegalRAGEngine()
    await rag_engine.initialize_storages()
    
    # Cargar documentos procesados
    processed_dir = Path(settings.PROCESSED_DIR)
    md_files = list(processed_dir.glob("**/*.md"))
    
    logger.info(f"📁 Encontrados {len(md_files)} documentos procesados")
    
    # Procesar cada documento
    processed_count = 0
    for i, md_file in enumerate(md_files, 1):
        if md_file.stat().st_size < 100:  # Ignorar archivos muy pequeños
            continue
            
        logger.info(f"📄 Procesando [{i}/{len(md_files)}]: {md_file.name}")
        
        try:
            content = md_file.read_text(encoding="utf-8")
            
            # Extraer metadata del nombre
            doc_id = md_file.stem
            metadata = {
                "filename": md_file.name,
                "title": doc_id,
                "document_type": "legal_document",
                "source": "local_regeneration"
            }
            
            # Agregar a LightRAG (esto generará el knowledge graph)
            await rag_engine.add_document(
                content=content,
                metadata=metadata,
                document_id=doc_id
            )
            
            processed_count += 1
            logger.success(f"✅ {md_file.name} procesado ({processed_count}/{len(md_files)})")
            
        except Exception as e:
            logger.error(f"❌ Error procesando {md_file.name}: {e}")
    
    logger.info(f"\n🎉 Regeneración completada: {processed_count} documentos procesados")
    logger.info(f"📊 Documentos en memoria: {len(rag_engine.documents)}")
    
    # Verificar knowledge graph
    try:
        kg = await rag_engine.get_knowledge_graph()
        logger.info(f"🔗 Knowledge Graph: {kg.get('total_nodes', 0)} nodes, {kg.get('total_edges', 0)} edges")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo obtener el knowledge graph: {e}")

if __name__ == "__main__":
    asyncio.run(regenerate_knowledge_graph())
