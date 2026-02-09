import asyncio
from pathlib import Path
from typing import Dict, List, Any
from loguru import logger
from tqdm import tqdm
import concurrent.futures

from ingestion.docling_processor import LegalPDFProcessor
from rag.lightrag_engine import LegalRAGEngine
from utils.file_utils import FileUtils
from config.settings import settings

class OptimizedLegalIngestionPipeline:
    """Pipeline optimizado para ingesta paralela de documentos legales"""
    
    def __init__(self, max_workers: int = 4):
        self.pdf_processor = LegalPDFProcessor()
        self.rag_engine = LegalRAGEngine()
        self.file_utils = FileUtils()
        self.max_workers = max_workers  # Controlar concurrencia
        
        # Directorios
        self.raw_dir = Path("docs/raw_pdfs")
        self.processed_dir = Path("docs/processed")
        self.failed_dir = Path("docs/failed")
        
        # Asegurar que existan los directorios
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Crea directorios necesarios"""
        for directory in [self.raw_dir, self.processed_dir, self.failed_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    async def process_all_pdfs_parallel(self) -> Dict[str, Any]:
        """
        Procesa PDFs en paralelo para mayor velocidad
        
        Returns:
            Dict con resultados del procesamiento
        """
        logger.info(f"Iniciando procesamiento PARALELO de PDFs (workers: {self.max_workers})")
        
        # Obtener todos los PDFs
        pdf_files = list(self.raw_dir.glob("**/*.pdf"))
        
        if not pdf_files:
            logger.warning("No se encontraron PDFs para procesar")
            return {"processed_count": 0, "failed_count": 0, "details": []}
        
        # Crear semáforo para limitar concurrencia
        semaphore = asyncio.Semaphore(self.max_workers)
        
        # Procesar en paralelo con control de concurrencia
        tasks = []
        for pdf_file in pdf_files:
            task = self._process_with_semaphore(semaphore, pdf_file)
            tasks.append(task)
        
        # Ejecutar todas las tareas concurrentemente
        results = await asyncio.gather(*tasks)
        
        # Separar exitosos y fallidos
        processed = [r for r in results if r["status"] == "success"]
        failed = [r for r in results if r["status"] == "failed"]
        
        # Reconstruir índice RAG una sola vez al final
        if processed:
            logger.info("Reconstruyendo índice RAG...")
            await self.rag_engine.rebuild_index()
        
        summary = {
            "processed_count": len(processed),
            "failed_count": len(failed),
            "details": processed + failed,
            "optimization": "parallel_processing",
            "workers_used": self.max_workers
        }
        
        logger.info(f"Procesamiento paralelo completado: {summary['processed_count']} exitosos, {summary['failed_count']} fallidos")
        return summary
    
    async def _process_with_semaphore(self, semaphore: asyncio.Semaphore, pdf_file: Path) -> Dict[str, Any]:
        """
        Procesa un PDF con control de concurrencia
        
        Args:
            semaphore: Controla el número máximo de procesos simultáneos
            pdf_file: Archivo PDF a procesar
            
        Returns:
            Dict con resultado del procesamiento
        """
        async with semaphore:
            try:
                result = await self.process_single_pdf_optimized(pdf_file)
                logger.info(f"✅ Procesado: {pdf_file.relative_to(self.raw_dir)}")
                return result
                
            except Exception as e:
                error_result = {
                    "filename": str(pdf_file.relative_to(self.raw_dir)),
                    "error": str(e),
                    "status": "failed"
                }
                
                # Mover a fallidos
                relative_path = pdf_file.relative_to(self.raw_dir)
                failed_path = self.failed_dir / relative_path
                failed_path.parent.mkdir(parents=True, exist_ok=True)
                pdf_file.rename(failed_path)
                
                logger.error(f"❌ Falló: {relative_path} - {str(e)}")
                return error_result
    
    async def process_single_pdf_optimized(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Versión optimizada de procesamiento individual
        
        Args:
            pdf_path: Path al archivo PDF
            
        Returns:
            Dict con resultado optimizado
        """
        relative_path = pdf_path.relative_to(self.raw_dir)
        
        # Verificar si ya está procesado
        output_file = self.processed_dir / f"{relative_path.stem}.md"
        if output_file.exists():
            logger.debug(f"⏭️  Ya procesado: {relative_path}")
            return {
                "filename": str(relative_path),
                "status": "already_exists",
                "message": "Document already processed"
            }
        
        # Procesar con Docling
        start_time = asyncio.get_event_loop().time()
        markdown_content = await self.pdf_processor.process_pdf(str(pdf_path))
        processing_time = asyncio.get_event_loop().time() - start_time
        
        # Guardar resultado
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        # Agregar al RAG inmediatamente
        metadata = {
            "filename": str(relative_path),
            "file_size": pdf_path.stat().st_size,
            "processing_time": processing_time,
            "category": str(relative_path.parent)
        }
        
        document_id = f"{relative_path.parent}_{relative_path.stem}"
        await self.rag_engine.add_document(markdown_content, metadata, document_id)
        
        return {
            "filename": str(relative_path),
            "status": "success",
            "processing_time": processing_time,
            "content_length": len(markdown_content),
            "document_id": document_id
        }
    
    def get_performance_recommendations(self) -> Dict[str, Any]:
        """
        Analiza el sistema y da recomendaciones de rendimiento
        
        Returns:
            Dict con recomendaciones optimizadas
        """
        import psutil
        
        # Obtener specs del sistema
        cpu_count = psutil.cpu_count()
        memory_gb = psutil.virtual_memory().total / (1024**3)
        
        # Recomendaciones basadas en hardware
        if memory_gb < 8:
            recommended_workers = 2
            reason = "Memoria limitada"
        elif memory_gb < 16:
            recommended_workers = min(4, cpu_count)
            reason = "Memoria moderada"
        else:
            recommended_workers = min(8, cpu_count)
            reason = "Buena memoria disponible"
        
        return {
            "current_workers": self.max_workers,
            "recommended_workers": recommended_workers,
            "cpu_cores": cpu_count,
            "memory_gb": round(memory_gb, 1),
            "reason": reason,
            "estimated_speedup": f"{recommended_workers}x más rápido que secuencial",
            "tip": "Usa workers = min(8, cpu_cores) para mejor rendimiento"
        }
