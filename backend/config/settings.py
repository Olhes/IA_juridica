from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
import os
from pathlib import Path

class Settings(BaseSettings):
    """Configuración centralizada del sistema IA Jurídica"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Configuración del Servidor
    APP_NAME: str = "IA Jurídica"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Entorno
    NODE_ENV: str = "development"
    ENVIRONMENT: str = "development"
    
    # Configuración de Base de Datos
    DATABASE_URL: str = "sqlite:///./juridica.db"
    DATABASE_PATH: str = "./database/juridica.db"
    
    # Configuración de OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4"
    OPENAI_MAX_TOKENS: int = 1500
    OPENAI_TEMPERATURE: float = 0.7
    
    # Configuración de Documentos
    DOCS_ROOT_DIR: str = "./docs"
    RAW_PDF_DIR: str = "./docs/raw_pdfs"
    PROCESSED_DIR: str = "./docs/processed"
    KNOWLEDGE_GRAPH_DIR: str = "./docs/knowledge_graph"
    FAILED_DIR: str = "./docs/failed"
    
    # Configuración de RAG
    RAG_ENGINE: str = "lightrag"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 768
    MAX_CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    # Configuración de Evaluación
    EVALUATION_ENABLED: bool = True
    DEEPEVAL_API_KEY: Optional[str] = None
    EVALUATION_THRESHOLD: float = 0.7
    
    # Configuración de Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/juridica.log"
    LOG_MAX_SIZE: str = "10MB"
    LOG_BACKUP_COUNT: int = 5
    
    # Configuración de Seguridad
    SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30
    
    # Configuración de Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 900
    RATE_LIMIT_WINDOW_MS: int = 900000
    RATE_LIMIT_MAX_REQUESTS: int = 100
    
    # Configuración de CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:3001"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # Configuración de Archivos
    MAX_FILE_SIZE: int = 50 * 1024 * 1024
    ALLOWED_FILE_TYPES: List[str] = [".pdf", ".doc", ".docx", ".txt"]
    
    # Configuración de Traducción
    TRANSLATION_ENABLED: bool = True
    NLLB_MODEL: str = "facebook/nllb-200-distilled-600M"
    QUEEN_MODEL: Optional[str] = None
    
    # Configuración de Monitoreo
    OPIK_ENABLED: bool = False
    OPIK_API_KEY: Optional[str] = None
    OPIK_PROJECT: str = "ia-juridica"
    
    # Configuración de Cache
    CACHE_ENABLED: bool = True
    CACHE_TTL: int = 3600
    CACHE_MAX_SIZE: int = 1000
    
    # Configuración de PDF
    PDF_GENERATION_ENABLED: bool = True
    PDF_TEMPLATE_DIR: str = "./templates/pdf"
    PDF_OUTPUT_DIR: str = "./temp/pdfs"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._create_directories()
    
    def _create_directories(self):
        """Crea directorios necesarios"""
        directories = [
            self.DOCS_ROOT_DIR,
            self.RAW_PDF_DIR,
            self.PROCESSED_DIR,
            self.KNOWLEDGE_GRAPH_DIR,
            self.FAILED_DIR,
            self.DATABASE_PATH.rsplit('/', 1)[0],
            self.LOG_FILE.rsplit('/', 1)[0],
            self.PDF_OUTPUT_DIR,
            self.PDF_TEMPLATE_DIR
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    def is_development(self) -> bool:
        return self.DEBUG or self.ENVIRONMENT.lower() == "development"
    
    def is_production(self) -> bool:
        return not self.is_development()
    
    def get_openai_config(self) -> dict:
        return {
            "api_key": self.OPENAI_API_KEY,
            "model": self.OPENAI_MODEL,
            "max_tokens": self.OPENAI_MAX_TOKENS,
            "temperature": self.OPENAI_TEMPERATURE
        }
    
    def get_rag_config(self) -> dict:
        return {
            "engine": self.RAG_ENGINE,
            "embedding_model": self.EMBEDDING_MODEL,
            "embedding_dim": self.EMBEDDING_DIM,
            "max_chunk_size": self.MAX_CHUNK_SIZE,
            "chunk_overlap": self.CHUNK_OVERLAP,
            "working_dir": self.KNOWLEDGE_GRAPH_DIR
        }
    
    def validate_configuration(self) -> dict:
        issues = []
        warnings = []
        
        if not self.OPENAI_API_KEY:
            issues.append("OPENAI_API_KEY no está configurada")
        
        if self.SECRET_KEY == "your-secret-key-change-in-production" and self.is_production():
            issues.append("SECRET_KEY debe ser cambiada en producción")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "configuration_summary":{
                "app_name":self.APP_NAME,
                "version":self.APP_VERSION
            }
        }

settings = Settings()
