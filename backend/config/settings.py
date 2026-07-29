from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional, Dict, Any
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
    DATABASE_HOST: str = os.getenv("DATABASE_HOST", "localhost")
    DATABASE_PORT: int = int(os.getenv("DATABASE_PORT", "5433"))
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "juridica_db")
    DATABASE_USER: str = os.getenv("DATABASE_USER", "postgres")
    DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"postgresql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}")
    
    # Configuración de SQLAlchemy para PostgreSQL (chat persistente)
    # Usando psycopg en lugar de asyncpg por compatibilidad con Windows
    SQLALCHEMY_DATABASE_URL: str = os.getenv("SQLALCHEMY_DATABASE_URL", f"postgresql+psycopg://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}")
    
    # Configuración de Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    
    # Configuración de SQLAlchemy
    SQLALCHEMY_ECHO: bool = False
    SQLALCHEMY_POOL_SIZE: int = 10
    SQLALCHEMY_MAX_OVERFLOW: int = 20
    
    # Configuración de OpenAI (legacy)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5-mini"
    OPENAI_MAX_COMPLETION_TOKENS: int = 1500
    OPENAI_TEMPERATURE: float = 0.7
    
    # Configuración de Cohere (principal)
    COHERE_API_KEY: str = os.getenv("COHERE_API_KEY", "")
    COHERE_EMBED_MODEL: str = "embed-multilingual-v3.0"
    COHERE_RERANK_MODEL: str = "rerank-multilingual-v3.0"
    COHERE_LLM_MODEL: str = "command-r7b-12-2024"
    COHERE_MAX_TOKENS: int = 512
    COHERE_TEMPERATURE: float = 0.3
    
    # Configuración de Neo4j
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "")
    NEO4J_DATABASE: str = os.getenv("NEO4J_DATABASE", "neo4j")
    NEO4J_ENABLED: bool = os.getenv("NEO4J_ENABLED", "false").lower() == "true"
    
    # Configuración de Knowledge Graph local
    LOAD_LOCAL_KG: bool = os.getenv("LOAD_LOCAL_KG", "false").lower() == "true"  # Deshabilitado en producción
    
    # Configuración de Reranking
    RERANK_TOP_K: int = 5
    RERANK_CANDIDATES: int = 50
    
    # Configuración de Documentos
    DOCS_ROOT_DIR: str = "./docs"
    RAW_PDF_DIR: str = "./docs/raw_pdfs"
    PROCESSED_DIR: str = "./docs/processed"
    KNOWLEDGE_GRAPH_DIR: str = "./docs/knowledge_graph"
    FAILED_DIR: str = "./docs/failed"
    
    # Configuración de RAG
    RAG_ENGINE: str = "lightrag"
    EMBEDDING_MODEL: str = "embed-multilingual-v3.0"
    EMBEDDING_DIM: int = 1024
    MAX_CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    EMBEDDING_BATCH_SIZE: int = 96  # Límite de Cohere por llamada
    
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
    ANONYMOUS_SESSION_SECRET: str = "local-development-session-secret-change-me"
    ANONYMOUS_SESSION_COOKIE_NAME: str = "ia_juridica_session"
    ANONYMOUS_SESSION_COOKIE_DOMAIN: Optional[str] = None
    ANONYMOUS_SESSION_COOKIE_SAMESITE: str = "lax"
    ANONYMOUS_SESSION_COOKIE_SECURE: bool = False
    ANONYMOUS_SESSION_TTL_DAYS: int = 30
    ADMIN_ENDPOINTS_ENABLED: bool = False
    ADMIN_API_KEY: Optional[str] = None
    API_DOCS_ENABLED: Optional[bool] = None
    
    # Configuración de Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 900
    RATE_LIMIT_WINDOW_MS: int = 900000
    RATE_LIMIT_MAX_REQUESTS: int = 100
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    LLM_RATE_LIMIT: str = "10/minute"
    CONVERSATION_CREATE_RATE_LIMIT: str = "20/hour"
    ADMIN_RATE_LIMIT: str = "5/hour"
    SESSION_BOOTSTRAP_RATE_LIMIT: str = "20/hour"
    
    # Configuración de CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:3001", "https://ia-juridica-frontend.onrender.com"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: List[str] = ["Content-Type", "X-API-Key", "X-Request-ID"]
    
    # Configuración de Archivos
    MAX_FILE_SIZE: int = 50 * 1024 * 1024
    ALLOWED_FILE_TYPES: List[str] = [".pdf", ".doc", ".docx", ".txt"]
    
    # Configuración de Traducción
    TRANSLATION_ENABLED: bool = True
    TRANSLATION_METHOD: str = "google_translate"
    
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

    def docs_enabled(self) -> bool:
        if self.API_DOCS_ENABLED is not None:
            return self.API_DOCS_ENABLED
        return self.is_development()

    def session_cookie_secure(self) -> bool:
        return self.is_production() or self.ANONYMOUS_SESSION_COOKIE_SECURE
    
    def get_openai_config(self) -> dict:
        """Configuración OpenAI (legacy)"""
        return {
            "api_key": self.OPENAI_API_KEY,
            "model": self.OPENAI_MODEL,
            "max_completion_tokens": self.OPENAI_MAX_COMPLETION_TOKENS,
            "temperature": self.OPENAI_TEMPERATURE
        }
    
    def get_cohere_config(self) -> Dict[str, Any]:
        """Configuración Cohere (principal)"""
        return {
            "api_key": self.COHERE_API_KEY,
            "embed_model": self.COHERE_EMBED_MODEL,
            "rerank_model": self.COHERE_RERANK_MODEL,
            "llm_model": self.COHERE_LLM_MODEL,
            "max_tokens": self.COHERE_MAX_TOKENS,
            "temperature": self.COHERE_TEMPERATURE,
            "embedding_dim": self.EMBEDDING_DIM,
            "rerank_top_k": self.RERANK_TOP_K,
            "rerank_candidates": self.RERANK_CANDIDATES,
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
        
        if not self.COHERE_API_KEY:
            issues.append("COHERE_API_KEY no está configurada")
        
        if not self.OPENAI_API_KEY:
            warnings.append("OPENAI_API_KEY no está configurada (legacy, opcional)")
        
        if self.is_production():
            if (
                len(self.ANONYMOUS_SESSION_SECRET.encode("utf-8")) < 32
                or self.ANONYMOUS_SESSION_SECRET == "local-development-session-secret-change-me"
            ):
                issues.append("ANONYMOUS_SESSION_SECRET debe ser aleatorio y tener al menos 32 bytes en producción")
            if not self.session_cookie_secure():
                issues.append("La cookie anónima debe usar Secure en producción")
            if "*" in self.CORS_ORIGINS or not self.CORS_ORIGINS:
                issues.append("CORS_ORIGINS debe enumerar orígenes explícitos en producción")
            if "*" in self.CORS_ALLOW_METHODS or "*" in self.CORS_ALLOW_HEADERS:
                issues.append("CORS methods/headers no pueden usar wildcard en producción")
            if self.RATE_LIMIT_ENABLED and self.RATE_LIMIT_STORAGE_URI == "memory://":
                issues.append("RATE_LIMIT_STORAGE_URI debe ser compartido entre workers en producción")
            if not self.DATABASE_PASSWORD and not os.getenv("DATABASE_URL"):
                issues.append("DATABASE_PASSWORD o DATABASE_URL es obligatorio en producción")

        if self.ANONYMOUS_SESSION_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
            issues.append("ANONYMOUS_SESSION_COOKIE_SAMESITE debe ser lax, strict o none")
        if self.ANONYMOUS_SESSION_COOKIE_SAMESITE == "none" and not self.session_cookie_secure():
            issues.append("SameSite=None requiere Secure")
        if self.ADMIN_ENDPOINTS_ENABLED and not self.ADMIN_API_KEY:
            issues.append("ADMIN_API_KEY es obligatoria cuando los endpoints admin están habilitados")
        
        if self.EMBEDDING_DIM != 1024:
            warnings.append(f"EMBEDDING_DIM es {self.EMBEDDING_DIM}, se esperan 1024 para Cohere embed-multilingual-v3.0")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "configuration_summary":{
                "app_name": self.APP_NAME,
                "version": self.APP_VERSION,
                "llm_provider": "cohere",
                "llm_model": self.COHERE_LLM_MODEL,
                "embed_model": self.COHERE_EMBED_MODEL,
            }
        }

settings = Settings()
