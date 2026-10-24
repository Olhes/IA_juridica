"""One retrieval → generation → validation → translation contract for every route."""

from copy import deepcopy
import logging

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from modules.language.services.language_detector import LanguageDetector
from modules.language.services.translation_service import TranslationService
from services.citation_verifier import jurisprudence_keys, verify_citations
from services.pipeline_telemetry import PipelineTimer
from services.translation_qe import estimate_quality


class PipelineError(HTTPException):
    """HTTPException con un `code` estable que el stream NDJSON reenvía al cliente."""

    def __init__(self, status_code, detail, code):
        super().__init__(status_code, detail)
        self.code = code


EXCERPT_CHARS = 240


def _evidence(documents):
    """Fuentes recuperadas para citar: ``[{source, text}]`` (texto del corpus, no del modelo)."""
    return [
        {
            "source": (d.get("metadata") or {}).get("title")
            or (d.get("metadata") or {}).get("filename")
            or "Fuente desconocida",
            "text": d.get("content") or "",
        }
        for d in documents
    ]


def _evidence_summary(documents):
    return [
        {
            "source": item["source"],
            "relevance": d.get("relevance_score"),
            "excerpt": " ".join(item["text"].split())[:EXCERPT_CHARS],
            # Camino de recuperación: grafo de LightRAG o búsqueda léxica local.
            "origin": (d.get("metadata") or {}).get("retrieval_origin") or "lexical",
            "jurisprudence": jurisprudence_keys(item["text"]),
        }
        for item, d in zip(_evidence(documents), documents)
    ]


def response_text(data, language="spanish"):
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return ""
    names = (["respuesta_quechua", "quechua"] if language == "quechua" else []) + [
        "respuesta_espanol",
        "spanish",
        "answer",
        "respuesta",
    ]
    return next(
        (data[n] for n in names if isinstance(data.get(n), str) and data[n].strip()), ""
    )


async def answer_query(
    state,
    query,
    language,
    *,
    history=None,
    context=None,
    cache_key=None,
    on_stage=None,
):
    timer = PipelineTimer(on_stage)
    phase = getattr(state, "corpus_state", None)
    if phase in {"loading", "failed", "stopped"}:
        raise PipelineError(503, "Legal corpus unavailable", "RETRIEVAL_UNAVAILABLE")
    if phase == "degraded" and not getattr(state.rag_engine, "documents", {}):
        raise PipelineError(503, "Legal corpus unavailable", "RETRIEVAL_UNAVAILABLE")
    optimizer = state.llm_optimizer
    cached = optimizer.get_cached(cache_key) if cache_key else None
    if cached:
        timer.cache_hit = True
        result = {
            "success": True,
            "query": query,
            "language": language,
            **deepcopy(cached),
            "cached": True,
        }
        result["metadata"] = {**(result.get("metadata") or {}), "timings": timer.snapshot()}
        return result

    processed_query = query
    translator = TranslationService()
    if LanguageDetector().detect_language(query) == "qu":
        async with timer.stage("translate_in"):
            translated = await translator.translate(query, "qu", "es")
        if not translated.get("success"):
            raise PipelineError(
                503, "Query translation unavailable; retry in Spanish",
                "TRANSLATION_UNAVAILABLE",
            )
        processed_query = translated["translated_text"]
    retrieval_query = processed_query
    if history:
        prior_questions = "\n".join(
            m["content"] for m in history if m["role"] == "user"
        )
        retrieval_query += (
            "\nContexto de preguntas anteriores:\n" + prior_questions[-3000:]
        )
    try:
        async with timer.stage("retrieval"):
            rag_result = await state.rag_engine.query_with_rerank(retrieval_query)
    except Exception as error:
        logging.getLogger("ia_juridica.pipeline").error(
            "retrieval_failed error_type=%s", type(error).__name__
        )
        raise PipelineError(
            503, "Legal retrieval unavailable", "RETRIEVAL_UNAVAILABLE"
        ) from None
    if rag_result.get("method") == "error":
        raise PipelineError(503, "Legal retrieval unavailable", "RETRIEVAL_UNAVAILABLE")
    documents = rag_result.get("documents", [])
    enriched_prompt, enriched_context = state.context_engineer.build_legal_prompt(
        query=processed_query,
        documents=documents,
        language="spanish",
        history=history,
        context=context,
    )
    if documents:
        try:
            async with timer.stage("generation"):
                response = await state.legal_agent.respond_general(
                    query=processed_query,
                    context=rag_result,
                    language="spanish",
                    enriched_prompt=enriched_prompt,
                )
        except Exception as error:
            logging.getLogger("ia_juridica.pipeline").error(
                "generation_failed error_type=%s", type(error).__name__
            )
            raise PipelineError(
                502, "Legal response unavailable", "GENERATION_UNAVAILABLE"
            ) from None
        data = response.model_dump() if hasattr(response, "model_dump") else response
    else:
        # Lack of evidence is an explicit abstention, not invented advice.
        data = {
            "respuesta_espanol": "No hay evidencia suficiente en el corpus para responder esta consulta. "
            "Solicita revisión profesional o incorpora una fuente verificable.",
            "fuentes_legales": [],
        }
    async with timer.stage("validation"):
        validated = await state.response_validator.validate(
            response_data=data,
            rag_result=rag_result,
            query=processed_query,
            language="spanish",
            enriched_context=enriched_context,
        )
    final = jsonable_encoder(validated.answer_data)
    if not documents:
        final = data  # Self-correction must not manufacture advice without evidence.
    if not response_text(final).strip():
        raise PipelineError(502, "Legal response unavailable", "GENERATION_UNAVAILABLE")
    validation = validated.validation_report.model_dump()
    validation["is_reliable"] = bool(documents and validated.is_reliable)
    translation = None
    if language == "quechua":
        original = response_text(final)
        async with timer.stage("translate_out"):
            result = await translator.translate(original, "es", "qu")
        translated = bool(result.get("success"))
        translated_text = result.get("translated_text", original) if translated else original
        # El aviso vive solo en `metadata.translation`; el texto no lleva avisos pegados.
        translation = {
            "success": result.get("success"),
            "complete": result.get("complete"),
            "warning": result.get("warning")
            or "Traducción no disponible; se conserva el español.",
            "review_required": result.get("review_required", True),
            "fallback_to_spanish": not translated,
            **{
                key: value
                for key, value in estimate_quality(original, translated_text, success=translated).items()
                if key in {"quality", "reasons", "basis"}
            },
        }
        if isinstance(final, dict):
            final["respuesta_quechua"] = translated_text
            final["answer"] = translated_text
        else:
            final = translated_text
    optimizer.track(enriched_prompt or query, response_text(final, language))
    payload = {
        "response": final,
        "sources": validated.sources if documents else [],
        "validation": validation,
        "metadata": {
            "translation": translation,
            "pipeline": "validated-before-delivery-v1",
            "evidence_status": "retrieved" if documents else "insufficient_evidence",
            "retrieval_method": rag_result.get("method", "unknown"),
            "citations": verify_citations(response_text(final), _evidence(documents)) if documents else [],
            "evidence": _evidence_summary(documents),
            "total_candidates": rag_result.get("total_candidates", 0),
            "optimizer_stats": optimizer.get_session_stats(),
        },
    }
    if (
        validation["is_reliable"]
        and cache_key
        and (translation is None or translation.get("success"))
    ):
        optimizer.cache_response(cache_key, deepcopy(payload))
    payload["metadata"]["timings"] = timer.snapshot()
    return {
        "success": True,
        "query": query,
        "language": language,
        "cached": False,
        **payload,
    }
