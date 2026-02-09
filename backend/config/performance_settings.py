from pydantic_settings import BaseSettings
from typing import Optional
import psutil

class PerformanceSettings(BaseSettings):
    """Configuración optimizada para rendimiento de procesamiento"""
    
    # Procesamiento Paralelo
    MAX_WORKERS: int = 4
    ENABLE_PARALLEL_PROCESSING: bool = True
    BATCH_SIZE: int = 10
    
    # Configuración de Docling optimizada
    DOCLING_OCR_ENABLED: bool = True
    DOCLING_TABLE_STRUCTURE: bool = True
    DOCLING_PAGE_IMAGES: bool = False  # Ahorra memoria
    
    # Cache y Memoria
    ENABLE_PROCESSING_CACHE: bool = True
    MAX_MEMORY_USAGE_GB: float = 6.0  # Límite de memoria
    
    # RAG Optimizado
    RAG_BATCH_INSERT_SIZE: int = 5
    ENABLE_INCREMENTAL_INDEXING: bool = True
    
    # Timeout y Reintentos
    PROCESSING_TIMEOUT_SECONDS: int = 300  # 5 minutos por PDF
    MAX_RETRIES: int = 2
    
    # Monitoreo
    ENABLE_PERFORMANCE_LOGGING: bool = True
    LOG_PROCESSING_TIMES: bool = True
    
    class Config:
        env_file = ".env"
        env_prefix = "PERF_"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._auto_optimize_settings()
    
    def _auto_optimize_settings(self):
        """Optimiza configuración basada en hardware disponible"""
        
        # Detectar hardware
        cpu_count = psutil.cpu_count()
        memory_gb = psutil.virtual_memory().total / (1024**3)
        
        # Optimizar workers basado en CPU y memoria
        if memory_gb >= 16:
            self.MAX_WORKERS = min(8, cpu_count)
        elif memory_gb >= 8:
            self.MAX_WORKERS = min(4, cpu_count)
        else:
            self.MAX_WORKERS = min(2, cpu_count)
        
        # Ajustar límite de memoria
        self.MAX_MEMORY_USAGE_GB = min(memory_gb * 0.7, 8.0)
        
        # Deshabilitar features si hay poca memoria
        if memory_gb < 4:
            self.DOCLING_PAGE_IMAGES = False
            self.DOCLING_TABLE_STRUCTURE = False
        
        print(f"🚀 Configuración optimizada: {self.MAX_WORKERS} workers, {self.MAX_MEMORY_USAGE_GB:.1f}GB límite")
    
    def get_docling_config(self) -> dict:
        """Retorna configuración optimizada para Docling"""
        return {
            "ocr_enabled": self.DOCLING_OCR_ENABLED,
            "table_structure": self.DOCLING_TABLE_STRUCTURE,
            "page_images": self.DOCLING_PAGE_IMAGES,
            "timeout": self.PROCESSING_TIMEOUT_SECONDS
        }
    
    def get_performance_profile(self) -> str:
        """Identifica el perfil de rendimiento del sistema"""
        memory_gb = psutil.virtual_memory().total / (1024**3)
        
        if memory_gb >= 16:
            return "high_performance"
        elif memory_gb >= 8:
            return "standard"
        else:
            return "resource_constrained"

# Instancia global
performance_settings = PerformanceSettings()
