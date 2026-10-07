"""
Servicio de gestión de conversaciones con persistencia
IA Jurídica - Redis Cache + PostgreSQL Storage
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from models.chat_models import (
    MessageCreate,
    MessageResponse,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    ChatRequest,
    ChatResponse,
    CachedConversation,
    ConversationContext,
    MessageType,
)
from database.redis_adapter import redis_adapter
from database.postgres_adapter_final import PostgreSQLAdapter
from modules.language.services.language_detector import LanguageDetector
from modules.language.services.translation_service import TranslationService


class ChatService:
    """Servicio principal para gestión de chat persistente"""

    def __init__(self):
        self.redis = redis_adapter
        self.db = PostgreSQLAdapter()
        self.cache_ttl = {
            "conversation": 3600,  # 1 hora
            "session": 86400,  # 24 horas
            "context": 1800,  # 30 minutos
        }

        # Inicializar servicios de idioma
        self.language_detector = LanguageDetector()
        self.translation_service = TranslationService()

    async def initialize(self):
        """Inicializar servicio y conexiones"""
        await self.redis.initialize()
        await self.db.initialize()

    # === Gestión de Conversaciones ===

    async def create_conversation(
        self, user_id: str, title: Optional[str] = None, language: str = "spanish"
    ) -> ConversationResponse:
        """Crear nueva conversación"""
        conversation_title = (
            title or f"Conversación {datetime.now().strftime('%d/%m %H:%M')}"
        )

        # Simulación temporal para depuración: omitir la base de datos para debug-user.
        if user_id == "debug-user":
            import uuid

            return ConversationResponse(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title=conversation_title,
                language=language,
                metadata={},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_active=True,
                message_count=0,
                last_message=None,
            )

        # Guardar en base de datos (pasar parámetros individuales)
        db_conversation = await self.db.create_conversation(
            user_id=user_id, title=conversation_title, language=language
        )

        # Construir respuesta desde el dict del adapter
        conversation_response = ConversationResponse(
            id=db_conversation["id"],
            user_id=db_conversation["user_id"],
            title=db_conversation["title"],
            language=db_conversation["language"],
            metadata=db_conversation.get("metadata", {}),
            created_at=(
                db_conversation["created_at"]
                if isinstance(db_conversation["created_at"], datetime)
                else datetime.fromisoformat(db_conversation["created_at"])
            ),
            updated_at=(
                db_conversation.get("updated_at", db_conversation["created_at"])
                if isinstance(
                    db_conversation.get("updated_at", db_conversation["created_at"]),
                    datetime,
                )
                else datetime.fromisoformat(
                    db_conversation.get("updated_at", db_conversation["created_at"])
                )
            ),
            is_active=db_conversation.get("is_active", True),
            message_count=0,
            last_message=None,
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
                updated_at=conversation_response.updated_at,
            )

            await self.redis.set_cache(
                self._conversation_cache_key(user_id, conversation_response.id),
                cached_conv.to_redis_format(),
                self.cache_ttl["conversation"],
            )
        except Exception:
            print("Conversation cache write failed")

        return conversation_response

    async def get_conversation(
        self, conversation_id: str, user_id: str
    ) -> Optional[ConversationResponse]:
        """Obtener conversación con mensajes"""
        # Simulación temporal para depuración: omitir la base de datos para debug-user.
        if user_id == "debug-user":
            return ConversationResponse(
                id=conversation_id,
                user_id=user_id,
                title="Conversación de prueba",
                language="spanish",
                metadata={},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_active=True,
                message_count=0,
                last_message=None,
            )

        # Primero intentar Redis cache
        cache_key = self._conversation_cache_key(user_id, conversation_id)
        cached = await self.redis.get_cache(cache_key)
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
                    last_message=(
                        cached_conv.messages[-1] if cached_conv.messages else None
                    ),
                )

        # Si no está en cache, buscar en base de datos
        db_conversation = await self.db.get_conversation(conversation_id, user_id)
        if not db_conversation:
            return None

        # Obtener mensajes
        messages = await self.db.get_conversation_messages(conversation_id, user_id)
        message_responses = []
        for msg in messages:
            try:
                message_responses.append(
                    MessageResponse(
                        id=msg["id"],
                        conversation_id=msg.get("conversation_id", conversation_id),
                        role=msg["role"],
                        content=msg["content"],
                        language=msg.get("language", "spanish"),
                        metadata=msg.get("metadata", {}),
                        message_type=MessageType.TEXT,
                        tokens_used=msg.get("tokens_used", 0),
                        model_used=msg.get("model_used"),
                        created_at=(
                            msg["created_at"]
                            if isinstance(msg["created_at"], datetime)
                            else datetime.fromisoformat(msg["created_at"])
                        ),
                    )
                )
            except Exception:
                print("Cached message parse failed")
                continue

        # Construir respuesta
        conversation_response = ConversationResponse(
            id=db_conversation["id"],
            user_id=db_conversation.get("user_id", ""),
            title=db_conversation["title"],
            language=db_conversation["language"],
            metadata=db_conversation.get("metadata", {}),
            created_at=(
                db_conversation["created_at"]
                if isinstance(db_conversation["created_at"], datetime)
                else datetime.fromisoformat(db_conversation["created_at"])
            ),
            updated_at=(
                db_conversation.get("updated_at", db_conversation["created_at"])
                if isinstance(
                    db_conversation.get("updated_at", db_conversation["created_at"]),
                    datetime,
                )
                else datetime.fromisoformat(
                    db_conversation.get("updated_at", db_conversation["created_at"])
                )
            ),
            is_active=db_conversation.get("is_active", True),
            message_count=len(message_responses),
            last_message=message_responses[-1] if message_responses else None,
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
                updated_at=conversation_response.updated_at,
            )

            await self.redis.set_cache(
                cache_key, cached_conv.to_redis_format(), self.cache_ttl["conversation"]
            )
        except Exception:
            print("Conversation cache write failed")

        return conversation_response

    async def get_user_conversations(
        self, user_id: str, limit: int = 50
    ) -> List[ConversationResponse]:
        """Obtener conversaciones de un usuario"""
        # Simulación temporal para depuración: omitir la base de datos para debug-user.
        if user_id == "debug-user":
            return []

        conversations = await self.db.get_user_conversations(user_id, limit)
        result = []
        for conv in conversations:
            try:
                result.append(
                    ConversationResponse(
                        id=conv["id"],
                        user_id=conv.get("user_id", ""),
                        title=conv["title"],
                        language=conv["language"],
                        metadata=conv.get("metadata", {}),
                        created_at=(
                            conv["created_at"]
                            if isinstance(conv["created_at"], datetime)
                            else datetime.fromisoformat(conv["created_at"])
                        ),
                        updated_at=(
                            conv.get("updated_at", conv["created_at"])
                            if isinstance(
                                conv.get("updated_at", conv["created_at"]), datetime
                            )
                            else datetime.fromisoformat(
                                conv.get("updated_at", conv["created_at"])
                            )
                        ),
                        is_active=conv.get("is_active", True),
                        message_count=conv.get("message_count", 0),
                        last_message=None,
                    )
                )
            except Exception:
                print("Conversation parse failed")
                continue
        return result

    # === Gestión de Mensajes ===

    async def add_message(
        self, conversation_id: str, user_id: str, message_data: MessageCreate
    ) -> MessageResponse:
        """Agregar mensaje a conversación"""
        # Simulación temporal para depuración: omitir la base de datos para debug-user.
        if user_id == "debug-user":
            import uuid

            return MessageResponse(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                role=message_data.role,
                content=message_data.content,
                language=message_data.language,
                metadata=message_data.metadata or {},
                created_at=datetime.now(timezone.utc),
                message_type="text",  # Required field
                tokens_used=0,  # Required field
                model_used="debug",  # Required field
            )

        # Guardar en base de datos (pasar parámetros individuales)
        db_message = await self.db.create_message(
            conversation_id=conversation_id,
            owner_id=user_id,
            content=message_data.content,
            role=message_data.role,
            metadata=message_data.metadata,
        )
        if not db_message:
            raise ValueError("Conversation not found")
        message_response = MessageResponse.model_validate(db_message)

        # Actualizar cache en Redis
        cache_key = self._conversation_cache_key(user_id, conversation_id)
        cached = await self.redis.get_cache(cache_key)
        if cached:
            cached_conv = CachedConversation.from_redis_format(cached)
            if cached_conv.user_id != user_id:
                raise ValueError("Conversation not found")
            cached_conv.messages.append(message_response)
            cached_conv.updated_at = datetime.now(timezone.utc)

            await self.redis.set_cache(
                cache_key, cached_conv.to_redis_format(), self.cache_ttl["conversation"]
            )

        return message_response

    async def get_conversation_messages(
        self, conversation_id: str, user_id: str, limit: int = 100
    ) -> List[MessageResponse]:
        """Obtener mensajes de conversación"""
        # Intentar cache primero
        cached = await self.redis.get_cache(
            self._conversation_cache_key(user_id, conversation_id)
        )
        if cached:
            cached_conv = CachedConversation.from_redis_format(cached)
            if cached_conv.user_id != user_id:
                return []
            return (
                cached_conv.messages[-limit:]
                if len(cached_conv.messages) > limit
                else cached_conv.messages
            )

        # Si no está en cache, buscar en DB (el método del adapter no usa limit)
        messages = await self.db.get_conversation_messages(conversation_id, user_id)
        return [MessageResponse.model_validate(msg) for msg in messages]

    # === Procesamiento de Chat ===

    async def process_chat_message(
        self, request: ChatRequest, user_id: str
    ) -> ChatResponse:
        """Procesar mensaje de chat con persistencia y traducción automática"""
        query_for_processing = request.message
        original_language = request.language

        # 3. Determinar conversación
        conversation_id = request.conversation_id
        if not conversation_id:
            # Crear nueva conversación
            conversation = await self.create_conversation(
                user_id=user_id, language=original_language
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
            metadata=request.context or {},
        )

        saved_message = await self.add_message(conversation_id, user_id, user_message)

        # 6. Obtener contexto de conversación
        context = await self._build_conversation_context(
            conversation_id, user_id, original_language
        )
        from context.conversation_prompt import bounded_history, with_conversation

        previous_messages = await self.get_conversation_messages(
            conversation_id, user_id, limit=13
        )
        history = bounded_history(
            [m for m in previous_messages if m.id != saved_message.id]
        )
        with_conversation("", history, request.context)

        # Same application service as /legal-query and the NDJSON transport.
        from main import app
        from optimization.query_cache import answer_cache_key
        from services.legal_queries import answer_query, response_text
        revision = app.state.rag_engine.get_cache_revision()
        cache_key = answer_cache_key(query_for_processing, original_language, user_id,
            request.context, history, conversation_id, revision, "query") if revision else None
        result = await answer_query(app.state, query_for_processing, original_language,
            history=history, context=request.context, cache_key=cache_key)
        translation_meta = result["metadata"].get("translation")
        assistant_message = MessageCreate(role="assistant",
            content=response_text(result["response"], original_language), language=original_language,
            metadata={"sources": result["sources"], "validation": result["validation"],
                      "translation": translation_meta, "cached": result["cached"]})

        assistant_response = await self.add_message(
            conversation_id, user_id, assistant_message
        )

        # 9. Obtener historial actualizado
        history = await self.get_conversation_messages(
            conversation_id, user_id, limit=10
        )

        return ChatResponse(
            success=True,
            conversation_id=conversation_id,
            message=assistant_response,
            conversation_history=history,
            metadata={
                "context": context.model_dump(),
                "language": original_language,
                "translation_applied": bool(
                    translation_meta and translation_meta.get("success")
                ),
                "translation": translation_meta,
            },
        )

    async def _build_conversation_context(
        self, conversation_id: str, user_id: str, language: str
    ) -> ConversationContext:
        """Construir contexto de conversación"""
        messages = await self.get_conversation_messages(
            conversation_id, user_id, limit=20
        )

        # Análisis simple del contexto (mejorar con NLP)
        all_text = " ".join([msg.content for msg in messages])

        # Detectar tópicos legales básicos
        legal_topics = [
            "contrato",
            "demanda",
            "divorcio",
            "herencia",
            "laboral",
            "penal",
            "civil",
        ]
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
            metadata={"message_count": len(messages)},
        )

    async def invalidate_conversation_cache(
        self, conversation_id: str, user_id: str
    ) -> bool:
        """Invalidar cache de conversación específica"""
        try:
            if not await self.get_conversation(conversation_id, user_id):
                return False
            return await self.redis.delete_cache(
                self._conversation_cache_key(user_id, conversation_id)
            )
        except Exception:
            print("Conversation cache invalidation failed")
            return False

    # === Utilidades ===

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Eliminar conversación"""
        # Simulación temporal para depuración: omitir la base de datos para debug-user.
        if user_id == "debug-user":
            return True

        # Eliminar de base de datos
        success = await self.db.delete_conversation(conversation_id, user_id)

        if success:
            # Eliminar de cache
            await self.redis.delete_cache(
                self._conversation_cache_key(user_id, conversation_id)
            )

        return success

    async def search_conversations(
        self, user_id: str, query: str, limit: int = 20
    ) -> List[ConversationResponse]:
        """Buscar conversaciones por contenido"""
        # Buscar en base de datos
        conversations = await self.db.search_conversations(user_id, query, limit)
        return [ConversationResponse.model_validate(conv) for conv in conversations]

    async def get_conversation_stats(
        self, conversation_id: str, user_id: str
    ) -> Dict[str, Any]:
        """Obtener estadísticas de conversación"""
        conversation = await self.get_conversation(conversation_id, user_id)
        if not conversation:
            return {}

        messages = await self.get_conversation_messages(conversation_id, user_id)

        # Las fechas heredadas sin zona seguían la convención UTC de utcnow.
        # No reinterpretar fechas con offset ni modificar la conversación original.
        created_at = conversation.created_at
        if created_at.utcoffset() is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        return {
            "conversation_id": conversation_id,
            "message_count": len(messages),
            "user_messages": len([m for m in messages if m.role == "user"]),
            "assistant_messages": len([m for m in messages if m.role == "assistant"]),
            "total_tokens": sum(m.tokens_used for m in messages),
            "languages": list(set(m.language for m in messages)),
            "duration_hours": (
                datetime.now(timezone.utc) - created_at
            ).total_seconds()
            / 3600,
            "last_activity": conversation.updated_at,
        }

    async def update_conversation(
        self, conversation_id: str, user_id: str, update_data: ConversationUpdate
    ) -> Optional[ConversationResponse]:
        if not await self.db.update_conversation(conversation_id, user_id, update_data):
            return None
        await self.redis.delete_cache(
            self._conversation_cache_key(user_id, conversation_id)
        )
        return await self.get_conversation(conversation_id, user_id)

    @staticmethod
    def _conversation_cache_key(user_id: str, conversation_id: str) -> str:
        return f"conversation:{user_id}:{conversation_id}"


# Instancia global del servicio
chat_service = ChatService()
