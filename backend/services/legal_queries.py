"""One retrieval → generation → validation → translation contract for every route."""

from copy import deepcopy
import logging

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from modules.language.services.language_detector import LanguageDetector
from modules.language.services.translation_service import TranslationService


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
    state, query, language, *, history=None, context=None, cache_key=None
):
    phase = getattr(state, "corpus_state", None)
    if phase in {"loading", "failed", "stopped"}:
        raise HTTPException(503, "Legal corpus unavailable")
    if phase == "degraded" and not getattr(state.rag_engine, "documents", {}):
        raise HTTPException(503, "Legal corpus unavailable")
    optimizer = state.llm_optimizer
    cached = optimizer.get_cached(cache_key) if cache_key else None
    if cached:
        return {
            "success": True,
            "query": query,
            "language": language,
            **deepcopy(cached),
            "cached": True,
        }

    processed_query = query
    translator = TranslationService()
    if LanguageDetector().detect_language(query) == "qu":
        translated = await translator.translate(query, "qu", "es")
        if not translated.get("success"):
            raise HTTPException(503, "Query translation unavailable; retry in Spanish")
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
        rag_result = await state.rag_engine.query_with_rerank(retrieval_query)
    except Exception as error:
        logging.getLogger("ia_juridica.pipeline").error(
            "retrieval_failed error_type=%s", type(error).__name__
        )
        raise HTTPException(503, "Legal retrieval unavailable") from None
    if rag_result.get("method") == "error":
        raise HTTPException(503, "Legal retrieval unavailable")
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
            raise HTTPException(502, "Legal response unavailable") from None
        data = response.model_dump() if hasattr(response, "model_dump") else response
    else:
        # Lack of evidence is an explicit abstention, not invented advice.
        data = {
            "respuesta_espanol": "No hay evidencia suficiente en el corpus para responder esta consulta. "
            "Solicita revisión profesional o incorpora una fuente verificable.",
            "fuentes_legales": [],
        }
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
        raise HTTPException(502, "Legal response unavailable")
    validation = validated.validation_report.model_dump()
    validation["is_reliable"] = bool(documents and validated.is_reliable)
    translation = None
    if language == "quechua":
        original = response_text(final)
        result = await translator.translate(original, "es", "qu")
        translation = {
            k: result.get(k)
            for k in ("success", "complete", "warning", "review_required")
        }
        translated_text = (
            result.get("translated_text", original)
            if result.get("success")
            else original
        )
        translated_text += (
            "\n\n[Aviso: "
            + result.get("warning", "Traducción no disponible; se conserva el español.")
            + "]"
        )
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
    return {
        "success": True,
        "query": query,
        "language": language,
        "cached": False,
        **payload,
    }
