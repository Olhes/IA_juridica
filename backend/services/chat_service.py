"""
Servicio de gestión de conversaciones con persistencia
IA Jurídica - Redis Cache + PostgreSQL Storage
"""

import uuid
import hashlib
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import json

from models.chat_models import (
    MessageCreate, MessageResponse, ConversationCreate, ConversationResponse,
    ConversationUpdate, ChatRequest, ChatResponse, CachedConversation,
    UserSession, ConversationContext, ContextSummary, MessageType
)
from database.redis_adapter import redis_adapter
from database.postgres_adapter_final import PostgreSQLAdapter
from config.settings import settings
from language.language_detector import LanguageDetector
from language.translation_service import TranslationService


class ChatService:
    """Servicio principal para gestión de chat persistente"""
    
    def __init__(self):
        self.redis = redis_adapter
        self.db = PostgreSQLAdapter()
        self.cache_ttl = {
            'conversation': 3600,  # 1 hora
            'session': 86400,     # 24 horas
            'context': 1800       # 30 minutos
        }
        
        # Inicializar servicios de idioma
        self.language_detector = LanguageDetector()
        self.translation_service = TranslationService()
    
    async def initialize(self):
        """Inicializar servicio y conexiones"""
        await self.redis.initialize()
        await self.db.initialize()
    
    # === Gestión de Sesiones ===
    
    async def create_or_get_session(self, user_id: str, session_token: Optional[str] = None) -> UserSession:
        """Crear o recuperar sesión de usuario"""
        if session_token:
            # Intentar recuperar sesión existente
            try:
                cached_session = await self.redis.get_cache(f"session:{session_token}")
                if cached_session:
                    session = UserSession.from_redis_format(cached_session)
                    # Verificar que la sesión no esté expirada
                    if session.expires_at > datetime.utcnow():
                        # Actualizar última actividad
                        session.last_activity = datetime.utcnow()
                        session.expires_at = datetime.utcnow() + timedelta(hours=24)
                        await self.redis.create_user_session(session_token, session.to_redis_format())
                        return session
                    else:
                        print(f"⚠️ Session {session_token} expired, creating new one")
            except Exception as e:
                print(f"⚠️ Error retrieving session {session_token}: {e}")
                # Continuar para crear nueva sesión
        
        # Crear nueva sesión
        session_id = str(uuid.uuid4())
        new_session = UserSession(
            session_id=session_id,
            user_id=user_id,
            language_preferences={"primary": "spanish", "secondary": "quechua"},
            last_activity=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        await self.redis.create_user_session(session_id, new_session.to_redis_format())
        return new_session
    
    # === Gestión de Conversaciones ===
    
    async def create_conversation(self, user_id: str, title: Optional[str] = None, 
                                language: str = "spanish") -> ConversationResponse:
        """Crear nueva conversación"""
        conversation_data = ConversationCreate(
            user_id=user_id,
            title=title or f"Conversación {datetime.now().strftime('%d/%m %H:%M')}",
            language=language
        )
        
        # Guardar en base de datos (pasar parámetros individuales)
        db_conversation = await self.db.create_conversation(
            user_id=user_id,
            title=conversation_data.title,
            language=language
        )
        
        # Construir respuesta desde el dict del adapter
        conversation_response = ConversationResponse(
            id=db_conversation['id'],
            user_id=db_conversation['user_id'],
            title=db_conversation['title'],
            language=db_conversation['language'],
            metadata=db_conversation.get('metadata', {}),
            created_at=db_conversation['created_at'] if isinstance(db_conversation['created_at'], datetime) else datetime.fromisoformat(db_conversation['created_at']),
            updated_at=db_conversation.get('updated_at', db_conversation['created_at']) if isinstance(db_conversation.get('updated_at', db_conversation['created_at']), datetime) else datetime.fromisoformat(db_conversation.get('updated_at', db_conversation['created_at'])),
            is_active=db_conversation.get('is_active', True),
            message_count=0,
            last_message=None
        )
        
        # Cache en Redis
        try:
            cached_conv = CachedConversation(
                id=conversation_response.id,
                user_id=conversation_response.user_id,
                title=conversation_response.title,
                language=conversation_response.language,
                messages=[],
                metadata=conversation_response.metadata,
                created_at=conversation_response.created_at,
                updated_at=conversation_response.updated_at
            )
            
            await self.redis.set_cache(
                f"conversation:{conversation_response.id}",
                cached_conv.to_redis_format(),
                self.cache_ttl['conversation']
            )
        except Exception as e:
            print(f"⚠️ Error caching conversation: {e}")
        
        return conversation_response
    
    async def get_conversation(self, conversation_id: str, user_id: str) -> Optional[ConversationResponse]:
        """Obtener conversación con mensajes"""
        # Primero intentar Redis cache
        cached = await self.redis.get_cache(f"conversation:{conversation_id}")
        if cached:
            cached_conv = CachedConversation.from_redis_format(cached)
            if cached_conv.user_id == user_id:
                return ConversationResponse(
                    id=cached_conv.id,
                    user_id=cached_conv.user_id,
                    title=cached_conv.title,
                    language=cached_conv.language,
                    metadata=cached_conv.metadata,
                    created_at=cached_conv.created_at,
                    updated_at=cached_conv.updated_at,
                    is_active=True,
                    message_count=len(cached_conv.messages),
                    last_message=cached_conv.messages[-1] if cached_conv.messages else None
                )
        
        # Si no está en cache, buscar en base de datos
        db_conversation = await self.db.get_conversation(conversation_id)
        if not db_conversation:
            return None
        
        # Obtener mensajes
        messages = await self.db.get_conversation_messages(conversation_id)
        message_responses = []
        for msg in messages:
            try:
                message_responses.append(MessageResponse(
                    id=msg['id'],
                    conversation_id=msg.get('conversation_id', conversation_id),
                    role=msg['role'],
                    content=msg['content'],
                    language=msg.get('language', 'spanish'),
                    metadata=msg.get('metadata', {}),
                    message_type=MessageType.TEXT,
                    tokens_used=msg.get('tokens_used', 0),
                    model_used=msg.get('model_used'),
                    created_at=msg['created_at'] if isinstance(msg['created_at'], datetime) else datetime.fromisoformat(msg['created_at'])
                ))
            except Exception as e:
                print(f"⚠️ Error parsing message: {e}")
                continue
        
        # Construir respuesta
        conversation_response = ConversationResponse(
            id=db_conversation['id'],
            user_id=db_conversation.get('user_id', ''),
            title=db_conversation['title'],
            language=db_conversation['language'],
            metadata=db_conversation.get('metadata', {}),
            created_at=db_conversation['created_at'] if isinstance(db_conversation['created_at'], datetime) else datetime.fromisoformat(db_conversation['created_at']),
            updated_at=db_conversation.get('updated_at', db_conversation['created_at']) if isinstance(db_conversation.get('updated_at', db_conversation['created_at']), datetime) else datetime.fromisoformat(db_conversation.get('updated_at', db_conversation['created_at'])),
            is_active=db_conversation.get('is_active', True),
            message_count=len(message_responses),
            last_message=message_responses[-1] if message_responses else None
        )
        
        # Actualizar cache
        try:
            cached_conv = CachedConversation(
                id=conversation_response.id,
                user_id=conversation_response.user_id,
                title=conversation_response.title,
                language=conversation_response.language,
                messages=message_responses,
                metadata=conversation_response.metadata,
                created_at=conversation_response.created_at,
                updated_at=conversation_response.updated_at
            )
            
            await self.redis.set_cache(
                f"conversation:{conversation_id}",
                cached_conv.to_redis_format(),
                self.cache_ttl['conversation']
            )
        except Exception as e:
            print(f"⚠️ Error caching conversation: {e}")
        
        return conversation_response
    
    async def get_user_conversations(self, user_id: str, limit: int = 50) -> List[ConversationResponse]:
        """Obtener conversaciones de un usuario"""
        conversations = await self.db.get_user_conversations(user_id, limit)
        result = []
        for conv in conversations:
            try:
                result.append(ConversationResponse(
                    id=conv['id'],
                    user_id=conv.get('user_id', ''),
                    title=conv['title'],
                    language=conv['language'],
                    metadata=conv.get('metadata', {}),
                    created_at=conv['created_at'] if isinstance(conv['created_at'], datetime) else datetime.fromisoformat(conv['created_at']),
                    updated_at=conv.get('updated_at', conv['created_at']) if isinstance(conv.get('updated_at', conv['created_at']), datetime) else datetime.fromisoformat(conv.get('updated_at', conv['created_at'])),
                    is_active=conv.get('is_active', True),
                    message_count=conv.get('message_count', 0),
                    last_message=None
                ))
            except Exception as e:
                print(f"⚠️ Error parsing conversation: {e}")
                continue
        return result
    
    # === Gestión de Mensajes ===
    
    async def add_message(self, conversation_id: str, message_data: MessageCreate) -> MessageResponse:
        """Agregar mensaje a conversación"""
        # Guardar en base de datos (pasar parámetros individuales)
        db_message = await self.db.create_message(
            conversation_id=conversation_id,
            content=message_data.content,
            role=message_data.role,
            metadata=message_data.metadata
        )
        message_response = MessageResponse.model_validate(db_message)
        
        # Actualizar cache en Redis
        cached = await self.redis.get_cache(f"conversation:{conversation_id}")
        if cached:
            cached_conv = CachedConversation.from_redis_format(cached)
            cached_conv.messages.append(message_response)
            cached_conv.updated_at = datetime.utcnow()
            
            await self.redis.set_cache(
                f"conversation:{conversation_id}",
                cached_conv.to_redis_format(),
                self.cache_ttl['conversation']
            )
        
        return message_response
    
    async def get_conversation_messages(self, conversation_id: str, limit: int = 100) -> List[MessageResponse]:
        """Obtener mensajes de conversación"""
        # Intentar cache primero
        cached = await self.redis.get_cache(f"conversation:{conversation_id}")
        if cached:
            cached_conv = CachedConversation.from_redis_format(cached)
            return cached_conv.messages[-limit:] if len(cached_conv.messages) > limit else cached_conv.messages
        
        # Si no está en cache, buscar en DB (el método del adapter no usa limit)
        messages = await self.db.get_conversation_messages(conversation_id)
        return [MessageResponse.model_validate(msg) for msg in messages]
    
    # === Procesamiento de Chat ===
    
    async def process_chat_message(self, request: ChatRequest, user_id: str) -> ChatResponse:
        """Procesar mensaje de chat con persistencia y traducción automática"""
        print(f"🔍 Procesando mensaje: {request.message[:50]}...")
        print(f"🌐 Idioma solicitado: {request.language}")
        
        # 1. Detectar idioma del mensaje del usuario
        detected_language = self.language_detector.detect_language(request.message)
        print(f"🔎 Idioma detectado: {detected_language}")
        
        # 2. Si el idioma es quechua, traducir a español para procesamiento
        query_for_processing = request.message
        original_language = request.language
        
        if detected_language == "qu" or request.language == "quechua":
            print(f"🔄 Detectado quechua, iniciando traducción a español...")
            # Traducir consulta de quechua a español
            translation_result = await self.translation_service.translate(
                text=request.message,
                source_lang="qu",
                target_lang="es"
            )
            
            print(f"📊 Resultado de traducción: {translation_result}")
            
            if translation_result.get("success"):
                query_for_processing = translation_result["translated_text"]
                original_language = "quechua"
                print(f"✅ Traducción Quechua -> Español: {request.message} -> {query_for_processing}")
            else:
                # Fallback: usar mensaje original si falla traducción
                query_for_processing = request.message
                original_language = "quechua"
                print(f"⚠️  Traducción falló, usando mensaje original")
        
        # 3. Gestionar sesión
        session = await self.create_or_get_session(user_id, request.session_token)
        
        # 4. Determinar conversación
        conversation_id = request.conversation_id
        if not conversation_id:
            # Crear nueva conversación
            conversation = await self.create_conversation(
                user_id=user_id,
                language=original_language
            )
            conversation_id = conversation.id
        else:
            # Verificar que la conversación exists y pertenece al usuario
            conversation = await self.get_conversation(conversation_id, user_id)
            if not conversation:
                raise ValueError("Conversación no encontrada")
        
        # 5. Guardar mensaje del usuario (en idioma original)
        user_message = MessageCreate(
            role="user",
            content=request.message,
            language=original_language,
            metadata=request.context or {}
        )
        
        saved_message = await self.add_message(conversation_id, user_message)
        
        # 6. Obtener contexto de conversación
        context = await self._build_conversation_context(conversation_id, original_language)
        
        # 7. Procesar con IA usando el pipeline existente (en español)
        from main import LegalQueryRequest
        import asyncio
        
        # Crear request para el pipeline existente (usando español para procesamiento)
        legal_request = LegalQueryRequest(
            query=query_for_processing,
            language="spanish",  # Procesar siempre en español
            context=request.context,
            conversation_id=conversation_id,
            user_id=user_id
        )
        
        # Obtener respuesta del pipeline existente
        try:
            # Importar aquí para evitar circular imports
            from main import app
            from context.context_engineering import ContextEngineer
            from agents.pydantic_agents import LegalAgent
            from rag.lightrag_engine import LegalRAGEngine
            
            # Obtener componentes del estado de la app
            rag_engine = app.state.rag_engine
            legal_agent = app.state.legal_agent
            context_engineer = app.state.context_engineer
            
            # Procesar con RAG (en español)
            rag_result = await rag_engine.query_with_rerank(query_for_processing)
            
            # Construir prompt enriquecido (en español)
            documents = rag_result.get("documents", [])
            enriched_prompt, enriched_context = context_engineer.build_legal_prompt(
                query=query_for_processing,
                documents=documents,
                language="spanish",
            )
            
            # Generar respuesta con Cohere (en español)
            response = await legal_agent.respond_general(
                query=query_for_processing,
                context=rag_result,
                language="spanish",
                enriched_prompt=enriched_prompt,
            )
            
            # Extraer contenido de la respuesta
            if hasattr(response, "model_dump"):
                response_payload = response.model_dump()
            elif hasattr(response, "dict"):
                response_payload = response.dict()
            else:
                response_payload = response
            
            # Extraer el texto de respuesta en español
            assistant_content = str(
                response_payload.get("respuesta_espanol")
                or response_payload.get("spanish")
                or response_payload.get("answer", "")
            )
            
            # 8. Si el idioma original es quechua, traducir la respuesta de español a quechua
            if original_language == "quechua":
                translation_result = await self.translation_service.translate(
                    text=assistant_content,
                    source_lang="es",
                    target_lang="qu"
                )
                
                if translation_result.get("success"):
                    assistant_content = translation_result["translated_text"]
                    print(f"🔄 Traducción Español -> Quechua completada")
                else:
                    # Fallback: mantener respuesta en español si falla traducción
                    print(f"⚠️ Error traduciendo respuesta a quechua, usando español")
                    assistant_content = assistant_content
            
            # Guardar respuesta del asistente (en idioma original del usuario)
            assistant_message = MessageCreate(
                role="assistant",
                content=assistant_content,
                language=original_language,
                model_used="command-r7b-12-2024",
                metadata={
                    "sources": rag_result.get("sources", []),
                    "rag_result": rag_result,
                    "enriched_context": enriched_context
                }
            )
            
        except Exception as e:
            print(f"Error procesando con IA: {e}")
            # Fallback a respuesta simple
            assistant_message = MessageCreate(
                role="assistant",
                content="Lo siento, no pude procesar tu consulta en este momento. Por favor, intenta nuevamente.",
                language=original_language,
                model_used="fallback",
                metadata={"error": str(e)}
            )
        
        assistant_response = await self.add_message(conversation_id, assistant_message)
        
        # 9. Obtener historial actualizado
        history = await self.get_conversation_messages(conversation_id, limit=10)
        
        # 10. Actualizar sesión
        session.conversation_id = conversation_id
        session.last_activity = datetime.utcnow()
        await self.redis.create_user_session(session.session_id, session.to_redis_format())
        
        return ChatResponse(
            success=True,
            conversation_id=conversation_id,
            session_id=session.session_id,
            message=assistant_response,
            conversation_history=history,
            metadata={
                "context": context.model_dump(),
                "language": original_language,
                "translation_applied": original_language == "quechua"
            }
        )
    
    async def _build_conversation_context(self, conversation_id: str, language: str) -> ConversationContext:
        """Construir contexto de conversación"""
        messages = await self.get_conversation_messages(conversation_id, limit=20)
        
        # Análisis simple del contexto (mejorar con NLP)
        all_text = " ".join([msg.content for msg in messages])
        
        # Detectar tópicos legales básicos
        legal_topics = ["contrato", "demanda", "divorcio", "herencia", "laboral", "penal", "civil"]
        detected_topic = None
        for topic in legal_topics:
            if topic.lower() in all_text.lower():
                detected_topic = topic
                break
        
        return ConversationContext(
            conversation_id=conversation_id,
            detected_legal_topic=detected_topic,
            urgency_level="normal",  # Analizar urgencia basada en palabras clave
            detected_location="Perú",  # Mejorar con detección real
            cultural_context="formal",
            formality_level="formal",
            key_entities=[],  # Extraer con NLP
            metadata={"message_count": len(messages)}
        )
    
    # === Gestión de Sesiones ===
    
    async def clear_user_session(self, user_id: str, session_token: Optional[str] = None) -> bool:
        """Limpiar/invalidar sesión de usuario activa"""
        try:
            # Si se proporciona session_token, eliminar esa sesión específica
            if session_token:
                try:
                    await self.redis.delete_cache(f"session:{session_token}")
                    print(f"✅ Cleared session: {session_token}")
                    return True
                except Exception as e:
                    print(f"⚠️ Error clearing session {session_token}: {e}")
                    return False
            
            # Si no hay session_token, intentar limpiar todas las sesiones del usuario
            # Esto es más complejo sin un índice de sesiones por usuario
            # Por ahora, simplemente retornamos True ya que no hay sesión específica que limpiar
            print(f"ℹ️ No specific session token provided for user {user_id}")
            return True
        except Exception as e:
            print(f"⚠️ Error in clear_user_session: {e}")
            return False
    
    async def invalidate_conversation_cache(self, conversation_id: str) -> bool:
        """Invalidar cache de conversación específica"""
        try:
            await self.redis.delete_cache(f"conversation:{conversation_id}")
            return True
        except Exception as e:
            print(f"⚠️ Error invalidating conversation cache: {e}")
            return False
    
    # === Utilidades ===
    
    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Eliminar conversación"""
        # Eliminar de base de datos
        success = await self.db.delete_conversation(conversation_id, user_id)
        
        if success:
            # Eliminar de cache
            await self.redis.delete_cache(f"conversation:{conversation_id}")
        
        return success
    
    async def search_conversations(self, user_id: str, query: str, limit: int = 20) -> List[ConversationResponse]:
        """Buscar conversaciones por contenido"""
        # Buscar en base de datos
        conversations = await self.db.search_conversations(user_id, query, limit)
        return [ConversationResponse.model_validate(conv) for conv in conversations]
    
    async def get_conversation_stats(self, conversation_id: str, user_id: str) -> Dict[str, Any]:
        """Obtener estadísticas de conversación"""
        conversation = await self.get_conversation(conversation_id, user_id)
        if not conversation:
            return {}
        
        messages = await self.get_conversation_messages(conversation_id)
        
        return {
            "conversation_id": conversation_id,
            "message_count": len(messages),
            "user_messages": len([m for m in messages if m.role == "user"]),
            "assistant_messages": len([m for m in messages if m.role == "assistant"]),
            "total_tokens": sum(m.tokens_used for m in messages),
            "languages": list(set(m.language for m in messages)),
            "duration_hours": (datetime.utcnow() - conversation.created_at).total_seconds() / 3600,
            "last_activity": conversation.updated_at
        }


# Instancia global del servicio
chat_service = ChatService()
