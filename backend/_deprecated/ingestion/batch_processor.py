import asyncio
from pathlib import Path
from typing import List, Dict, Any
from loguru import logger
import time

class BatchPDFProcessor:
    """Procesador optimizado para grandes volúmenes de PDFs"""
    
    def __init__(self, batch_size: int = 50, max_workers: int = 8):
        self.batch_size = batch_size
        self.max_workers = max_workers
        
    async def process_large_volume(self, pdf_dir: Path) -> Dict[str, Any]:
        """
        Procesa grandes volúmenes de PDFs por lotes
        
        Args:
            pdf_dir: Directorio con PDFs
            
        Returns:
            Dict con resultados del procesamiento por lotes
        """
        pdf_files = list(pdf_dir.glob("**/*.pdf"))
        total_files = len(pdf_files)
        
        logger.info(f"📊 Iniciando procesamiento de {total_files} PDFs")
        logger.info(f"🔢 Configuración: {self.batch_size} archivos por lote, {self.max_workers} workers")
        
        # Dividir en lotes
        batches = [
            pdf_files[i:i + self.batch_size] 
            for i in range(0, total_files, self.batch_size)
        ]
        
        total_batches = len(batches)
        results = {
            "total_files": total_files,
            "total_batches": total_batches,
            "batch_results": [],
            "total_time": 0,
            "successful_files": 0,
            "failed_files": 0
        }
        
        start_time = time.time()
        
        # Procesar cada lote
        for batch_idx, batch in enumerate(batches, 1):
            logger.info(f"📦 Procesando lote {batch_idx}/{total_batches} ({len(batch)} archivos)")
            
            batch_start = time.time()
            batch_result = await self._process_batch(batch, batch_idx)
            batch_time = time.time() - batch_start
            
            # Actualizar resultados
            results["batch_results"].append({
                "batch_number": batch_idx,
                "files_count": len(batch),
                "successful": batch_result["successful"],
                "failed": batch_result["failed"],
                "time": batch_time,
                "avg_time_per_file": batch_time / len(batch) if batch else 0
            })
            
            results["successful_files"] += batch_result["successful"]
            results["failed_files"] += batch_result["failed"]
            
            logger.info(f"✅ Lote {batch_idx} completado: {batch_result['successful']} exitosos, {batch_result['failed']} fallidos, {batch_time:.1f}s")
            
            # Pequeña pausa entre lotes para no sobrecargar
            if batch_idx < total_batches:
                await asyncio.sleep(2)
        
        results["total_time"] = time.time() - start_time
        
        # Estadísticas finales
        avg_time_per_file = results["total_time"] / total_files if total_files > 0 else 0
        results["statistics"] = {
            "avg_time_per_file": avg_time_per_file,
            "files_per_minute": total_files / (results["total_time"] / 60) if results["total_time"] > 0 else 0,
            "success_rate": (results["successful_files"] / total_files * 100) if total_files > 0 else 0
        }
        
        logger.info(f"🎉 Procesamiento completado:")
        logger.info(f"   📊 Total: {results['successful_files']} exitosos, {results['failed_files']} fallidos")
        logger.info(f"   ⏱️  Tiempo total: {results['total_time']:.1f}s ({results['total_time']/60:.1f}min)")
        logger.info(f"   📈 Promedio: {avg_time_per_file:.1f}s por archivo")
        logger.info(f"   🚀 Velocidad: {results['statistics']['files_per_minute']:.1f} archivos/minuto")
        
        return results
    
    async def _process_batch(self, batch: List[Path], batch_idx: int) -> Dict[str, Any]:
        """
        Procesa un lote específico de PDFs
        
        Args:
            batch: Lista de archivos PDF del lote
            batch_idx: Número del lote
            
        Returns:
            Dict con resultados del lote
        """
        from ingestion.optimized_pipeline import OptimizedLegalIngestionPipeline
        
        # Crear pipeline específico para este lote
        pipeline = OptimizedLegalIngestionPipeline(max_workers=self.max_workers)
        
        # Mover archivos del lote a directorio temporal
        temp_dir = Path(f"temp_batch_{batch_idx}")
        temp_dir.mkdir(exist_ok=True)
        
        try:
            # Copiar archivos del lote al directorio temporal
            for pdf_file in batch:
                temp_file = temp_dir / pdf_file.name
                import shutil
                shutil.copy2(pdf_file, temp_file)
            
            # Procesar lote
            batch_result = await pipeline.process_all_pdfs_parallel()
            
            return {
                "successful": batch_result.get("processed_count", 0),
                "failed": batch_result.get("failed_count", 0)
            }
            
        finally:
            # Limpiar directorio temporal
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
    
    def estimate_processing_time(self, total_files: int) -> Dict[str, Any]:
        """
        Estima tiempo de procesamiento para un volumen de archivos
        
        Args:
            total_files: Número total de archivos a procesar
            
        Returns:
            Dict con estimaciones
        """
        # Basado en pruebas reales: ~15 segundos por PDF con 8 workers
        avg_time_per_file = 15  # segundos
        
        # Calcular lotes necesarios
        num_batches = (total_files + self.batch_size - 1) // self.batch_size
        
        # Tiempo estimado
        processing_time = (total_files / self.max_workers) * avg_time_per_file
        batch_overhead = num_batches * 2  # 2 segundos de pausa por lote
        total_estimated = processing_time + batch_overhead
        
        return {
            "total_files": total_files,
            "num_batches": num_batches,
            "files_per_batch": self.batch_size,
            "estimated_seconds": total_estimated,
            "estimated_minutes": total_estimated / 60,
            "estimated_hours": total_estimated / 3600,
            "files_per_minute": total_files / (total_estimated / 60) if total_estimated > 0 else 0
        }
