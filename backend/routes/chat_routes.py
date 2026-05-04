"""
Endpoints para chat persistente con Redis + PostgreSQL
IA Jurídica - Sistema de conversaciones continuas
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime
import uuid

from models.chat_models import (
    ChatRequest, ChatResponse, ConversationResponse, ConversationCreate,
    ConversationUpdate, ConversationList, ConversationHistory
)
from services.chat_service import chat_service
from config.settings import settings

router = APIRouter(prefix="/chat", tags=["chat"])


# === Endpoints Principales de Chat ===

@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    Enviar mensaje al chat con persistencia
    
    **Inputs:**
    - message: Texto del mensaje (requerido)
    - conversation_id: ID conversación existente (opcional)
    - language: "spanish" o "quechua" (default: spanish)
    - session_token: Token de sesión (opcional)
    - context: Metadatos adicionales (opcional)
    
    **Flow:**
    1. Verificar/crear sesión en Redis
    2. Crear o recuperar conversación
    3. Guardar mensaje del usuario
    4. Procesar con IA (RAG + Context Engineering)
    5. Guardar respuesta del asistente
    6. Retornar con historial actualizado
    """
    try:
        # Para demostración, usar user_id fijo (en producción usar autenticación)
        user_id = "d1d0e0f7-1b3d-43fc-875d-b6991e6c94af"
        
        response = await chat_service.process_chat_message(request, user_id)
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando mensaje: {str(e)}")


@router.get("/conversations", response_model=ConversationList)
async def get_user_conversations(
    limit: int = Query(default=20, le=100),
    active_only: bool = Query(default=True)
):
    """
    Obtener lista de conversaciones del usuario
    
    **Query params:**
    - limit: Número máximo de conversaciones (max: 100)
    - active_only: Solo conversaciones activas
    """
    try:
        user_id = "d1d0e0f7-1b3d-43fc-875d-b6991e6c94af"  # UUID del usuario demo
        
        conversations = await chat_service.get_user_conversations(user_id, limit)
        
        if active_only:
            conversations = [c for c in conversations if c.is_active]
        
        return ConversationList(
            conversations=conversations,
            total_count=len(conversations),
            active_count=len([c for c in conversations if c.is_active])
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo conversaciones: {str(e)}")


@router.get("/conversations/{conversation_id}", response_model=ConversationHistory)
async def get_conversation_history(conversation_id: str, limit: int = Query(default=50, le=200)):
    """
    Obtener historial completo de una conversación
    
    **Path params:**
    - conversation_id: ID de la conversación
    
    **Query params:**
    - limit: Número máximo de mensajes (max: 200)
    """
    try:
        user_id = "d1d0e0f7-1b3d-43fc-875d-b6991e6c94af"  # UUID del usuario demo
        
        # Obtener conversación
        conversation = await chat_service.get_conversation(conversation_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        
        # Obtener mensajes
        messages = await chat_service.get_conversation_messages(conversation_id, limit)
        
        # Generar resumen de contexto
        context_summary = await chat_service._build_conversation_context(
            conversation_id, conversation.language
        )
        
        return ConversationHistory(
            conversation=conversation,
            messages=messages,
            total_messages=len(messages),
            context_summary=context_summary.model_dump()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo historial: {str(e)}")


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(conversation_data: ConversationCreate):
    """
    Crear nueva conversación
    
    **Body:**
    - user_id: ID del usuario
    - title: Título personalizado (opcional)
    - language: Idioma preferido
    - initial_message: Mensaje inicial (opcional)
    """
    try:
        conversation = await chat_service.create_conversation(
            user_id=conversation_data.user_id,
            title=conversation_data.title,
            language=conversation_data.language
        )
        
        # Si hay mensaje inicial, procesarlo
        if conversation_data.initial_message:
            chat_request = ChatRequest(
                message=conversation_data.initial_message,
                conversation_id=conversation.id,
                language=conversation_data.language
            )
            await chat_service.process_chat_message(chat_request, conversation_data.user_id)
        
        return conversation
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creando conversación: {str(e)}")


@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(conversation_id: str, update_data: ConversationUpdate):
    """
    Actualizar metadata de conversación
    
    **Body:**
    - title: Nuevo título (opcional)
    - metadata: Metadatos adicionales (opcional)
    - is_active: Estado activo (opcional)
    """
    try:
        print(f"DEBUG: Actualizando conversación {conversation_id} con datos: {update_data}")
        user_id = "d1d0e0f7-1b3d-43fc-875d-b6991e6c94af"  # UUID del usuario demo
        
        # Verificar que la conversación exists y pertenece al usuario
        conversation = await chat_service.get_conversation(conversation_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        
        # Actualizar en base de datos
        updated = await chat_service.db.update_conversation(conversation_id, update_data)
        print(f"DEBUG: Resultado de actualización: {updated}")
        if not updated:
            raise HTTPException(status_code=400, detail="No se pudo actualizar la conversación")
        
        # Obtener conversación actualizada
        updated_conversation = await chat_service.get_conversation(conversation_id, user_id)
        return updated_conversation
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando conversación: {str(e)}")


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """
    Eliminar conversación y todos sus mensajes
    
    **Path params:**
    - conversation_id: ID de la conversación a eliminar
    """
    try:
        user_id = "d1d0e0f7-1b3d-43fc-875d-b6991e6c94af"  # UUID del usuario demo
        
        success = await chat_service.delete_conversation(conversation_id, user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Conversación no encontrada o no autorizada")
        
        return {"success": True, "message": "Conversación eliminada correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error eliminando conversación: {str(e)}")


# === Endpoints de Búsqueda ===

@router.get("/search")
async def search_conversations(
    q: str = Query(..., min_length=2, description="Término de búsqueda"),
    limit: int = Query(default=10, le=50)
):
    """
    Buscar conversaciones por contenido
    
    **Query params:**
    - q: Término de búsqueda (requerido, min: 2 caracteres)
    - limit: Número máximo de resultados (max: 50)
    """
    try:
        user_id = "d1d0e0f7-1b3d-43fc-875d-b6991e6c94af"  # UUID del usuario demo
        
        conversations = await chat_service.search_conversations(user_id, q, limit)
        
        return {
            "success": True,
            "query": q,
            "results": conversations,
            "total_count": len(conversations)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en búsqueda: {str(e)}")


# === Endpoints de Estadísticas ===

@router.get("/conversations/{conversation_id}/stats")
async def get_conversation_stats(conversation_id: str):
    """
    Obtener estadísticas detalladas de una conversación
    
    **Stats incluidas:**
    - Número de mensajes totales
    - Mensajes por rol (user/assistant)
    - Tokens consumidos
    - Idiomas utilizados
    - Duración de la conversación
    - Última actividad
    """
    try:
        user_id = "d1d0e0f7-1b3d-43fc-875d-b6991e6c94af"  # UUID del usuario demo
        
        stats = await chat_service.get_conversation_stats(conversation_id, user_id)
        
        if not stats:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        
        return {
            "success": True,
            "stats": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo estadísticas: {str(e)}")


@router.get("/sessions/{session_id}")
async def get_session_info(session_id: str):
    """
    Obtener información de sesión activa
    
    **Info incluida:**
    - ID de usuario
    - Conversación activa
    - Preferencias de idioma
    - Perfil cultural
    - Última actividad
    """
    try:
        cached_session = await chat_service.redis.get_cache(f"session:{session_id}")
        
        if not cached_session:
            raise HTTPException(status_code=404, detail="Sesión no encontrada o expirada")
        
        from models.chat_models import UserSession
        session = UserSession.from_redis_format(cached_session)
        
        return {
            "success": True,
            "session": session.to_redis_format()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo sesión: {str(e)}")


# === Endpoints de Utilidad ===

@router.post("/conversations/{conversation_id}/continue")
async def continue_conversation(conversation_id: str, message: str):
    """
    Continuar conversación existente con nuevo mensaje
    
    **Body:**
    - message: Nuevo mensaje para continuar la conversación
    """
    try:
        user_id = "d1d0e0f7-1b3d-43fc-875d-b6991e6c94af"  # UUID del usuario demo
        
        # Verificar que la conversación exists
        conversation = await chat_service.get_conversation(conversation_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        
        # Procesar mensaje
        chat_request = ChatRequest(
            message=message,
            conversation_id=conversation_id,
            language=conversation.language
        )
        
        response = await chat_service.process_chat_message(chat_request, user_id)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error continuando conversación: {str(e)}")


@router.get("/health")
async def chat_health_check():
    """
    Health check específico para el servicio de chat
    
    **Componentes verificados:**
    - Redis connection
    - PostgreSQL connection
    - Cache functionality
    """
    try:
        # Verificar Redis
        redis_health = await chat_service.redis.health_check()
        
        # Verificar PostgreSQL
        db_health = await chat_service.db.health_check()
        
        # Verificar funcionalidad básica
        test_key = f"health_test_{uuid.uuid4().hex[:8]}"
        await chat_service.redis.set_cache(test_key, "test", 10)
        cached = await chat_service.redis.get_cache(test_key)
        await chat_service.redis.delete_cache(test_key)
        
        cache_working = cached == "test"
        
        overall_status = "healthy" if (
            redis_health.get("status") == "healthy" and
            db_health.get("status") == "healthy" and
            cache_working
        ) else "degraded"
        
        return {
            "status": overall_status,
            "components": {
                "redis": redis_health.get("status", "unknown"),
                "postgresql": db_health.get("status", "unknown"),
                "cache": "working" if cache_working else "error"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
