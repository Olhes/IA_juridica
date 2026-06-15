"""
Fixtures globales para el testing framework de IA Jurídica.

Arquitectura de fixtures:
  - Mocks de Cohere (sin costo API real en tests unitarios)
  - Corpus RAG de ejemplo con documentos legales reales simplificados
  - Instancias pre-configuradas de cada capa de validación
  - Respuestas de prueba: buenas (grounded) y malas (hallucinated)

Convención:
  - Fixtures con scope="session"  → caro de crear, compartido en toda la sesión
  - Fixtures con scope="function" → default, aislado por test
"""

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Módulos del proyecto ───────────────────────────────────────────────────────
from modules.validation.services.anti_hallucination import AntiHallucinationLayer
from modules.validation.services.cross_checker import RAGCrossChecker
from modules.validation.services.self_correction import SelfCorrectionEngine
from modules.validation.services.response_validator import ResponseValidator, ValidationConfig
from optimization.llm_optimizer import LLMOptimizer


# ── Event loop (compatibilidad pytest-asyncio) ─────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CORPUS RAG DE PRUEBA
# Documentos legales peruanos simplificados que replican la estructura
# real del sistema (dict `rag_engine.documents`)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def sample_documents() -> Dict[str, Any]:
    """
    Corpus RAG de prueba con documentos legales peruanos.
    Replica exactamente la estructura de LegalRAGEngine.documents.
    """
    return {
        "pension_alimentos_guia": {
            "content": (
                "El artículo 472 del Código Civil peruano define alimentos como "
                "lo indispensable para el sustento, habitación, vestido, educación, "
                "instrucción, capacitación para el trabajo, asistencia médica y psicológica "
                "y recreación según la situación y posibilidades de la familia. "
                "La pensión de alimentos se fija en proporción a las necesidades del "
                "alimentista y a las posibilidades del obligado. "
                "El artículo 481 establece que los alimentos se regulan por el juez "
                "en proporción a las necesidades de quien los pide y a las posibilidades "
                "del que debe darlos."
            ),
            "metadata": {
                "filename": "Pensión_de_Alimentos_Guía_Integral.md",
                "title": "Guía Integral de Pensión de Alimentos",
                "document_type": "normativa_simplificada",
                "source": "disk_reload",
            },
            "chunks": [
                "El artículo 472 del Código Civil define alimentos como lo indispensable para el sustento.",
                "La pensión se fija en proporción a las necesidades del alimentista y posibilidades del obligado.",
                "El artículo 481 establece que los alimentos los regula el juez.",
            ],
        },
        "violencia_familiar_ley30364": {
            "content": (
                "La Ley 30364, Ley para Prevenir, Sancionar y Erradicar la Violencia "
                "contra las Mujeres y los Integrantes del Grupo Familiar, define la "
                "violencia familiar como cualquier acción o conducta que cause muerte, "
                "daño o sufrimiento físico, sexual o psicológico. "
                "Las víctimas pueden denunciar en la comisaría, fiscalía o juzgado de familia. "
                "El Centro de Emergencia Mujer (CEM) brinda atención gratuita y especializada."
            ),
            "metadata": {
                "filename": "violencia.md",
                "title": "Ley 30364 - Violencia Familiar",
                "document_type": "normativa_simplificada",
                "source": "disk_reload",
            },
            "chunks": [
                "La Ley 30364 define violencia familiar como acción que causa daño físico, sexual o psicológico.",
                "Las víctimas pueden denunciar en comisaría, fiscalía o juzgado de familia.",
                "El CEM brinda atención gratuita especializada a víctimas de violencia.",
            ],
        },
        "regimen_visitas_guia": {
            "content": (
                "El régimen de visitas es el derecho que tiene el progenitor que no tiene "
                "la tenencia del menor a mantener contacto con sus hijos. "
                "Se solicita ante el Juzgado de Familia presentando DNI y partida de nacimiento. "
                "Existe régimen de visitas con y sin pernocte. "
                "En caso de incumplimiento, se puede solicitar variación del régimen."
            ),
            "metadata": {
                "filename": "visitas.md",
                "title": "Régimen de Visitas - Guía",
                "document_type": "guia_paso_a_paso",
                "source": "disk_reload",
            },
            "chunks": [
                "El régimen de visitas permite al progenitor sin tenencia mantener contacto con sus hijos.",
                "Se solicita ante el Juzgado de Familia con DNI y partida de nacimiento.",
            ],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MOCKS DE SERVICIOS EXTERNOS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_cohere_client():
    """Mock de cohere.AsyncClient para evitar llamadas reales a la API."""
    client = AsyncMock()
    # Respuesta corregida por defecto
    mock_response = MagicMock()
    mock_response.text = (
        "Según el artículo 472 del Código Civil, los alimentos comprenden lo indispensable "
        "para el sustento del menor. La pensión se determina según las necesidades del "
        "alimentista y las posibilidades del obligado, conforme al artículo 481."
    )
    client.chat.return_value = mock_response
    return client


@pytest.fixture
def mock_rag_engine(sample_documents):
    """Mock de LegalRAGEngine con corpus real de prueba."""
    engine = MagicMock()
    engine.documents = sample_documents
    engine.cohere_client = AsyncMock()

    # query_with_rerank retorna estructura real del sistema
    engine.query_with_rerank = AsyncMock(return_value={
        "answer": "Información sobre pensión de alimentos según el Código Civil.",
        "documents": [
            {
                "content": "El artículo 472 del Código Civil define alimentos como lo indispensable.",
                "metadata": {"filename": "pension.md"},
                "id": "pension_chunk_0",
            },
            {
                "content": "La pensión se fija en proporción a las necesidades y posibilidades.",
                "metadata": {"filename": "pension.md"},
                "id": "pension_chunk_1",
            },
        ],
        "rerank_scores": [0.92, 0.85],
        "sources": ["Pensión_de_Alimentos_Guía_Integral.md"],
        "method": "cohere_rerank",
        "total_candidates": 10,
    })
    return engine


@pytest.fixture
def mock_context_engineer():
    """Mock de ContextEngineer para validación cultural."""
    engineer = MagicMock()
    engineer.validate_response_cultural_appropriateness.return_value = {
        "is_appropriate": True,
        "issues": [],
        "recommendations": [],
        "cultural_score": 0.9,
    }
    return engineer


# ═══════════════════════════════════════════════════════════════════════════════
# RESPUESTAS DE PRUEBA (FIXTURES DE DATOS)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def good_legal_response_text() -> str:
    """
    Respuesta correctamente fundamentada en el corpus RAG.
    No debería generar flags de alucinación.
    """
    return (
        "Según el artículo 472 del Código Civil peruano, los alimentos comprenden "
        "lo indispensable para el sustento, habitación, vestido, educación e instrucción. "
        "La pensión de alimentos se fija en proporción a las necesidades del alimentista "
        "y a las posibilidades del obligado, conforme al artículo 481 del mismo código. "
        "Para iniciar el proceso, debe presentar su DNI y la partida de nacimiento del menor "
        "ante el Juzgado de Familia. El CEM puede brindarle asesoría gratuita."
    )


@pytest.fixture
def hallucinated_response_text() -> str:
    """
    Respuesta con múltiples señales de alucinación:
    - Artículo 9876 inexistente
    - Ley N° 12 (número demasiado corto)
    - Monto fijo de pensión
    - Incertidumbre al citar norma
    """
    return (
        "Según el artículo 9876 del Código Civil, la pensión mínima es de S/ 500. "
        "La Ley N° 12 establece normas sobre alimentos que posiblemente el artículo "
        "sobre alimentos fue derogado en 2021. "
        "Casación 1234-25 de la Sala señala que el juez puede fijar pensiones retroactivas. "
        "La pensión máxima es de S/ 2000 según la norma vigente."
    )


@pytest.fixture
def good_response_data() -> Dict[str, Any]:
    """GeneralLegalResponse serializado de respuesta válida."""
    return {
        "tema": "pension_alimentos",
        "respuesta_espanol": (
            "Según el artículo 472 del Código Civil, los alimentos son lo indispensable "
            "para el sustento. La pensión la fija el juez según necesidades y posibilidades."
        ),
        "respuesta_quechua": "(Traducción quechua no disponible)",
        "pasos_recomendados": [
            {"paso": 1, "descripcion": "Reunir DNI y partida de nacimiento", "documentos_requeridos": ["DNI"]}
        ],
        "recursos": [{"nombre": "CEM", "tipo": "Centro de Emergencia Mujer", "descripcion": "Asesoría gratuita"}],
        "advertencias": [],
        "fuentes": [{"nombre": "Código Civil", "tipo": "Código", "numero": "Artículo 472"}],
        "confianza": 0.85,
    }


@pytest.fixture
def hallucinated_response_data() -> Dict[str, Any]:
    """GeneralLegalResponse serializado con alucinaciones."""
    return {
        "tema": "pension_alimentos",
        "respuesta_espanol": (
            "La Ley N° 12 establece que la pensión mínima es de S/ 500. "
            "El artículo 9876 del Código Civil fue derogado en 2021. "
            "Posiblemente el artículo aplicable sea el decreto supremo."
        ),
        "respuesta_quechua": "(Traducción quechua no disponible)",
        "pasos_recomendados": [],
        "recursos": [],
        "advertencias": [],
        "fuentes": [],
        "confianza": 0.4,
    }


@pytest.fixture
def sample_rag_result() -> Dict[str, Any]:
    """Resultado típico de rag_engine.query_with_rerank()."""
    return {
        "answer": "Basado en los documentos: información sobre pensión de alimentos.",
        "documents": [
            {
                "content": "El artículo 472 del Código Civil define alimentos.",
                "metadata": {"filename": "pension.md"},
                "id": "pension_chunk_0",
            }
        ],
        "rerank_scores": [0.88],
        "sources": ["pension.md"],
        "method": "cohere_rerank",
        "total_candidates": 8,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# INSTANCIAS DE MÓDULOS DE VALIDACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def anti_hallucination_layer() -> AntiHallucinationLayer:
    return AntiHallucinationLayer(risk_threshold=0.40)


@pytest.fixture
def cross_checker(sample_documents) -> RAGCrossChecker:
    return RAGCrossChecker(documents=sample_documents, grounded_threshold=0.55)


@pytest.fixture
def self_correction_engine(mock_cohere_client) -> SelfCorrectionEngine:
    return SelfCorrectionEngine(cohere_client=mock_cohere_client, max_retries=2)


@pytest.fixture
def llm_optimizer() -> LLMOptimizer:
    return LLMOptimizer(cache_ttl_seconds=60, max_cache_size=100)


@pytest.fixture
def validation_config() -> ValidationConfig:
    return ValidationConfig(
        hallucination_threshold    =0.40,
        cross_check_threshold      =0.55,
        min_confidence_score       =0.30,
        max_self_correction_retries=1,   # Reducir en tests para velocidad
        enable_cross_check         =True,
        enable_self_correction     =True,
        enable_cultural_validation =False,  # Desactivar en unit tests
    )


@pytest.fixture
def response_validator(
    mock_rag_engine,
    mock_cohere_client,
    mock_context_engineer,
    validation_config,
) -> ResponseValidator:
    return ResponseValidator(
        rag_engine      =mock_rag_engine,
        cohere_client   =mock_cohere_client,
        context_engineer=mock_context_engineer,
        config          =validation_config,
    )