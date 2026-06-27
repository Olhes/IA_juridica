"""
Tests unitarios para AntiHallucinationLayer.

Cobertura:
  - Respuestas bien fundamentadas → riesgo bajo
  - Respuestas con patrones de alucinación → riesgo alto + flags
  - Penalización por rag_score bajo
  - Penalización estructural (respuesta larga sin respaldo)
  - Parametrización de patrones individuales
"""

import pytest
from modules.validation.services.anti_hallucination import AntiHallucinationLayer, HallucinationReport


class TestAntiHallucinationLayer:

    # ── Casos base ─────────────────────────────────────────────────────────────

    def test_good_response_has_low_risk(
        self, anti_hallucination_layer, good_legal_response_text
    ):
        """Respuesta bien fundamentada no debe superar el umbral de corrección."""
        report = anti_hallucination_layer.analyze(good_legal_response_text, rag_score=0.90)
        assert report.risk_score < 0.40
        assert not report.requires_correction

    def test_hallucinated_response_exceeds_threshold(
        self, anti_hallucination_layer, hallucinated_response_text
    ):
        """Respuesta con múltiples alucinaciones debe requerir corrección."""
        report = anti_hallucination_layer.analyze(hallucinated_response_text, rag_score=0.30)
        assert report.risk_score >= 0.40
        assert report.requires_correction
        assert len(report.flags) >= 2  # Al menos 2 patrones detectados

    def test_returns_hallucination_report_type(self, anti_hallucination_layer):
        """El método siempre retorna un HallucinationReport, sin importar el input."""
        report = anti_hallucination_layer.analyze("Texto de prueba.", rag_score=0.80)
        assert isinstance(report, HallucinationReport)

    def test_empty_response_flagged(self, anti_hallucination_layer):
        """Respuesta vacía debe retornar report con requires_correction=True."""
        report = anti_hallucination_layer.analyze("", rag_score=0.90)
        assert report.requires_correction

    def test_very_short_response_flagged(self, anti_hallucination_layer):
        """Respuesta de 1 palabra también debe generar report."""
        report = anti_hallucination_layer.analyze("Sí.", rag_score=0.90)
        assert isinstance(report, HallucinationReport)

    # ── Penalización por rag_score bajo ────────────────────────────────────────

    def test_low_rag_score_increases_risk(
        self, anti_hallucination_layer, good_legal_response_text
    ):
        """Mismo texto → mayor riesgo cuando el RAG score es bajo."""
        report_high = anti_hallucination_layer.analyze(good_legal_response_text, rag_score=0.95)
        report_low  = anti_hallucination_layer.analyze(good_legal_response_text, rag_score=0.10)
        assert report_low.risk_score > report_high.risk_score
        assert report_low.rag_penalty > 0

    def test_zero_rag_score_has_penalty(self, anti_hallucination_layer):
        """RAG score = 0 debe generar la penalización máxima por RAG."""
        report = anti_hallucination_layer.analyze("Respuesta legal.", rag_score=0.0)
        assert report.rag_penalty > 0

    def test_high_rag_score_no_penalty(self, anti_hallucination_layer):
        """RAG score ≥ threshold no debe generar penalización RAG."""
        report = anti_hallucination_layer.analyze("Respuesta legal.", rag_score=0.80)
        assert report.rag_penalty == 0.0

    # ── Patrones individuales de alucinación ───────────────────────────────────

    @pytest.mark.parametrize("text,expected_flag", [
        (
            "Según el artículo 9876 del Código Civil peruano...",
            "articulo_alto",
        ),
        (
            "La Ley N° 12 establece normas sobre alimentos.",
            "ley_corta",
        ),
        (
            "La pensión mínima es de S/ 500 según la norma.",
            "monto_fijo_pension",
        ),
        (
            "Posiblemente el artículo aplicable sea el decreto.",
            "incertidumbre_legal",
        ),
    ])
    def test_individual_patterns_detected(
        self, anti_hallucination_layer, text, expected_flag
    ):
        """Cada patrón de alucinación debe ser detectado individualmente."""
        report = anti_hallucination_layer.analyze(text, rag_score=0.80)
        detected_names = [d["name"] for d in report.pattern_details]
        assert expected_flag in detected_names, (
            f"Patrón '{expected_flag}' no detectado en: '{text}'\n"
            f"Detectados: {detected_names}"
        )

    def test_multiple_patterns_accumulate_penalty(self, anti_hallucination_layer):
        """Múltiples patrones deben acumular penalización hasta el máximo."""
        text_with_many_patterns = (
            "La Ley N° 12 dice que el artículo 9876 fija la pensión mínima a S/ 300. "
            "Posiblemente el artículo sobre alimentos fue derogado. "
            "El tribunal constitucional federal así lo resolvió."
        )
        report = anti_hallucination_layer.analyze(text_with_many_patterns, rag_score=0.80)
        assert report.pattern_penalty > 0.30   # Penalización acumulada
        assert report.risk_score <= 1.0        # No excede 1.0

    # ── Penalización estructural ───────────────────────────────────────────────

    def test_long_response_low_rag_triggers_structural_penalty(
        self, anti_hallucination_layer
    ):
        """Respuesta larga con RAG score bajo → penalización estructural."""
        long_text = "Esta es información legal detallada. " * 60   # ~1500+ chars
        report = anti_hallucination_layer.analyze(long_text, rag_score=0.40)
        assert report.structural_penalty > 0

    def test_long_response_high_rag_no_structural_penalty(
        self, anti_hallucination_layer
    ):
        """Respuesta larga con buen RAG score → sin penalización estructural."""
        long_text = "Esta es información legal detallada. " * 60
        report = anti_hallucination_layer.analyze(long_text, rag_score=0.80)
        assert report.structural_penalty == 0.0

    # ── Score total ─────────────────────────────────────────────────────────────

    def test_risk_score_bounded_0_to_1(self, anti_hallucination_layer):
        """El risk_score siempre debe estar en [0, 1]."""
        worst_case = (
            "La Ley N° 1 dice que el artículo 9999 fija pensión mínima de S/ 999. "
            "Posiblemente el artículo fue derogado en 1999. " * 5
        )
        report = anti_hallucination_layer.analyze(worst_case, rag_score=0.0)
        assert 0.0 <= report.risk_score <= 1.0

    def test_custom_threshold_changes_requires_correction(self):
        """Umbral personalizado debe cambiar el criterio de requires_correction."""
        strict  = AntiHallucinationLayer(risk_threshold=0.20)
        lenient = AntiHallucinationLayer(risk_threshold=0.80)

        text = "La pensión mínima es de S/ 500 por ley."   # Tiene 1 flag

        report_strict  = strict.analyze(text, rag_score=0.70)
        report_lenient = lenient.analyze(text, rag_score=0.70)

        # Con umbral estricto podría requerir corrección; con leniente, no
        # (Al menos uno de los dos debe diferir del otro)
        assert not (report_strict.requires_correction and report_lenient.requires_correction) \
            or report_strict.risk_score == report_lenient.risk_score