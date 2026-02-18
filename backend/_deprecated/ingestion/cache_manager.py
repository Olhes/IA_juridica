import json
import hashlib
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime
from loguru import logger

class ProcessingCache:
    """
    Gestiona caché de documentos procesados para evitar reprocesamiento
    """
    
    def __init__(self, cache_file: str = "./docs/processing_cache.json"):
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict[str, Any]:
        """Carga caché desde disco"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"No se pudo cargar caché: {e}")
        
        return {
            "processed_files": {},
            "last_updated": datetime.now().isoformat(),
            "version": "1.0"
        }
    
    def _save_cache(self):
        """Guarda caché a disco"""
        try:
            self.cache["last_updated"] = datetime.now().isoformat()
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando caché: {e}")
    
    def get_file_hash(self, file_path: Path) -> str:
        """Calcula hash SHA-256 de un archivo"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Error calculando hash de {file_path}: {e}")
            return ""
    
    def is_processed(self, pdf_path: Path) -> bool:
        """
        Verifica si un PDF ya fue procesado
        
        Args:
            pdf_path: Path al archivo PDF
            
        Returns:
            True si ya fue procesado y no ha cambiado
        """
        relative_path = str(pdf_path.relative_to(Path("docs/raw_pdfs")))
        
        # Verificar si está en caché
        if relative_path not in self.cache["processed_files"]:
            return False
        
        # Verificar si el archivo cambió
        current_hash = self.get_file_hash(pdf_path)
        cached_info = self.cache["processed_files"][relative_path]
        
        if cached_info.get("file_hash") != current_hash:
            logger.info(f"🔄 Archivo modificado: {relative_path}")
            return False
        
        # Verificar si el markdown de salida existe
        output_path = Path("docs/processed") / f"{pdf_path.stem}.md"
        if not output_path.exists():
            logger.info(f"📝 Markdown no encontrado: {relative_path}")
            return False
        
        return True
    
    def mark_processed(self, pdf_path: Path, processing_time: float, content_length: int):
        """
        Marca un archivo como procesado
        
        Args:
            pdf_path: Path al PDF procesado
            processing_time: Tiempo de procesamiento en segundos
            content_length: Longitud del contenido generado
        """
        relative_path = str(pdf_path.relative_to(Path("docs/raw_pdfs")))
        file_hash = self.get_file_hash(pdf_path)
        
        self.cache["processed_files"][relative_path] = {
            "file_hash": file_hash,
            "processed_at": datetime.now().isoformat(),
            "processing_time": processing_time,
            "content_length": content_length,
            "pdf_size": pdf_path.stat().st_size
        }
        
        self._save_cache()
        logger.info(f"✅ Marcado como procesado: {relative_path}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del caché"""
        processed_files = self.cache["processed_files"]
        
        if not processed_files:
            return {
                "total_processed": 0,
                "total_processing_time": 0,
                "average_processing_time": 0,
                "total_content_size": 0
            }
        
        total_time = sum(info.get("processing_time", 0) for info in processed_files.values())
        total_content = sum(info.get("content_length", 0) for info in processed_files.values())
        
        return {
            "total_processed": len(processed_files),
            "total_processing_time": round(total_time, 2),
            "average_processing_time": round(total_time / len(processed_files), 2),
            "total_content_size": total_content,
            "last_updated": self.cache["last_updated"]
        }
    
    def clear_cache(self):
        """Limpia toda la caché"""
        self.cache = {
            "processed_files": {},
            "last_updated": datetime.now().isoformat(),
            "version": "1.0"
        }
        self._save_cache()
        logger.info("🧹 Caché limpiada")
