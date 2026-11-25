"""One retrieval → generation → validation → translation contract for every route."""

from copy import deepcopy
import asyncio
import logging

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from modules.language.services.language_detector import LanguageDetector
from modules.language.services.translation_service import TranslationService
from retrieval.sat_chat import SATChatRetriever
from services.citation_verifier import evidence_matches, evidence_keys, jurisprudence_keys, verify_citations
from services.pipeline_telemetry import PipelineTimer
from services.translation_qe import estimate_quality


class PipelineError(HTTPException):
    """HTTPException con un `code` estable que el stream NDJSON reenvía al cliente."""

    def __init__(self, status_code, detail, code):
        super().__init__(status_code, detail)
        self.code = code


EXCERPT_CHARS = 240


def _public_validation(report):
    """El solapamiento es diagnóstico, no una verificación semántica ni probabilidad."""
    result = dict(report or {})
    for key in ("is_grounded", "is_reliable", "confidence", "confidence_score", "hallucination_risk"):
        result[key] = None
    result["semantic_verification"] = "not_performed"
    # Las entradas previas en caché aún pueden contener la antigua etiqueta.
    if isinstance(result.get("warnings"), list):
        result["warnings"] = [
            "El índice heurístico interno no alcanzó el umbral de revisión; "
            "no mide la probabilidad de que la respuesta sea correcta."
            if isinstance(warning, str) and warning.startswith("Confianza insuficiente:")
            else warning
            for warning in result["warnings"]
        ]
    if isinstance(result.get("cross_check"), dict):
        result["cross_check"] = {**result["cross_check"], "is_grounded": None}
    return result


def _evidence(documents):
    """Fuentes recuperadas para citar: ``[{source, text}]`` (texto del corpus, no del modelo)."""
    return [
        {
            "source": (d.get("metadata") or {}).get("citation")
            or (d.get("metadata") or {}).get("title")
            or (d.get("metadata") or {}).get("filename")
            or "Fuente desconocida",
            "text": d.get("content") or "",
            "citation": (d.get("metadata") or {}).get("citation"),
        }
        for d in documents
    ]


def _evidence_summary(documents):
    """Un item por fragmento recuperado, con la estructura que el corpus conozca.

    ``section`` y ``version_id`` permiten agrupar la evidencia como árbol
    norma → artículos sin reconstruir la jerarquía en el cliente.
    """
    summary = []
    for item, document in zip(_evidence(documents), documents):
        metadata = document.get("metadata") or {}
        section = metadata.get("sat_section") or {}
        summary.append(
            {
                "source": item["source"],
                # Nombre del documento recuperado (norma): agrupa el árbol aunque
                # `source` sea la cita exacta ("Artículo 3 de la Ley 28970").
                "document": metadata.get("title") or metadata.get("filename") or item["source"],
                "relevance": document.get("relevance_score"),
                "excerpt": " ".join(item["text"].split())[:EXCERPT_CHARS],
                # Camino de recuperación: grafo de LightRAG o búsqueda léxica local.
                "origin": metadata.get("retrieval_origin") or "lexical",
                "jurisprudence": jurisprudence_keys(item["text"]),
                "section": section.get("title") or metadata.get("section_label"),
                "version_id": metadata.get("version_id"),
                "source_url": metadata.get("source_url"),
            }
        )
    return summary


def _response_citations(answer, documents):
    checks = verify_citations(answer, _evidence(documents))
    sections = {}
    for document in documents:
        metadata = document.get("metadata") or {}
        section = metadata.get("sat_section")
        if metadata.get("retrieval_origin") != "sat" or not section or not document.get("content"):
            continue
        key = f"sat-section:{section['version_id']}"
        sections[key] = {
            "key": key, "text": section["title"], "status": "verified",
            "source": metadata.get("title"), "excerpt": None,
            "sat_section": {**section, "text": document["content"].strip()},
        }
    if not sections:
        return checks
    covered = set().union(*(evidence_keys(item["text"]) for item in sections.values()))
    # Collapse only references to the same structural citation, not citations
    # to other provisions that happen to be mentioned inside the recovered text.
    remaining = [
        check for check in checks
        if not any(evidence_matches(check["key"], key) for key in covered)
    ]
    return [*sections.values(), *remaining]


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


async def _ensure_corpus_ready(state) -> None:
    phase = getattr(state, "corpus_state", None)
    if phase == "degraded":
        # El corpus SAT puede publicarse sin reiniciar: se reevalúa solo mientras
        # está degradado y deja de consultar en cuanto hay una revisión publicada.
        probe = getattr(getattr(state, "query_retriever", None), "corpus_ready", None)
        if callable(probe) and await asyncio.to_thread(probe):
            state.corpus_state = phase = "ready"
    if phase in {"loading", "failed", "stopped"}:
        raise PipelineError(503, "Legal corpus unavailable", "RETRIEVAL_UNAVAILABLE")
    if phase == "degraded" and not getattr(state.rag_engine, "documents", {}):
        raise PipelineError(503, "Legal corpus unavailable", "RETRIEVAL_UNAVAILABLE")


async def _translate_query_in(query: str, timer: PipelineTimer) -> str:
    if LanguageDetector().detect_language(query) != "qu":
        return query
    async with timer.stage("translate_in"):
        translated = await TranslationService().translate(query, "qu", "es")
    if not translated.get("success"):
        raise PipelineError(
            503,
            "Query translation unavailable; retry in Spanish",
            "TRANSLATION_UNAVAILABLE",
        )
    return translated["translated_text"]


async def _run_retrieval(state, processed_query: str, prior_questions: list[str], timer: PipelineTimer):
    retrieval_query = processed_query
    if prior_questions:
        retrieval_query += (
            "\nContexto de preguntas anteriores:\n" + "\n".join(prior_questions)[-3000:]
        )
    try:
        async with timer.stage("retrieval"):
            retriever = getattr(state, "query_retriever", None) or state.rag_engine
            if isinstance(retriever, SATChatRetriever):
                rag_result = await retriever.query_with_rerank(
                    processed_query, prior_questions=prior_questions
                )
            else:
                rag_result = await retriever.query_with_rerank(retrieval_query)
    except Exception as error:
        logging.getLogger("ia_juridica.pipeline").error(
            "retrieval_failed error_type=%s", type(error).__name__
        )
        raise PipelineError(
            503, "Legal retrieval unavailable", "RETRIEVAL_UNAVAILABLE"
        ) from None
    if rag_result.get("method") == "error":
        raise PipelineError(503, "Legal retrieval unavailable", "RETRIEVAL_UNAVAILABLE")
    return rag_result


def _apply_sat_prompt_guides(enriched_prompt, rag_result, documents, reference):
    if reference and documents:
        enriched_prompt = f"{enriched_prompt or ''}\n\nReferencia exacta recuperada: {reference['citation']}"
    verbatim = rag_result.get("verbatim_answer") if documents and reference else None
    if verbatim:
        guide = verbatim.replace("<!-- image -->", "")
        body = guide.partition("\n\n")[2]
        evidence = (rag_result.get("answer") or "").replace("<!-- image -->", "")
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if not lines or not all(line in evidence for line in lines):
            enriched_prompt = f"{enriched_prompt or ''}\n\n{guide}"
    return (enriched_prompt or "").replace("<!-- image -->", "") if documents else enriched_prompt


async def _generate_answer(
    state,
    processed_query: str,
    language: str,
    rag_result: dict,
    documents: list,
    reference,
    enriched_prompt,
    timer: PipelineTimer,
    on_delta,
):
    if not documents:
        # Lack of evidence is an explicit abstention, not invented advice.
        return {
            "respuesta_espanol": (
                rag_result["sat_warning"]
                if reference
                else "No hay evidencia suficiente en el corpus para responder esta consulta. "
                "Solicita revisión profesional o incorpora una fuente verificable."
            ),
            "fuentes_legales": [],
        }

    generation_context = {
        **rag_result,
        "answer": (rag_result.get("answer") or "").replace("<!-- image -->", ""),
    }
    try:
        async with timer.stage("generation"):
            options = dict(
                query=processed_query,
                context=generation_context,
                language="spanish",
                enriched_prompt=enriched_prompt,
            )
            if on_delta is not None and language == "spanish":
                parts = []
                async for delta in state.legal_agent.stream_general_text(**options):
                    parts.append(delta)
                    await on_delta(delta)
                response = state.legal_agent.build_general_response_from_text(
                    "".join(parts), processed_query
                )
            else:
                response = await state.legal_agent.respond_general(**options)
    except Exception as error:
        logging.getLogger("ia_juridica.pipeline").error(
            "generation_failed error_type=%s", type(error).__name__
        )
        raise PipelineError(
            502, "Legal response unavailable", "GENERATION_UNAVAILABLE"
        ) from None
    return response.model_dump() if hasattr(response, "model_dump") else response


async def _translate_answer_out(final, language: str, timer: PipelineTimer):
    if language != "quechua":
        return final, None
    original = response_text(final)
    async with timer.stage("translate_out"):
        result = await TranslationService().translate(original, "es", "qu")
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
            for key, value in estimate_quality(
                original, translated_text, success=translated
            ).items()
            if key in {"quality", "reasons", "basis"}
        },
    }
    if isinstance(final, dict):
        final["respuesta_quechua"] = translated_text
        final["answer"] = translated_text
    else:
        final = translated_text
    return final, translation


async def answer_query(
    state,
    query,
    language,
    *,
    history=None,
    context=None,
    cache_key=None,
    on_stage=None,
    on_delta=None,
):
    timer = PipelineTimer(on_stage)
    await _ensure_corpus_ready(state)

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
        result["metadata"] = {
            **(result.get("metadata") or {}),
            "timings": timer.snapshot(),
        }
        result["validation"] = _public_validation(result.get("validation"))
        return result

    processed_query = await _translate_query_in(query, timer)
    prior_questions = [m["content"] for m in (history or []) if m["role"] == "user"]
    rag_result = await _run_retrieval(state, processed_query, prior_questions, timer)

    documents = rag_result.get("documents", [])
    reference = (
        rag_result.get("sat_reference") if rag_result.get("method") == "sat" else None
    )
    enriched_prompt, enriched_context = state.context_engineer.build_legal_prompt(
        query=processed_query,
        documents=documents,
        history=history,
        context=context,
        include_documents=False,
    )
    enriched_prompt = _apply_sat_prompt_guides(
        enriched_prompt, rag_result, documents, reference
    )
    data = await _generate_answer(
        state,
        processed_query,
        language,
        rag_result,
        documents,
        reference,
        enriched_prompt,
        timer,
        on_delta,
    )

    async with timer.stage("validation"):
        validated = await state.response_validator.validate(
            response_data=data,
            rag_result=rag_result,
            query=processed_query,
            language="spanish",
            enriched_context=enriched_context,
        )
    final = jsonable_encoder(validated.answer_data) if documents else data
    if not response_text(final).strip():
        raise PipelineError(502, "Legal response unavailable", "GENERATION_UNAVAILABLE")

    cacheable = bool(documents and validated.is_reliable)
    validation = _public_validation(validated.validation_report.model_dump())
    if rag_result.get("method") == "sat" and rag_result.get("sat_warning"):
        validation.setdefault("warnings", []).append(rag_result["sat_warning"])

    final, translation = await _translate_answer_out(final, language, timer)
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
            **(
                {
                    "sat_warning": rag_result.get("sat_warning"),
                    "sat_as_of": rag_result.get("sat_as_of"),
                    "sat_reference": reference,
                }
                if rag_result.get("method") == "sat"
                else {}
            ),
            "citations": (
                _response_citations(response_text(final), documents) if documents else []
            ),
            "evidence": _evidence_summary(documents),
            "total_candidates": rag_result.get("total_candidates", 0),
            "optimizer_stats": optimizer.get_session_stats(),
        },
    }
    if cacheable and cache_key and (translation is None or translation.get("success")):
        optimizer.cache_response(cache_key, deepcopy(payload))
    payload["metadata"]["timings"] = timer.snapshot()
    return {
        "success": True,
        "query": query,
        "language": language,
        "cached": False,
        **payload,
    }
