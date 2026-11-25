"""Stream telemetry, user feedback, quality overview, evaluation, and stats endpoints."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from config.settings import settings
from database.errors import DatabaseUnavailableError
from optimization.llm_optimizer import LLMOptimizer
from security import Principal, limiter, require_principal, verify_admin_api_key
from services.feedback_store import FeedbackIn, FeedbackStore
from services.quality_access import require_quality_admin
from services.stream_telemetry import StreamTelemetry, stream_metrics

router = APIRouter(tags=["quality"])

MAX_TELEMETRY_BYTES = 4096


class QueueDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accept", "reject"]


def _feedback_store() -> FeedbackStore:
    import main as runtime

    store = getattr(runtime.app.state, "feedback_store", None)
    if store is None:
        store = FeedbackStore(settings.FEEDBACK_DIR)
        runtime.app.state.feedback_store = store
    return store


def _message_role(message) -> str:
    return getattr(message.role, "value", message.role)


async def _rated_exchange(conversation_id: str, owner_id: str):
    """Última consulta y respuesta de una conversación propia; (None, None) si no se pueden leer."""
    import main as runtime

    try:
        if not await runtime.chat_service.get_conversation(conversation_id, owner_id):
            return None, None
        messages = await runtime.chat_service.get_conversation_messages(
            conversation_id, owner_id, limit=12
        )
    except (DatabaseUnavailableError, ValueError):
        return None, None
    answer = next(
        (m.content for m in reversed(messages) if _message_role(m) == "assistant"),
        None,
    )
    query = next(
        (m.content for m in reversed(messages) if _message_role(m) == "user"),
        None,
    )
    return query, answer


@router.post("/telemetry/stream", status_code=204)
@limiter.limit(settings.TELEMETRY_RATE_LIMIT)
async def stream_telemetry(request: Request):
    """Telemetría del cliente: solo números y request_id, nunca texto."""
    body = await request.body()
    if len(body) > MAX_TELEMETRY_BYTES:
        raise HTTPException(413, "Telemetry payload too large")
    try:
        item = StreamTelemetry.model_validate_json(body)
    except ValueError:
        raise HTTPException(422, "Invalid telemetry payload")
    stream_metrics.record(item)
    return Response(status_code=204)


@router.get("/telemetry/stream/summary")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def stream_telemetry_summary(
    request: Request, _auth: bool = Depends(verify_admin_api_key)
):
    return {"success": True, "summary": stream_metrics.summary()}


@router.post("/feedback", status_code=201)
@limiter.limit(settings.FEEDBACK_RATE_LIMIT)
async def submit_feedback(
    request: Request,
    payload: FeedbackIn,
    principal: Principal = Depends(require_principal),
):
    query = answer = None
    if payload.share_text and payload.rating == "down" and payload.conversation_id:
        query, answer = await _rated_exchange(payload.conversation_id, principal.id)
    record = _feedback_store().add(principal.id, payload, query=query, answer=answer)
    return {
        "success": True,
        "id": record["id"],
        "queued": record["queue_status"] == "pending",
    }


@router.get("/feedback/queue")
@limiter.limit(settings.QUALITY_RATE_LIMIT)
async def feedback_queue(
    request: Request, _admin: str = Depends(require_quality_admin)
):
    store = _feedback_store()
    return {
        "success": True,
        "summary": store.summary(),
        "items": store.queue("pending")[:50],
    }


@router.post("/feedback/queue/{item_id}/decision")
@limiter.limit(settings.QUALITY_RATE_LIMIT)
async def decide_feedback(
    request: Request,
    item_id: str,
    payload: QueueDecision,
    _admin: str = Depends(require_quality_admin),
):
    record = _feedback_store().decide(item_id, payload.decision)
    if record is None:
        raise HTTPException(404, "Queue item not found")
    return {
        "success": True,
        "id": record["id"],
        "queue_status": record["queue_status"],
    }


@router.get("/quality/published")
@limiter.limit(settings.QUALITY_RATE_LIMIT)
async def quality_published(request: Request):
    import main as runtime

    return {"success": True, "published": runtime.load_published()}


@router.get("/quality/admin/overview")
@limiter.limit(settings.QUALITY_RATE_LIMIT)
async def quality_admin_overview(
    request: Request, _admin: str = Depends(require_quality_admin)
):
    import main as runtime

    return {
        "success": True,
        "overview": runtime.admin_overview(_feedback_store(), stream_metrics),
    }


@router.post("/evaluate-system")
@limiter.limit(settings.ADMIN_RATE_LIMIT)
async def evaluate_system(
    request: Request,
    _auth: bool = Depends(verify_admin_api_key),
    provider: Literal["application", "nvidia-voyage"] = "application",
    limit: Optional[int] = Query(default=None, ge=1, le=1000),
):
    import main as runtime

    try:
        if not settings.EVALUATION_ENABLED:
            raise HTTPException(503, "Evaluación deshabilitada por configuración")
        if provider == "nvidia-voyage" and limit is None:
            raise HTTPException(422, "Indica el límite usado al grabar el cassette")
        report = (
            await runtime._evaluate_harness(provider, limit)
            if provider == "nvidia-voyage"
            else await runtime._evaluate_harness()
        )
        return {
            "success": report["n_cases"] > 0 and report["n_errors"] == 0,
            "results": {
                "evaluation_scope": "recorded_responses_not_live_model",
                "provider": provider,
                "judge": report["judge"],
                "n_cases": report["n_cases"],
                "n_errors": report["n_errors"],
                "metrics": report["metrics"],
                "gold": report["gold"],
                **(
                    {
                        "ragas_non_llm_string_similarity": report[
                            "ragas_non_llm_string_similarity"
                        ]
                    }
                    if "ragas_non_llm_string_similarity" in report
                    else {}
                ),
            },
        }
    except HTTPException:
        raise
    except (FileNotFoundError, ImportError) as error:
        runtime._log_failure("evaluation_unavailable", error, request)
        raise HTTPException(503, "Harness de evaluación no disponible") from None
    except Exception as error:
        runtime._log_failure("evaluation_failed", error, request)
        raise HTTPException(500, "Evaluation failed")


@router.get("/validation-stats")
async def get_validation_stats(_auth: bool = Depends(verify_admin_api_key)):
    """Retorna estadísticas del pipeline de validación y uso del optimizador."""
    import main as runtime

    try:
        optimizer: LLMOptimizer = runtime.app.state.llm_optimizer
        rag_stats = (
            runtime.app.state.rag_engine.get_stats()
            if runtime.app.state.rag_engine
            else {"engine": "sat"}
        )
        cfg = runtime.app.state.response_validator.config
        return {
            "success": True,
            "optimizer": optimizer.get_session_stats(),
            "rag_engine": rag_stats,
            "validation_config": {
                "hallucination_threshold": cfg.hallucination_threshold,
                "cross_check_threshold": cfg.cross_check_threshold,
                "min_confidence_score": cfg.min_confidence_score,
                "self_correction_retries": cfg.max_self_correction_retries,
            },
        }
    except Exception as error:
        runtime._log_failure("validation_stats_failed", error)
        raise HTTPException(500, "Stats failed")
