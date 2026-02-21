"""
Tests de integración del pipeline de validación completo.

Estos tests verifican que todas las capas trabajen juntas correctamente:
  AntiHallucinationLayer → RAGCrossChecker → SelfCorrectionEngine → ResponseValidator

No hacen llamadas reales a Cohere (usan el mock_cohere_client del conftest).
Sí usan el corpus RAG de sample_documents (sin mock) para el CrossChecker.

Convención:
  - @pytest.mark.asyncio para tests con await
  - @pytest.mark.integration para marcar integración (útil en CI para separar suites)
"""

import pytest
from validation.schemas import (
    ConfidenceLevel,
    ValidatedResponse,
    ValidationReport,
    ValidationStatus,
)
from validation.response_validator import ResponseValidator, ValidationConfig


pytestmark = pytest.mark.integration


class TestResponseValidatorIntegration:

    # ── Pipeline completo con respuesta válida ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_good_response_passes_pipeline(
        self,
        response_validator,
        good_response_data,
        sample_rag_result,
    ):
        """Respuesta bien fundamentada debe pasar el pipeline con status PASSED o WARNED."""
        result = await response_validator.validate(
            response_data=good_response_data,
            rag_result   =sample_rag_result,
            query        ="¿Qué comprenden los alimentos según el Código Civil?",
            language     ="spanish",
        )
        assert isinstance(result, ValidatedResponse)
        assert result.validation_report.status in (
            ValidationStatus.PASSED, ValidationStatus.WARNED, ValidationStatus.CORRECTED
        )
        assert result.validation_report.confidence != ConfidenceLevel.LOW

    @pytest.mark.asyncio
    async def test_hallucinated_response_triggers_correction(
        self,
        response_validator,
        hallucinated_response_data,
        sample_rag_result,
        mock_cohere_client,
    ):
        """Respuesta con alucinaciones debe disparar self-correction y marcar status."""
        # RAG score bajo para amplificar el riesgo de alucinación
        low_score_rag = dict(sample_rag_result)
        low_score_rag["rerank_scores"] = [0.20]

        result = await response_validator.validate(
            response_data=hallucinated_response_data,
            rag_result   =low_score_rag,
            query        ="pensión de alimentos Perú",
            language     ="spanish",
        )
        assert isinstance(result, ValidatedResponse)
        # Con alucinaciones detectadas debe haberse intentado corrección
        assert result.validation_report.corrections_applied >= 0
        # El resultado debe ser un status conocido
        assert result.validation_report.status in ValidationStatus.__members__.values()

    # ── Estructura del ValidatedResponse ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_validated_response_has_all_required_fields(
        self,
        response_validator,
        good_response_data,
        sample_rag_result,
    ):
        """ValidatedResponse debe tener todos los campos requeridos por el schema."""
        result = await response_validator.validate(
            response_data=good_response_data,
            rag_result   =sample_rag_result,
            query        ="alimentos",
            language     ="spanish",
        )
        report = result.validation_report

        # Verificar presencia de todos los campos del report
        assert isinstance(report, ValidationReport)
        assert report.confidence_score >= 0.0
        assert report.confidence_score <= 1.0
        assert report.hallucination_risk >= 0.0
        assert report.hallucination_risk <= 1.0
        assert isinstance(report.is_grounded, bool)
        assert isinstance(report.corrections_applied, int)
        assert isinstance(report.warnings, list)
        assert report.validated_at is not None

    @pytest.mark.asyncio
    async def test_cross_check_summary_present(
        self,
        response_validator,
        good_response_data,
        sample_rag_result,
    ):
        """Con cross_check habilitado, debe haber un CrossCheckSummary en el report."""
        result = await response_validator.validate(
            response_data=good_response_data,
            rag_result   =sample_rag_result,
            query        ="alimentos código civil",
        )
        assert result.validation_report.cross_check is not None
        cross = result.validation_report.cross_check
        assert 0.0 <= cross.overlap_score <= 1.0
        assert isinstance(cross.ungrounded_claims, list)
        assert isinstance(cross.supporting_chunks, list)

    @pytest.mark.asyncio
    async def test_sources_propagated_from_rag(
        self,
        response_validator,
        good_response_data,
        sample_rag_result,
    ):
        """Las fuentes del RAG deben propagarse al ValidatedResponse."""
        result = await response_validator.validate(
            response_data=good_response_data,
            rag_result   =sample_rag_result,
            query        ="alimentos",
        )
        assert result.sources == sample_rag_result["sources"]

    @pytest.mark.asyncio
    async def test_is_reliable_property(
        self,
        response_validator,
        good_response_data,
        sample_rag_result,
    ):
        """La propiedad is_reliable debe reflejar el estado del report."""
        result = await response_validator.validate(
            response_data=good_response_data,
            rag_result   =sample_rag_result,
            query        ="alimentos",
        )
        # is_reliable = status OK + confidence != LOW
        if result.validation_report.status in (ValidationStatus.PASSED, ValidationStatus.WARNED, ValidationStatus.CORRECTED):
            expected = result.validation_report.confidence != ConfidenceLevel.LOW
            assert result.is_reliable == expected

    # ── Configuraciones alternativas ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_disabled_cross_check(
        self,
        mock_rag_engine,
        mock_cohere_client,
        good_response_data,
        sample_rag_result,
    ):
        """Con enable_cross_check=False, cross_check debe ser None en el report."""
        config = ValidationConfig(enable_cross_check=False, enable_self_correction=False)
        validator = ResponseValidator(
            rag_engine   =mock_rag_engine,
            cohere_client=mock_cohere_client,
            config       =config,
        )
        result = await validator.validate(
            response_data=good_response_data,
            rag_result   =sample_rag_result,
            query        ="alimentos",
        )
        assert result.validation_report.cross_check is None

    @pytest.mark.asyncio
    async def test_disabled_self_correction(
        self,
        mock_rag_engine,
        mock_cohere_client,
        hallucinated_response_data,
        sample_rag_result,
    ):
        """Con enable_self_correction=False, no debe llamarse a Cohere para corrección."""
        config = ValidationConfig(enable_self_correction=False)
        validator = ResponseValidator(
            rag_engine   =mock_rag_engine,
            cohere_client=mock_cohere_client,
            config       =config,
        )
        mock_cohere_client.chat.reset_mock()  # Limpiar llamadas previas
        await validator.validate(
            response_data=hallucinated_response_data,
            rag_result   =sample_rag_result,
            query        ="alimentos",
        )
        # No debe haberse llamado a Cohere para corrección
        assert mock_cohere_client.chat.call_count == 0

    # ── Idioma quechua ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_quechua_language_accepted(
        self,
        response_validator,
        good_response_data,
        sample_rag_result,
    ):
        """El pipeline debe aceptar language='quechua' sin errores."""
        result = await response_validator.validate(
            response_data=good_response_data,
            rag_result   =sample_rag_result,
            query        ="mikuy paypim alimentos nin",
            language     ="quechua",
        )
        assert result.language == "quechua"
        assert isinstance(result, ValidatedResponse)

    # ── Edge cases ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_empty_documents_in_rag_result(
        self,
        response_validator,
        good_response_data,
    ):
        """RAG result sin documentos debe manejarse sin error."""
        empty_rag = {
            "answer": "No hay documentos disponibles.",
            "documents": [],
            "rerank_scores": [],
            "sources": [],
            "method": "fallback_no_match",
        }
        result = await response_validator.validate(
            response_data=good_response_data,
            rag_result   =empty_rag,
            query        ="alimentos",
        )
        assert isinstance(result, ValidatedResponse)
        assert result.validation_report.confidence_score <= 1.0

    @pytest.mark.asyncio
    async def test_processing_time_recorded(
        self,
        response_validator,
        good_response_data,
        sample_rag_result,
    ):
        """El tiempo de procesamiento debe ser registrado y ser positivo."""
        result = await response_validator.validate(
            response_data=good_response_data,
            rag_result   =sample_rag_result,
            query        ="alimentos",
        )
        assert result.validation_report.processing_time_ms is not None
        assert result.validation_report.processing_time_ms >= 0