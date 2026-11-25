"""Legal query, NDJSON streaming, PDF report, and TTS endpoints."""

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from config.settings import settings
from context.conversation_prompt import bounded_history, with_conversation
from database.errors import DatabaseUnavailableError
from models.request_types import NonBlankMessage, RequestContext, SupportedLanguage
from modules.voice.services.tts_service import TTSService
from optimization.query_cache import answer_cache_key
from security import Principal, limiter, require_principal
from services.legal_queries import answer_query
from services.legal_stream import stream_legal_query
from services.stream_guard import guard_stream

router = APIRouter(tags=["queries"])
logger = logging.getLogger("ia_juridica.api")


class LegalQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: NonBlankMessage
    language: SupportedLanguage = "spanish"
    context: Optional[RequestContext] = None
    conversation_id: Optional[str] = None


class PDFReportRequest(BaseModel):
    query: str = Field(..., min_length=1)
    response: Dict[str, Any]


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=5000)
    language: SupportedLanguage = "spanish"


def _ndjson_event(payload: Dict[str, Any]) -> str:
    """Serializa eventos NDJSON manejando datetime/enums/modelos pydantic."""
    return json.dumps(jsonable_encoder(payload), ensure_ascii=False) + "\n"


def _extract_response_text(response_payload: Any, language: str) -> str:
    if not isinstance(response_payload, dict):
        return str(response_payload or "")
    field_order = (
        ("respuesta_quechua", "quechua", "respuesta_espanol", "spanish", "answer")
        if language == "quechua"
        else ("respuesta_espanol", "spanish", "answer", "respuesta_quechua", "quechua")
    )
    for field in field_order:
        value = response_payload.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return ""


async def _prepare_query_context(payload, owner_id, mode):
    import main as runtime

    history = []
    if payload.conversation_id:
        if not await runtime.chat_service.get_conversation(
            payload.conversation_id, owner_id
        ):
            raise HTTPException(404, "Conversation not found")
        messages = await runtime.chat_service.get_conversation_messages(
            payload.conversation_id, owner_id, limit=12
        )
        history = bounded_history(messages)
    try:
        with_conversation("", history, payload.context)
    except ValueError:
        raise HTTPException(422, "Conversation context exceeds the prompt budget")
    engine = getattr(runtime.app.state, "query_retriever", None) or getattr(
        runtime.app.state, "rag_engine", None
    )
    revision_fn = getattr(engine, "get_cache_revision", None)
    revision = revision_fn() if callable(revision_fn) else None
    key = None
    if isinstance(revision, str) and revision:
        key = answer_cache_key(
            payload.query,
            payload.language,
            owner_id,
            payload.context,
            history,
            payload.conversation_id,
            revision,
            mode,
        )
    return key, history


async def _persist_assistant_response(
    conversation_id: Optional[str],
    owner_id: str,
    response_payload: Any,
    language: str,
    metadata: Dict[str, Any],
) -> None:
    import main as runtime

    if not conversation_id:
        return
    content = runtime._extract_response_text(response_payload, language)
    if not content:
        logger.warning("Skipping empty assistant response persistence")
        return
    try:
        from models.chat_models import MessageCreate, MessageRole

        await runtime.chat_service.add_message(
            conversation_id=conversation_id,
            user_id=owner_id,
            message_data=MessageCreate(
                content=content,
                role=MessageRole.ASSISTANT,
                language=language,
                metadata=metadata,
            ),
        )
    except DatabaseUnavailableError:
        raise
    except Exception as error:
        runtime._log_failure("assistant_persistence_failed", error)
        raise HTTPException(503, "Chat persistence unavailable")


@router.post("/legal-query")
@limiter.limit(settings.LLM_RATE_LIMIT)
async def legal_query(
    request: Request,
    payload: LegalQueryRequest,
    principal: Principal = Depends(require_principal),
):
    import main as runtime

    try:
        cache_key, history = await runtime._prepare_query_context(
            payload, principal.id, "query"
        )
        return await answer_query(
            runtime.app.state,
            payload.query,
            payload.language,
            history=history,
            context=payload.context,
            cache_key=cache_key,
        )
    except HTTPException:
        raise
    except DatabaseUnavailableError:
        raise HTTPException(503, "Chat persistence unavailable")
    except Exception as error:
        runtime._log_failure("legal_query_failed", error, request)
        raise HTTPException(500, "Legal query failed")


@router.post("/legal-query-stream")
@limiter.limit(settings.LLM_RATE_LIMIT)
async def legal_query_stream(
    request: Request,
    payload: LegalQueryRequest,
    principal: Principal = Depends(require_principal),
):
    """NDJSON v1: español progresivo, con respuesta final validada."""
    import main as runtime

    try:
        cache_key, history = await runtime._prepare_query_context(
            payload, principal.id, "query"
        )
        if payload.conversation_id:
            from models.chat_models import MessageCreate, MessageRole

            await runtime.chat_service.add_message(
                payload.conversation_id,
                principal.id,
                MessageCreate(
                    content=payload.query,
                    role=MessageRole.USER,
                    language=payload.language,
                ),
            )
    except HTTPException:
        raise
    except DatabaseUnavailableError:
        raise HTTPException(503, "Chat persistence unavailable")
    except ValueError:
        raise HTTPException(404, "Conversation not found")
    except Exception as error:
        runtime._log_failure("legal_query_stream_failed", error, request)
        raise HTTPException(500, "Legal query stream failed")

    async def persist(result):
        metadata = {"sources": result["sources"], "validation": result["validation"]}
        if any(
            c.get("sat_section")
            for c in result.get("metadata", {}).get("citations", [])
        ):
            # Keep the citation tied to the version used, even after a corpus update.
            metadata["api_response"] = result
        await _persist_assistant_response(
            payload.conversation_id,
            principal.id,
            result["response"],
            payload.language,
            metadata,
        )

    request_id = getattr(request.state, "request_id", "unknown")
    source = stream_legal_query(
        run_pipeline=lambda on_stage, on_delta=None: answer_query(
            runtime.app.state,
            payload.query,
            payload.language,
            history=history,
            context=payload.context,
            cache_key=cache_key,
            on_stage=on_stage,
            **({"on_delta": on_delta} if on_delta is not None else {}),
        ),
        extract_text=lambda result: runtime._extract_response_text(
            result["response"], payload.language
        ),
        persist=persist,
        request_id=request_id,
        language=payload.language,
        timeout_s=settings.STREAM_PIPELINE_TIMEOUT_SECONDS,
        live_text=payload.language == "spanish",
    )
    events = guard_stream(
        source,
        extract_text=lambda data: runtime._extract_response_text(
            data["response"], payload.language
        ),
        request_id=request_id,
        idle_timeout_s=settings.STREAM_IDLE_TIMEOUT_SECONDS,
        live_text=payload.language == "spanish",
    )
    return StreamingResponse(
        events,
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/generate-pdf-report",
    responses={
        500: {"description": "PDF generation failed"},
        503: {"description": "PDF generation unavailable"},
    },
)
async def generate_pdf_report(
    payload: PDFReportRequest,
    principal: Principal = Depends(require_principal),
):
    """Genera reporte PDF legal con ReportLab."""
    import main as runtime

    try:
        from utils.pdf_generator import generate_legal_pdf_bytes

        pdf_bytes = generate_legal_pdf_bytes(
            query=payload.query,
            response_data=payload.response,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="reporte_legal.pdf"',
                "Cache-Control": "no-store",
            },
        )
    except ImportError:
        raise HTTPException(503, "PDF generation unavailable")
    except Exception as error:
        runtime._log_failure("pdf_generation_failed", error)
        raise HTTPException(500, "PDF generation failed")


@router.post("/tts/synthesize")
@limiter.limit(settings.LLM_RATE_LIMIT)
async def synthesize_speech(
    request: Request,
    payload: TTSRequest,
    principal: Principal = Depends(require_principal),
):
    """Sintetiza texto a voz (Web Speech API para español, MMS-TTS para quechua)."""
    import main as runtime

    try:
        if payload.language != "quechua":
            return {
                "success": True,
                "method": "web_speech_api",
                "language": "es",
                "message": "Use Web Speech API in the browser for Spanish",
                "text": payload.text,
            }

        tts_service = TTSService()
        if not tts_service.is_available("qu"):
            raise HTTPException(
                503, f"TTS not available for language: {payload.language}"
            )
        audio_bytes = await tts_service.synthesize_quechua(payload.text)
        if audio_bytes is None:
            raise HTTPException(500, "Failed to synthesize audio")

        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition": 'attachment; filename="quechua_audio.wav"',
                "Cache-Control": "no-store",
            },
        )
    except HTTPException:
        raise
    except Exception as error:
        runtime._log_failure("tts_synthesis_failed", error, request)
        raise HTTPException(500, "TTS synthesis failed")
