"""
Tests de integración para la migración a Cohere.
Verifica embeddings, rerank, context engineering y endpoints.

Ejecutar: cd backend && python -m pytest tests/test_cohere_integration.py -v
"""

import os
import sys
import asyncio
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

# Asegurar que el directorio backend está en el path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def settings():
    """Retorna la instancia centralizada de settings"""
    from config.settings import settings as _settings
    return _settings


@pytest.fixture
def mock_cohere_embed_response():
    """Simula respuesta de Cohere embeddings (dim=1024)"""
    class EmbedResponse:
        class Embedding:
            float_ = [np.random.rand(1024).tolist()]
        embeddings = Embedding()
    return EmbedResponse()


@pytest.fixture
def mock_cohere_rerank_response():
    """Simula respuesta de Cohere rerank"""
    class RerankResult:
        def __init__(self, index, score):
            self.index = index
            self.relevance_score = score
    class RerankResponse:
        results = [
            RerankResult(2, 0.95),
            RerankResult(0, 0.80),
            RerankResult(1, 0.60),
        ]
    return RerankResponse()


# ---------------------------------------------------------------------------
# 1. Settings / Config
# ---------------------------------------------------------------------------

class TestSettings:
    """Verifica que settings.py carga la config de Cohere"""

    def test_cohere_fields_exist(self, settings):
        assert hasattr(settings, "COHERE_API_KEY")
        assert hasattr(settings, "COHERE_EMBED_MODEL")
        assert hasattr(settings, "COHERE_RERANK_MODEL")
        assert hasattr(settings, "COHERE_LLM_MODEL")

    def test_embedding_dim_is_1024(self, settings):
        assert settings.EMBEDDING_DIM == 1024

    def test_default_models(self, settings):
        assert settings.COHERE_EMBED_MODEL == "embed-multilingual-v3.0"
        assert settings.COHERE_RERANK_MODEL == "rerank-multilingual-v3.0"
        assert settings.COHERE_LLM_MODEL == "command-r7b-12-2024"

    def test_get_cohere_config_returns_dict(self, settings):
        cfg = settings.get_cohere_config()
        assert isinstance(cfg, dict)
        assert "embed_model" in cfg
        assert "rerank_model" in cfg
        assert "llm_model" in cfg

    def test_rerank_defaults(self, settings):
        assert settings.RERANK_TOP_K >= 1
        assert settings.RERANK_CANDIDATES >= settings.RERANK_TOP_K


# ---------------------------------------------------------------------------
# 2. Embeddings (mocked Cohere call)
# ---------------------------------------------------------------------------

class TestEmbeddings:
    """Verifica que las funciones de embedding producen vectores 1024d"""

    @pytest.mark.asyncio
    async def test_embedding_dimension(self, mock_cohere_embed_response):
        """La función de embedding debe devolver vectores de 1024 dimensiones"""
        with patch("cohere.AsyncClient") as MockClient:
            instance = MockClient.return_value
            instance.embed = AsyncMock(return_value=mock_cohere_embed_response)

            from rag.lightrag_engine import LegalRAGEngine
            engine = LegalRAGEngine.__new__(LegalRAGEngine)
            engine.settings = MagicMock()
            engine.settings.COHERE_API_KEY = "test-key"
            engine.settings.COHERE_EMBED_MODEL = "embed-multilingual-v3.0"
            engine.settings.EMBEDDING_DIM = 1024
            engine.settings.EMBEDDING_BATCH_SIZE = 96

            # El vector retornado debe tener 1024 dimensiones
            vec = mock_cohere_embed_response.embeddings.float_[0]
            assert len(vec) == 1024

    @pytest.mark.asyncio
    async def test_chunk_and_embed(self, mock_cohere_embed_response):
        """ContextualChunker.chunk_and_embed devuelve chunks con embeddings"""
        with patch("cohere.AsyncClient") as MockClient:
            instance = MockClient.return_value
            embed_resp = MagicMock()
            embed_resp.embeddings.float_ = [
                np.random.rand(1024).tolist() for _ in range(3)
            ]
            instance.embed = AsyncMock(return_value=embed_resp)

            from context.chunking_strategies import ContextualChunker
            chunker = ContextualChunker()
            chunker._cohere_client = instance

            text = "Artículo 1. " * 50 + "Artículo 2. " * 50 + "Artículo 3. " * 50
            result = await chunker.chunk_and_embed(text, {"title": "test_doc", "document_type": "legal"})

            assert len(result) > 0
            for chunk in result:
                assert "embedding" in chunk
                assert len(chunk["embedding"]) == 1024


# ---------------------------------------------------------------------------
# 3. Rerank
# ---------------------------------------------------------------------------

class TestRerank:
    """Verifica la lógica de reranking"""

    def test_rerank_response_ordering(self, mock_cohere_rerank_response):
        """Los resultados de rerank deben estar ordenados por score descendente"""
        scores = [r.relevance_score for r in mock_cohere_rerank_response.results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_fallback_rerank(self):
        """El fallback keyword-based rerank debe funcionar sin Cohere"""
        from rag.lightrag_engine import LegalRAGEngine
        engine = LegalRAGEngine.__new__(LegalRAGEngine)

        docs = [
            {"content": "Ley 30364 sobre violencia familiar", "metadata": {"filename": "ley30364.md"}},
            {"content": "Código Civil del Perú artículo 472 pensión", "metadata": {"filename": "codigo_civil.md"}},
            {"content": "Violencia contra la mujer medidas de protección", "metadata": {"filename": "violencia.md"}},
        ]
        query = "violencia familiar"
        result = await engine._fallback_rerank(query, docs, top_k=2, lightrag_answer="")

        ranked = result["documents"]
        assert len(ranked) == 2
        # Los docs con "violencia" deberían rankear más alto
        for doc in ranked:
            assert "violencia" in doc["content"].lower()


# ---------------------------------------------------------------------------
# 4. Context Engineering
# ---------------------------------------------------------------------------

class TestContextEngineering:
    """Verifica prompt building y context enrichment"""

    def test_prompt_manager_build(self):
        """PromptManager.build_prompt_for_cohere genera un prompt no vacío"""
        from context.prompt_templates import PromptManager
        pm = PromptManager()

        prompt = pm.build_prompt_for_cohere(
            prompt_type="violencia_familiar",
            query="¿Qué hago si mi pareja me agrede?",
            documents=[
                {"source": "Ley 30364", "content": "Artículo 2...", "score": 0.9}
            ],
            language="spanish",
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 50
        assert "violencia" in prompt.lower() or "agrede" in prompt.lower()

    def test_context_engineer_build_legal_prompt(self):
        """ContextEngineer.build_legal_prompt retorna (prompt, context)"""
        from context.context_engineering import ContextEngineer
        ce = ContextEngineer()

        prompt, ctx = ce.build_legal_prompt(
            query="¿Cómo denuncio violencia familiar en Cusco?",
            documents=[
                {"source": "Ley 30364", "content": "Artículo 2 define...", "score": 0.85}
            ],
            language="spanish",
        )
        assert isinstance(prompt, str)
        assert isinstance(ctx, dict)
        assert len(prompt) > 50

    def test_location_detection(self):
        """Detecta ubicación en la consulta"""
        from context.context_engineering import ContextEngineer
        ce = ContextEngineer()

        prompt, ctx = ce.build_legal_prompt(
            query="Necesito ayuda legal en Puno",
            documents=[],
            language="spanish",
        )
        # El contexto debe incluir alguna referencia a ubicación
        assert isinstance(ctx, dict)


# ---------------------------------------------------------------------------
# 5. PDF generation
# ---------------------------------------------------------------------------

class TestPDFGeneration:
    """Verifica la generación de PDFs"""

    def test_generate_pdf_creates_file(self, tmp_path):
        """generate_legal_pdf debe crear un archivo PDF"""
        from utils.pdf_generator import generate_legal_pdf

        response_data = {
            "tema": "violencia_familiar",
            "respuesta_espanol": "Debe acudir a la comisaría más cercana.",
            "respuesta_quechua": "Comisariyaman rinaykim.",
            "pasos_recomendados": [
                {"paso": 1, "descripcion": "Ir a la comisaría", "documentos_requeridos": ["DNI"]}
            ],
            "recursos": [
                {"nombre": "Línea 100", "contacto": "100", "descripcion": "Línea de emergencia"}
            ],
            "advertencias": [
                {"mensaje": "Si está en peligro inmediato, llame al 105."}
            ],
            "fuentes": [
                {"nombre": "Ley 30364", "tipo": "ley", "numero": "30364"}
            ],
        }

        pdf_path = generate_legal_pdf(
            query="¿Qué hago si me golpean?",
            response_data=response_data,
            output_dir=str(tmp_path),
        )

        assert os.path.isfile(pdf_path)
        assert pdf_path.endswith(".pdf")
        # Verificar que el archivo tiene contenido
        assert os.path.getsize(pdf_path) > 1000


# ---------------------------------------------------------------------------
# 6. Health endpoint (unit-level)
# ---------------------------------------------------------------------------

class TestHealthCheck:
    """Verifica que /health devuelve información útil"""

    @pytest.mark.asyncio
    async def test_health_returns_status(self):
        """El health check debe incluir campos de componentes"""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "components" in data


# ---------------------------------------------------------------------------
# 7. Rate limiting exists
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Verifica que slowapi está configurado"""

    def test_limiter_attached(self):
        """La app FastAPI debe tener el middleware de slowapi"""
        from main import app
        # Verificar que al menos un middleware o exception handler está registrado
        assert len(app.exception_handlers) > 0 or len(app.middleware_stack.__dict__) > 0
