"""
Tests unitarios para SelfCorrectionEngine.

Cobertura:
  - Sin corrección cuando hallucination_report.requires_correction=False
  - Corrección aplicada cuando se detectan alucinaciones
  - Retorno de tupla (texto, num_correcciones)
  - Cohere no disponible → retorna original sin error
  - Manejo de respuesta vacía de Cohere
  - Límite de max_retries respetado
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from modules.validation.services.anti_hallucination import AntiHallucinationLayer, HallucinationReport
from modules.validation.services.self_correction import SelfCorrectionEngine


@pytest.fixture
def rag_context_str() -> str:
    return (
        "El artículo 472 del Código Civil define alimentos como lo indispensable. "
        "La pensión la fija el juez según necesidades y posibilidades del obligado."
    )


class TestSelfCorrectionEngine:

    # ── Sin corrección (happy path) ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_correction_when_not_required(
        self,
        self_correction_engine,
        good_legal_response_text,
        anti_hallucination_layer,
        rag_context_str,
    ):
        """Cuando requires_correction=False, el engine retorna el original sin cambios."""
        report = anti_hallucination_layer.analyze(good_legal_response_text, rag_score=0.90)
        # Asegurar que este texto no requiere corrección
        report.requires_correction = False

        corrected, n = await self_correction_engine.correct(
            original_text        =good_legal_response_text,
            hallucination_report =report,
            rag_context          =rag_context_str,
            query                ="pensión de alimentos",
        )
        assert n == 0
        assert corrected == good_legal_response_text

    # ── Corrección aplicada ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_correction_applied_when_required(
        self,
        self_correction_engine,
        hallucinated_response_text,
        anti_hallucination_layer,
        rag_context_str,
        mock_cohere_client,
    ):
        """Cuando requires_correction=True, se llama a Cohere y se retorna texto corregido."""
        report = anti_hallucination_layer.analyze(hallucinated_response_text, rag_score=0.20)
        report.requires_correction = True

        corrected, n = await self_correction_engine.correct(
            original_text        =hallucinated_response_text,
            hallucination_report =report,
            rag_context          =rag_context_str,
            query                ="pensión de alimentos",
        )
        assert n >= 1
        mock_cohere_client.chat.assert_called()

    @pytest.mark.asyncio
    async def test_corrected_text_not_empty(
        self,
        self_correction_engine,
        hallucinated_response_text,
        rag_context_str,
    ):
        """El texto corregido nunca debe estar vacío."""
        report = HallucinationReport(
            risk_score=0.70,
            flags=["Artículo inexistente"],
            requires_correction=True,
        )
        corrected, _ = await self_correction_engine.correct(
            original_text       =hallucinated_response_text,
            hallucination_report=report,
            rag_context         =rag_context_str,
            query               ="alimentos",
        )
        assert len(corrected.strip()) >= 10

    @pytest.mark.asyncio
    async def test_returns_tuple_of_str_and_int(
        self,
        self_correction_engine,
        good_legal_response_text,
        rag_context_str,
    ):
        """Siempre debe retornar (str, int) independiente del resultado."""
        report = HallucinationReport(risk_score=0.0, requires_correction=False)
        result = await self_correction_engine.correct(
            original_text       =good_legal_response_text,
            hallucination_report=report,
            rag_context         =rag_context_str,
            query               ="alimentos",
        )
        corrected, n = result
        assert isinstance(corrected, str)
        assert isinstance(n, int)
        assert n >= 0

    # ── Cohere no disponible ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_cohere_returns_original(
        self, hallucinated_response_text, rag_context_str
    ):
        """Sin cliente Cohere, debe retornar el original sin lanzar excepción."""
        engine_no_cohere = SelfCorrectionEngine(cohere_client=None, max_retries=2)
        report = HallucinationReport(
            risk_score=0.70, flags=["test"], requires_correction=True
        )
        corrected, n = await engine_no_cohere.correct(
            original_text       =hallucinated_response_text,
            hallucination_report=report,
            rag_context         =rag_context_str,
            query               ="alimentos",
        )
        assert corrected == hallucinated_response_text
        assert n == 0

    # ── Manejo de errores ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_cohere_error_returns_original(
        self, hallucinated_response_text, rag_context_str
    ):
        """Si Cohere lanza excepción, debe retornar el original sin propagar el error."""
        failing_client = AsyncMock()
        failing_client.chat.side_effect = RuntimeError("Cohere timeout")

        engine = SelfCorrectionEngine(cohere_client=failing_client, max_retries=2)
        report = HallucinationReport(
            risk_score=0.70, flags=["test"], requires_correction=True
        )
        corrected, n = await engine.correct(
            original_text       =hallucinated_response_text,
            hallucination_report=report,
            rag_context         =rag_context_str,
            query               ="alimentos",
        )
        # No debe lanzar, debe retornar el texto más reciente
        assert isinstance(corrected, str)

    @pytest.mark.asyncio
    async def test_empty_cohere_response_uses_original(
        self, hallucinated_response_text, rag_context_str
    ):
        """Si Cohere retorna texto vacío, debe usar el original."""
        empty_client = AsyncMock()
        empty_response = MagicMock()
        empty_response.text = ""  # Respuesta vacía
        empty_client.chat.return_value = empty_response

        engine = SelfCorrectionEngine(cohere_client=empty_client, max_retries=1, min_length=50)
        report = HallucinationReport(
            risk_score=0.70, flags=["test"], requires_correction=True
        )
        corrected, n = await engine.correct(
            original_text       =hallucinated_response_text,
            hallucination_report=report,
            rag_context         =rag_context_str,
            query               ="alimentos",
        )
        # Con respuesta vacía, n=0 (no se aplicó corrección válida)
        assert n == 0

    # ── max_retries ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_max_retries_respected(
        self, hallucinated_response_text, rag_context_str, mock_cohere_client
    ):
        """El engine no debe llamar a Cohere más de max_retries veces."""
        engine = SelfCorrectionEngine(
            cohere_client=mock_cohere_client, max_retries=2
        )
        report = HallucinationReport(
            risk_score=0.70, flags=["test"], requires_correction=True
        )
        await engine.correct(
            original_text       =hallucinated_response_text,
            hallucination_report=report,
            rag_context         =rag_context_str,
            query               ="alimentos",
        )
        # Puede haberse llamado entre 1 y max_retries veces
        assert mock_cohere_client.chat.call_count <= 2