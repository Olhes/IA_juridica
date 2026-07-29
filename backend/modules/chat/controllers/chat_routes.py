from datetime import datetime, timezone
from typing import Annotated
import uuid

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


router = APIRouter(prefix="/chat", tags=["chat"])
# Temporarily disable auth for debugging
# CurrentPrincipal = Annotated[Principal, Depends(require_principal)]
CurrentPrincipal = None
def conversation_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Conversation not found")


class ContinueConversationRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)


@router.post("/message", response_model=ChatResponse)
@limiter.limit(settings.LLM_RATE_LIMIT)
async def send_message(
    request: Request,
    payload: ChatRequest,
    principal: CurrentPrincipal,
):
    try:
        principal_id = principal.id if principal else "debug-user"
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
    # Temporary fix for debugging: use a default principal ID when auth is disabled
    principal_id = principal.id if principal else "debug-user"
    # Convert string to bool if needed
    if isinstance(active_only, str):
        active_only = active_only.lower() in ('true', '1', 'yes')
    conversations = await chat_service.get_user_conversations(principal_id, limit)
    if active_only:
        conversations = [conversation for conversation in conversations if conversation.is_active]
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
    conversation = await chat_service.get_conversation(conversation_id, principal.id)
    if not conversation:
        raise conversation_not_found()
    messages = await chat_service.get_conversation_messages(
        conversation_id, principal.id, limit
    )
    context_summary = await chat_service._build_conversation_context(
        conversation_id, principal.id, conversation.language
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
    try:
        conversation = await chat_service.create_conversation(
            user_id=principal.id,
            title=conversation_data.title,
            language=conversation_data.language,
        )
    except DatabaseUnavailableError:
        raise HTTPException(status_code=503, detail="Chat persistence unavailable")
    if conversation_data.initial_message:
        await chat_service.process_chat_message(
            ChatRequest(
                message=conversation_data.initial_message,
                conversation_id=conversation.id,
                language=conversation_data.language,
            ),
            principal.id,
        )
    return conversation


@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    request: Request,
    conversation_id: str,
    update_data: ConversationUpdate,
    principal: CurrentPrincipal,
):
    updated = await chat_service.update_conversation(
        conversation_id, principal.id, update_data
    )
    if not updated:
        raise conversation_not_found()
    return updated


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    request: Request,
    conversation_id: str,
    principal: CurrentPrincipal,
):
    if not await chat_service.delete_conversation(conversation_id, principal.id):
        raise conversation_not_found()
    return {"success": True}


@router.get("/search")
async def search_conversations(
    request: Request,
    principal: CurrentPrincipal,
    q: str = Query(..., min_length=2),
    limit: int = Query(default=10, ge=1, le=50),
):
    conversations = await chat_service.search_conversations(principal.id, q, limit)
    return {"success": True, "results": conversations, "total_count": len(conversations)}


@router.get("/conversations/{conversation_id}/stats")
async def get_conversation_stats(
    request: Request,
    conversation_id: str,
    principal: CurrentPrincipal,
):
    stats = await chat_service.get_conversation_stats(conversation_id, principal.id)
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
    conversation = await chat_service.get_conversation(conversation_id, principal.id)
    if not conversation:
        raise conversation_not_found()
    return await chat_service.process_chat_message(
        ChatRequest(
            message=payload.message,
            conversation_id=conversation_id,
            language=conversation.language,
        ),
        principal.id,
    )


@router.post("/invalidate-cache/{conversation_id}")
async def invalidate_conversation_cache(
    request: Request,
    conversation_id: str,
    principal: CurrentPrincipal,
):
    if not await chat_service.invalidate_conversation_cache(conversation_id, principal.id):
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
        overall_status = "healthy" if (
            redis_health.get("status") == "healthy"
            and db_health.get("status") == "healthy"
            and cache_working
        ) else "degraded"
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
