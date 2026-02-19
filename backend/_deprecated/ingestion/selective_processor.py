import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger
import time

class SelectivePDFProcessor:
    """Procesador selectivo de PDFs - elige qué procesar"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        
    async def process_by_category(self, 
                                 categories: List[str] = None,
                                 exclude_categories: List[str] = None,
                                 max_files: int = None) -> Dict[str, Any]:
        """
        Procesa PDFs por categorías específicas
        
        Args:
            categories: Lista de categorías a procesar ['violencia_familiar', 'pension_alimentos']
            exclude_categories: Categorías a excluir
            max_files: Máximo número de archivos a procesar
            
        Returns:
            Dict con resultados del procesamiento selectivo
        """
        # Importación diferida para evitar errores
        from ingestion.optimized_pipeline import OptimizedLegalIngestionPipeline
        
        raw_dir = Path("docs/raw_pdfs")
        all_pdfs = list(raw_dir.glob("**/*.pdf"))
        
        # Filtrar por categorías
        selected_pdfs = self._filter_by_categories(all_pdfs, categories, exclude_categories)
        
        # Limitar número de archivos
        if max_files and len(selected_pdfs) > max_files:
            selected_pdfs = selected_pdfs[:max_files]
        
        logger.info(f"📋 Procesando {len(selected_pdfs)} PDFs seleccionados")
        logger.info(f"📂 Categorías: {categories or 'Todas'}")
        logger.info(f"🚫 Excluidas: {exclude_categories or 'Ninguna'}")
        
        # Crear pipeline y procesar
        pipeline = OptimizedLegalIngestionPipeline(max_workers=self.max_workers)
        
        start_time = time.time()
        results = await pipeline.process_all_pdfs_parallel()
        total_time = time.time() - start_time
        
        return {
            "selected_files": len(selected_pdfs),
            "categories": categories,
            "excluded_categories": exclude_categories,
            "processing_results": results,
            "total_time": total_time,
            "files_processed": results.get("processed_count", 0),
            "files_failed": results.get("failed_count", 0)
        }
    
    async def process_by_keywords(self,
                                 keywords: List[str],
                                 exclude_keywords: List[str] = None,
                                 max_files: int = None) -> Dict[str, Any]:
        """
        Procesa PDFs que contienen palabras clave en el nombre
        
        Args:
            keywords: Palabras clave a buscar ['guía', 'manual', 'formulario']
            exclude_keywords: Palabras clave a excluir
            max_files: Máximo número de archivos
            
        Returns:
            Dict con resultados
        """
        # Importación diferida
        from ingestion.optimized_pipeline import OptimizedLegalIngestionPipeline
        
        raw_dir = Path("docs/raw_pdfs")
        all_pdfs = list(raw_dir.glob("**/*.pdf"))
        
        # Filtrar por palabras clave
        selected_pdfs = []
        for pdf in all_pdfs:
            filename = pdf.name.lower()
            
            # Verificar inclusiones
            included = any(keyword.lower() in filename for keyword in keywords) if keywords else True
            
            # Verificar exclusiones
            excluded = any(keyword.lower() in filename for keyword in exclude_keywords) if exclude_keywords else False
            
            if included and not excluded:
                selected_pdfs.append(pdf)
        
        # Limitar número
        if max_files and len(selected_pdfs) > max_files:
            selected_pdfs = selected_pdfs[:max_files]
        
        logger.info(f"🔍 Procesando {len(selected_pdfs)} PDFs por palabras clave")
        logger.info(f"✅ Keywords: {keywords}")
        logger.info(f"❌ Excluded: {exclude_keywords}")
        
        # Procesar
        pipeline = OptimizedLegalIngestionPipeline(max_workers=self.max_workers)
        start_time = time.time()
        results = await pipeline.process_all_pdfs_parallel()
        total_time = time.time() - start_time
        
        return {
            "selected_files": len(selected_pdfs),
            "keywords": keywords,
            "excluded_keywords": exclude_keywords,
            "processing_results": results,
            "total_time": total_time,
            "files_processed": results.get("processed_count", 0),
            "files_failed": results.get("failed_count", 0)
        }
    
    async def process_specific_files(self,
                                  file_names: List[str],
                                  force_reprocess: bool = False) -> Dict[str, Any]:
        """
        Procesa archivos específicos por nombre
        
        Args:
            file_names: Lista exacta de nombres de archivo
            force_reprocess: Forzar reprocesamiento aunque estén en cache
            
        Returns:
            Dict con resultados
        """
        # Importación diferida
        from ingestion.optimized_pipeline import OptimizedLegalIngestionPipeline
        
        raw_dir = Path("docs/raw_pdfs")
        selected_pdfs = []
        
        for file_name in file_names:
            pdf_path = raw_dir / file_name
            if pdf_path.exists():
                selected_pdfs.append(pdf_path)
            else:
                # Buscar recursivamente
                found = list(raw_dir.glob(f"**/{file_name}"))
                if found:
                    selected_pdfs.extend(found)
                else:
                    logger.warning(f"❌ No encontrado: {file_name}")
        
        logger.info(f"📄 Procesando {len(selected_pdfs)} archivos específicos")
        
        # Si forzar reprocesamiento, limpiar cache de estos archivos
        if force_reprocess:
            await self._clear_cache_for_files(selected_pdfs)
        
        # Procesar
        pipeline = OptimizedLegalIngestionPipeline(max_workers=self.max_workers)
        start_time = time.time()
        results = await pipeline.process_all_pdfs_parallel()
        total_time = time.time() - start_time
        
        return {
            "requested_files": len(file_names),
            "found_files": len(selected_pdfs),
            "file_names": file_names,
            "force_reprocess": force_reprocess,
            "processing_results": results,
            "total_time": total_time,
            "files_processed": results.get("processed_count", 0),
            "files_failed": results.get("failed_count", 0)
        }
    
    def _filter_by_categories(self, 
                             all_pdfs: List[Path], 
                             categories: List[str] = None,
                             exclude_categories: List[str] = None) -> List[Path]:
        """Filtra PDFs por categorías (carpetas)"""
        selected = []
        
        for pdf in all_pdfs:
            relative_path = pdf.relative_to(Path("docs/raw_pdfs"))
            category = str(relative_path.parts[0]) if len(relative_path.parts) > 0 else "root"
            
            # Verificar inclusiones
            included = (category in categories) if categories else True
            
            # Verificar exclusiones
            excluded = (category in exclude_categories) if exclude_categories else False
            
            if included and not excluded:
                selected.append(pdf)
        
        return selected
    
    async def _clear_cache_for_files(self, pdf_files: List[Path]):
        """Limpia cache para archivos específicos"""
        from ingestion.cache_manager import CacheManager
        
        cache_manager = CacheManager()
        for pdf in pdf_files:
            cache_manager.mark_as_unprocessed(pdf)
        
        logger.info(f"🗑️  Cache limpiado para {len(pdf_files)} archivos")
    
    def list_available_options(self) -> Dict[str, Any]:
        """Lista todas las opciones disponibles para selección"""
        raw_dir = Path("docs/raw_pdfs")
        
        # Categorías disponibles
        categories = {}
        for pdf in raw_dir.glob("**/*.pdf"):
            relative_path = pdf.relative_to(raw_dir)
            category = str(relative_path.parts[0]) if len(relative_path.parts) > 0 else "root"
            
            if category not in categories:
                categories[category] = []
            categories[category].append(pdf.name)
        
        # Todos los archivos
        all_files = [pdf.name for pdf in raw_dir.glob("**/*.pdf")]
        
        # Palabras clave comunes
        common_keywords = set()
        for filename in all_files:
            words = filename.lower().replace('.pdf', '').replace('_', ' ').split()
            common_keywords.update(words)
        
        return {
            "categories": categories,
            "total_files": len(all_files),
            "all_files": sorted(all_files),
            "common_keywords": sorted(list(common_keywords))
        }
