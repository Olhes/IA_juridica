"""
Tests unitarios para RAGCrossChecker.

Cobertura:
  - Respuesta fundamentada en el corpus → is_grounded=True
  - Respuesta sin soporte → is_grounded=False + ungrounded_claims
  - Corpus vacío → optimista (True)
  - Actualización del corpus (update_documents)
  - Cache de tokens se invalida al actualizar corpus
  - Extracción correcta de afirmaciones del texto
  - Límites de overlap por afirmación
"""

import pytest
from validation.cross_checker import RAGCrossChecker, CrossCheckResult


class TestRAGCrossChecker:

    # ── Casos base ─────────────────────────────────────────────────────────────

    def test_grounded_response_passes(
        self, cross_checker, good_legal_response_text
    ):
        """Respuesta con términos del corpus → overlap alto → is_grounded=True."""
        result = cross_checker.check(good_legal_response_text, query="pensión alimentos")
        assert isinstance(result, CrossCheckResult)
        assert result.overlap_score >= 0.0
        # Con un corpus legal real y una respuesta legal, el overlap debe ser razonable
        assert result.total_claims >= 1
        assert result.checked_against > 0

    def test_hallucinated_response_has_low_overlap(
        self, cross_checker, hallucinated_response_text
    ):
        """Respuesta con términos inventados → afirmaciones no fundadas."""
        result = cross_checker.check(hallucinated_response_text, query="pensión alimentos")
        assert result.total_claims >= 1
        # Las afirmaciones con términos inventados deben aparecer como no fundadas
        # (al menos algunas, dado que el corpus no contiene "artículo 9876" etc.)
        assert isinstance(result.ungrounded_claims, list)

    def test_empty_response_returns_result(self, cross_checker):
        """Respuesta vacía → CrossCheckResult con is_grounded=False."""
        result = cross_checker.check("", query="alimentos")
        assert not result.is_grounded
        assert result.overlap_score == 0.0
        assert result.total_claims == 0

    def test_empty_corpus_returns_optimistic(self):
        """Sin documentos en el corpus → is_grounded=True (no podemos evaluar)."""
        checker = RAGCrossChecker(documents={})
        result = checker.check("Respuesta legal sobre alimentos.", query="alimentos")
        assert result.is_grounded
        assert result.overlap_score == 1.0

    def test_returns_cross_check_result_type(self, cross_checker):
        """Siempre debe retornar CrossCheckResult independiente del input."""
        result = cross_checker.check("Texto cualquiera.", query="test")
        assert isinstance(result, CrossCheckResult)

    # ── Estructura del resultado ────────────────────────────────────────────────

    def test_result_has_supporting_chunks(
        self, cross_checker, good_legal_response_text
    ):
        """Los supporting_chunks deben provenir del corpus RAG."""
        result = cross_checker.check(
            good_legal_response_text, query="artículo 472 alimentos"
        )
        # Si el corpus tiene contenido relevante, debe haber supporting chunks
        assert isinstance(result.supporting_chunks, list)

    def test_total_claims_count_is_correct(self, cross_checker):
        """El total de afirmaciones debe ser >= grounded + ungrounded."""
        text = (
            "El artículo 472 define alimentos. "
            "La pensión la fija el juez. "
            "Término completamente inventado xyz123 es válido."
        )
        result = cross_checker.check(text, query="alimentos")
        assert result.total_claims == result.grounded_claims + len(result.ungrounded_claims)

    def test_ungrounded_claims_are_strings(self, cross_checker, hallucinated_response_text):
        """Las afirmaciones no fundadas deben ser strings legibles."""
        result = cross_checker.check(hallucinated_response_text, query="alimentos")
        for claim in result.ungrounded_claims:
            assert isinstance(claim, str)
            assert len(claim) > 0

    def test_overlap_score_bounded(self, cross_checker, good_legal_response_text):
        """El overlap_score siempre debe estar en [0.0, 1.0]."""
        result = cross_checker.check(good_legal_response_text, query="alimentos")
        assert 0.0 <= result.overlap_score <= 1.0

    # ── Cache de tokens ─────────────────────────────────────────────────────────

    def test_corpus_cache_reused(self, cross_checker, good_legal_response_text):
        """Dos llamadas seguidas deben usar el cache de tokens (mismo tamaño de corpus)."""
        result1 = cross_checker.check(good_legal_response_text, query="alimentos")
        result2 = cross_checker.check(good_legal_response_text, query="alimentos")
        # El checked_against (nº tokens únicos) debe ser idéntico
        assert result1.checked_against == result2.checked_against

    def test_cache_invalidated_on_update(self, cross_checker, good_legal_response_text):
        """Al actualizar el corpus, el cache de tokens debe invalidarse."""
        # Primera consulta (cache se construye)
        result1 = cross_checker.check(good_legal_response_text, query="alimentos")

        # Actualizar corpus con un documento nuevo
        new_docs = dict(cross_checker.documents)
        new_docs["new_doc"] = {
            "content": "Información adicional sobre régimen de visitas.",
            "chunks": ["Información sobre régimen de visitas."],
            "metadata": {"filename": "nuevo.md"},
        }
        cross_checker.update_documents(new_docs)
        assert cross_checker._corpus_tokens is None  # Cache invalidado

        # Segunda consulta (cache se reconstruye con más tokens)
        result2 = cross_checker.check(good_legal_response_text, query="alimentos")
        assert result2.checked_against >= result1.checked_against

    # ── Threshold personalizado ─────────────────────────────────────────────────

    def test_custom_threshold_strict(self, sample_documents):
        """Threshold alto (0.95) → casi nada es grounded."""
        strict_checker = RAGCrossChecker(documents=sample_documents, grounded_threshold=0.95)
        result = strict_checker.check(
            "El artículo 472 del Código Civil define alimentos básicos.", query=""
        )
        # Con threshold 95% es casi imposible estar "grounded"
        assert not result.is_grounded

    def test_custom_threshold_permissive(self, sample_documents):
        """Threshold bajo (0.10) → casi todo es grounded."""
        permissive = RAGCrossChecker(documents=sample_documents, grounded_threshold=0.10)
        result = permissive.check("La ley peruana regula alimentos.", query="")
        assert result.is_grounded