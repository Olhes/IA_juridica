"""Estimación de calidad sin referencia y contrato `metadata.translation` (sin proveedores)."""

import pytest

from services import legal_queries
from services.legal_queries import answer_query
from services.translation_qe import (
    copy_rate,
    detect_language,
    estimate_quality,
    language_signals,
    length_ratio,
    protected_spans,
    references_preserved,
)

from .test_stream_pipeline import make_state

QUECHUA = "Imaynalla kachkanki, wiraqucha, kay wasipi llamk'asqaykimanta tapukuyki"
SPANISH = "La pensión de alimentos es un derecho que comprende la vivienda y la salud"


def test_language_heuristic_separates_quechua_spanish_and_short_text():
    assert detect_language(QUECHUA) == "qu" and detect_language(SPANISH) == "es"
    assert detect_language("Kay qillqa") == "unknown" and detect_language("") == "unknown"
    signals = language_signals(SPANISH)
    assert signals["spanish_ratio"] > 0.2 and signals["quechua_ratio"] < 0.35


def test_copy_rate_length_and_references():
    assert copy_rate("la pension de alimentos", "la pension de alimentos") == 1.0
    assert copy_rate("la pension de alimentos", "Qullqi chaskiy kamachiy") == 0.0
    assert length_ratio("abcd", "abcdefgh") == 2.0
    source = "Ley 30364 y artículo 8 [1]"
    assert protected_spans(source) == ["Ley 30364", "artículo 8", "[1]"]
    assert references_preserved(source, "Ley 30364, artículo 8 [1] kay") == (3, 3, [])
    assert references_preserved(source, "Ley 30364") == (1, 3, ["artículo 8", "[1]"])


def test_quality_is_high_only_when_every_automatic_check_passes():
    source = "El juez fijará una pensión de alimentos según el artículo 475 del Código Civil."
    good = "Kuskachaq alimentospaq qullqita churanqa, artículo 475 nisqanman hina, kamachikuypi."
    verdict = estimate_quality(source, good)
    assert verdict["quality"] == "alta" and verdict["reasons"] == []
    assert verdict["signals"]["references_kept"] == verdict["signals"]["references_total"] == 1
    assert "no sustituyen" in verdict["basis"]


@pytest.mark.parametrize(
    ("output", "success", "reason"),
    [
        ("El juez fijará una pensión de alimentos según el artículo 475 del Código Civil.", True, "parece español"),
        ("Kuskachaq alimentospaq qullqita churanqa kamachikuypi.", True, "referencias legales"),
        ("", False, "no disponible"),
        ("Kuskachaq " * 400, True, "longitud"),
    ],
)
def test_quality_is_low_for_untranslated_lost_references_failures_and_absurd_length(output, success, reason):
    source = "El juez fijará una pensión de alimentos según el artículo 475 del Código Civil."
    verdict = estimate_quality(source, output, success=success)
    assert verdict["quality"] == "baja" and any(reason in r for r in verdict["reasons"])


def test_quality_is_medium_when_the_language_cannot_be_confirmed():
    verdict = estimate_quality("Hay una pensión mensual para el hijo menor de edad", "Pension killa churi")
    assert verdict["quality"] == "media" and any("confirmar" in r for r in verdict["reasons"])


class FakeTranslator:
    def __init__(self, result):
        self.result = result

    async def translate(self, text, source, target):
        return self.result(text) if callable(self.result) else self.result


async def test_quechua_answer_keeps_the_notice_out_of_the_text_and_adds_quality(monkeypatch):
    spanish = "El juez fijará una pensión de alimentos según el artículo 475 del Código Civil."
    quechua = "Kuskachaq alimentospaq qullqita churanqa, artículo 475 nisqanman hina, kamachikuypi."
    monkeypatch.setattr(
        legal_queries, "TranslationService",
        lambda: FakeTranslator({"success": True, "complete": True, "translated_text": quechua,
                                "warning": "Traducción automática: requiere revisión lingüística y jurídica.", "review_required": True}),
    )
    state = make_state()
    state.response_validator.validate.return_value.answer_data = {"respuesta_espanol": spanish}
    result = await answer_query(state, "Consulta", "quechua")
    response, translation = result["response"], result["metadata"]["translation"]
    assert response["respuesta_quechua"] == quechua and response["respuesta_espanol"] == spanish
    assert "[Aviso" not in response["respuesta_quechua"] and "[Aviso" not in response["answer"]
    assert translation["quality"] == "alta" and translation["review_required"] is True
    assert translation["fallback_to_spanish"] is False and "revisión" in translation["warning"]
    assert translation["basis"] and translation["reasons"] == []


async def test_failed_translation_falls_back_to_spanish_without_a_pasted_notice(monkeypatch):
    spanish = "El juez fijará una pensión de alimentos."
    monkeypatch.setattr(legal_queries, "TranslationService", lambda: FakeTranslator({"success": False, "error": "Translation failed"}))
    state = make_state()
    state.response_validator.validate.return_value.answer_data = {"respuesta_espanol": spanish}
    result = await answer_query(state, "Consulta", "quechua")
    assert result["response"]["respuesta_quechua"] == spanish
    translation = result["metadata"]["translation"]
    assert translation["fallback_to_spanish"] is True and translation["quality"] == "baja"
    assert "conserva el español" in translation["warning"]
    state.llm_optimizer.cache_response.assert_not_called()
