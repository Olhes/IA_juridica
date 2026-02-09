from pydantic_settings import BaseSettings
from typing import Optional

class ScalabilitySettings(BaseSettings):
    """Configuración para manejo de grandes volúmenes de documentos"""
    
    # Límites de escalabilidad
    MAX_PDF_FILES: int = 10000
    MAX_STORAGE_GB: int = 500
    MAX_MEMORY_GB: int = 64
    
    # Procesamiento por lotes
    BATCH_SIZE: int = 100
    BATCH_WORKERS: int = 16
    BATCH_TIMEOUT_MINUTES: int = 30
    
    # Base de datos
    USE_POSTGRESQL: bool = True  # Para >1000 PDFs
    POSTGRESQL_MAX_CONNECTIONS: int = 20
    POSTGRESQL_POOL_SIZE: int = 10
    
    # Vector Database escalable
    VECTOR_DB_TYPE: str = "pinecone"  # pinecone, weaviate, chroma
    PINECONE_DIMENSION: int = 768
    PINECONE_POD_TYPE: str = "p1.x1"  # Para producción
    
    # Cache distribuida
    USE_REDIS_CACHE: bool = True
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_MAX_MEMORY: str = "2gb"
    
    # Monitoreo y alertas
    ENABLE_MONITORING: bool = True
    MEMORY_ALERT_THRESHOLD: float = 0.8  # 80% de RAM
    STORAGE_ALERT_THRESHOLD: float = 0.9  # 90% de almacenamiento
    
    class Config:
        env_file = ".env"
        env_prefix = "SCALE_"
    
    def get_resource_requirements(self, num_files: int) -> dict:
        """
        Calcula requisitos de recursos para un número de archivos
        
        Args:
            num_files: Número de archivos a procesar
            
        Returns:
            Dict con requisitos estimados
        """
        # Estimaciones basadas en experiencia
        avg_pdf_size_mb = 25
        avg_markdown_size_mb = 10
        avg_vector_size_mb = 15
        
        total_storage_gb = (
            (num_files * avg_pdf_size_mb) + 
            (num_files * avg_markdown_size_mb) + 
            (num_files * avg_vector_size_mb)
        ) / 1024
        
        required_memory_gb = min(
            (num_files * avg_vector_size_mb) / 1024 * 2,  # Vector DB + overhead
            self.MAX_MEMORY_GB
        )
        
        # Calcular lote óptimo
        optimal_batch_size = min(
            self.BATCH_SIZE,
            max(10, num_files // 20)  # Al menos 20 lotes
        )
        
        # Estimar tiempo
        estimated_minutes = (num_files / self.BATCH_WORKERS) * 0.25  # 15s por archivo
        
        return {
            "num_files": num_files,
            "storage_required_gb": round(total_storage_gb, 1),
            "memory_required_gb": round(required_memory_gb, 1),
            "optimal_batch_size": optimal_batch_size,
            "estimated_minutes": round(estimated_minutes, 1),
            "recommended_setup": self._get_recommended_setup(num_files),
            "cost_estimation": self._estimate_monthly_cost(num_files)
        }
    
    def _get_recommended_setup(self, num_files: int) -> str:
        """Recomienda configuración basada en volumen"""
        if num_files <= 100:
            return "Servidor básico: 8GB RAM, 4 cores, 100GB SSD"
        elif num_files <= 1000:
            return "Servidor estándar: 16GB RAM, 8 cores, 250GB SSD"
        elif num_files <= 5000:
            return "Servidor avanzado: 32GB RAM, 16 cores, 500GB SSD"
        else:
            return "Cluster: Múltiples servidores con balanceo de carga"
    
    def _estimate_monthly_cost(self, num_files: int) -> dict:
        """Estima costos mensuales de infraestructura"""
        storage_gb = (num_files * 50) / 1024  # 50MB por archivo total
        
        if num_files <= 1000:
            return {
                "server_type": "VPS estándar",
                "monthly_cost": 50,
                "storage_cost": storage_gb * 0.1,
                "total_estimated": 50 + (storage_gb * 0.1)
            }
        elif num_files <= 5000:
            return {
                "server_type": "Servidor dedicado",
                "monthly_cost": 200,
                "storage_cost": storage_gb * 0.08,
                "total_estimated": 200 + (storage_gb * 0.08)
            }
        else:
            return {
                "server_type": "Cloud enterprise",
                "monthly_cost": 500,
                "storage_cost": storage_gb * 0.05,
                "total_estimated": 500 + (storage_gb * 0.05)
            }

# Instancia global
scalability_settings = ScalabilitySettings()
