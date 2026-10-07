from datetime import datetime, timezone
from typing import Annotated, Optional
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from config.settings import settings
from database.postgres_adapter_final import DatabaseUnavailableError
from models.chat_models import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationHistory,
    ConversationList,
    ConversationResponse,
    ConversationUpdate,
)
from modules.chat.services.chat_service import chat_service
from security import Principal, limiter, require_principal
from models.request_types import NonBlankMessage

router = APIRouter(prefix="/chat", tags=["chat"])
CurrentPrincipal = Annotated[Principal, Depends(require_principal)]
logger = logging.getLogger("ia_juridica.chat")


def conversation_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Conversation not found")


class ContinueConversationRequest(BaseModel):
    message: NonBlankMessage


@router.post("/message", response_model=ChatResponse)
@limiter.limit(settings.LLM_RATE_LIMIT)
async def send_message(
    request: Request,
    payload: ChatRequest,
    principal: CurrentPrincipal,
):
    try:
        principal_id = principal.id
        return await chat_service.process_chat_message(payload, principal_id)
    except ValueError:
        raise conversation_not_found()


@router.get("/conversations", response_model=ConversationList)
async def get_user_conversations(
    request: Request,
    principal: CurrentPrincipal,
    limit: int = Query(default=20, ge=1, le=100),
    active_only: bool = Query(default=True),
):
    # Solución temporal de depuración: usar un identificador de principal predeterminado cuando la autenticación esté deshabilitada.
    principal_id = principal.id
    # Convertir la cadena a booleano si es necesario
    if isinstance(active_only, str):
        active_only = active_only.lower() in ("true", "1", "yes")

    try:
        conversations = await chat_service.get_user_conversations(principal_id, limit)
    except DatabaseUnavailableError:
        raise HTTPException(503, "Chat persistence unavailable")
    except Exception as e:
        logger.error(
            "chat_operation_failed request_id=%s error_type=%s",
            request.state.request_id,
            type(e).__name__,
        )
        raise HTTPException(500, "Failed to list conversations")

    if active_only:
        conversations = [
            conversation for conversation in conversations if conversation.is_active
        ]
    return ConversationList(
        conversations=conversations,
        total_count=len(conversations),
        active_count=sum(conversation.is_active for conversation in conversations),
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationHistory)
async def get_conversation_history(
    request: Request,
    conversation_id: str,
    principal: CurrentPrincipal,
    limit: int = Query(default=50, ge=1, le=200),
):
    # Solución temporal de depuración: usar un identificador de principal predeterminado cuando la autenticación esté deshabilitada.
    principal_id = principal.id

    conversation = await chat_service.get_conversation(conversation_id, principal_id)
    if not conversation:
        raise conversation_not_found()
    messages = await chat_service.get_conversation_messages(
        conversation_id, principal_id, limit
    )
    context_summary = await chat_service._build_conversation_context(
        conversation_id, principal_id, conversation.language
    )
    return ConversationHistory(
        conversation=conversation,
        messages=messages,
        total_messages=len(messages),
        context_summary=context_summary.model_dump(),
    )


@router.post("/conversations", response_model=ConversationResponse)
@limiter.limit(settings.CONVERSATION_CREATE_RATE_LIMIT)
async def create_conversation(
    request: Request,
    conversation_data: ConversationCreate,
    principal: CurrentPrincipal,
):
    # Solución temporal de depuración: usar un identificador de principal predeterminado cuando la autenticación esté deshabilitada.
    principal_id = principal.id

    try:
        conversation = await chat_service.create_conversation(
            user_id=principal_id,
            title=conversation_data.title,
            language=conversation_data.language,
        )
    except DatabaseUnavailableError:
        raise HTTPException(status_code=503, detail="Chat persistence unavailable")
    except Exception as e:
        # Gestionar otros errores (por ejemplo, si el usuario no existe)
        logger.error(
            "chat_operation_failed request_id=%s error_type=%s",
            request.state.request_id,
            type(e).__name__,
        )
        raise HTTPException(status_code=500, detail="Failed to create conversation")
    if conversation_data.initial_message:
        await chat_service.process_chat_message(
            ChatRequest(
                message=conversation_data.initial_message,
                conversation_id=conversation.id,
                language=conversation_data.language,
            ),
            principal_id,
        )
    return conversation


@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    request: Request,
    conversation_id: str,
    update_data: ConversationUpdate,
    principal: CurrentPrincipal,
):
    # Solución temporal de depuración: usar un identificador de principal predeterminado cuando la autenticación esté deshabilitada.
    principal_id = principal.id

    try:
        updated = await chat_service.update_conversation(
            conversation_id, principal_id, update_data
        )
        if not updated:
            raise conversation_not_found()
        return updated
    except HTTPException:
        raise
    except DatabaseUnavailableError:
        raise HTTPException(503, "Chat persistence unavailable")
    except Exception as e:
        logger.error(
            "conversation_update_failed request_id=%s error_type=%s",
            request.state.request_id,
            type(e).__name__,
        )
        raise


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    request: Request,
    conversation_id: str,
    principal: CurrentPrincipal,
):
    # Solución temporal de depuración: usar un identificador de principal predeterminado cuando la autenticación esté deshabilitada.
    principal_id = principal.id

    # Temporary mock for debugging - bypass database
    if principal_id == "debug-user":
        return {"success": True}

    if not await chat_service.delete_conversation(conversation_id, principal_id):
        raise conversation_not_found()
    return {"success": True}


@router.get("/search")
async def search_conversations(
    request: Request,
    principal: CurrentPrincipal,
    q: str = Query(..., min_length=2),
    limit: int = Query(default=10, ge=1, le=50),
):
    # Solución temporal de depuración: usar un identificador de principal predeterminado cuando la autenticación esté deshabilitada.
    principal_id = principal.id
    conversations = await chat_service.search_conversations(principal_id, q, limit)
    return {
        "success": True,
        "results": conversations,
        "total_count": len(conversations),
    }


@router.get("/conversations/{conversation_id}/stats")
async def get_conversation_stats(
    request: Request,
    conversation_id: str,
    principal: CurrentPrincipal,
):
    # Solución temporal de depuración: usar un identificador de principal predeterminado cuando la autenticación esté deshabilitada.
    principal_id = principal.id
    stats = await chat_service.get_conversation_stats(conversation_id, principal_id)
    if not stats:
        raise conversation_not_found()
    return {"success": True, "stats": stats}


@router.post("/conversations/{conversation_id}/continue", response_model=ChatResponse)
@limiter.limit(settings.LLM_RATE_LIMIT)
async def continue_conversation(
    request: Request,
    conversation_id: str,
    payload: ContinueConversationRequest,
    principal: CurrentPrincipal,
):
    # Solución temporal de depuración: usar un identificador de principal predeterminado cuando la autenticación esté deshabilitada.
    principal_id = principal.id

    conversation = await chat_service.get_conversation(conversation_id, principal_id)
    if not conversation:
        raise conversation_not_found()
    return await chat_service.process_chat_message(
        ChatRequest(
            message=payload.message,
            conversation_id=conversation_id,
            language=conversation.language,
        ),
        principal_id,
    )


@router.post("/invalidate-cache/{conversation_id}")
async def invalidate_conversation_cache(
    request: Request,
    conversation_id: str,
    principal: CurrentPrincipal,
):
    # Solución temporal de depuración: usar un identificador de principal predeterminado cuando la autenticación esté deshabilitada.
    principal_id = principal.id
    if not await chat_service.invalidate_conversation_cache(
        conversation_id, principal_id
    ):
        raise conversation_not_found()
    return {"success": True}


@router.get("/health")
async def chat_health_check():
    try:
        redis_health = await chat_service.redis.health_check()
        db_health = await chat_service.db.health_check()
        test_key = f"health_test_{uuid.uuid4().hex[:8]}"
        await chat_service.redis.set_cache(test_key, "test", 10)
        cached = await chat_service.redis.get_cache(test_key)
        await chat_service.redis.delete_cache(test_key)
        cache_working = cached == "test"
        overall_status = (
            "healthy"
            if (
                redis_health.get("status") == "healthy"
                and db_health.get("status") == "healthy"
                and cache_working
            )
            else "degraded"
        )
        return {
            "status": overall_status,
            "components": {
                "redis": redis_health.get("status", "unknown"),
                "postgresql": db_health.get("status", "unknown"),
                "cache": "working" if cache_working else "error",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
