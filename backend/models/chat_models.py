"""
Modelos de datos para el sistema de chat persistente
IA Jurídica - Conversaciones con Redis + PostgreSQL
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class MessageRole(str, Enum):
    """Roles posibles en un mensaje"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageType(str, Enum):
    """Tipos de mensajes"""
    TEXT = "text"
    LEGAL_QUERY = "legal_query"
    DOCUMENT_UPLOAD = "document_upload"
    SYSTEM_NOTIFICATION = "system_notification"


class MessageBase(BaseModel):
    """Base para todos los mensajes"""
    role: MessageRole
    content: str
    language: str = "spanish"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessageCreate(MessageBase):
    """Modelo para crear mensajes"""
    conversation_id: Optional[str] = None
    message_type: MessageType = MessageType.TEXT
    tokens_used: Optional[int] = 0
    model_used: Optional[str] = None


class MessageResponse(MessageBase):
    """Modelo para respuestas de mensajes"""
    id: str
    conversation_id: str
    message_type: MessageType
    tokens_used: int
    model_used: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class ConversationBase(BaseModel):
    """Base para conversaciones"""
    title: Optional[str] = None
    language: str = "spanish"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationCreate(ConversationBase):
    """Modelo para crear conversaciones"""
    user_id: str
    initial_message: Optional[str] = None


class ConversationUpdate(BaseModel):
    """Modelo para actualizar conversaciones"""
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ConversationResponse(ConversationBase):
    """Modelo para respuestas de conversaciones"""
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    is_active: bool
    message_count: int = 0
    last_message: Optional[MessageResponse] = None
    
    class Config:
        from_attributes = True


class ChatSession(BaseModel):
    """Sesión de chat activa en Redis"""
    session_id: str
    user_id: str
    conversation_id: str
    language: str = "spanish"
    context_stack: List[str] = Field(default_factory=list)
    cultural_profile: Dict[str, Any] = Field(default_factory=dict)
    last_activity: datetime
    expires_at: datetime


class ChatRequest(BaseModel):
    """Request para endpoint de chat"""
    message: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    language: str = "spanish"
    session_token: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Response para endpoint de chat"""
    success: bool
    conversation_id: str
    session_id: str
    message: MessageResponse
    conversation_history: List[MessageResponse]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationList(BaseModel):
    """Lista de conversaciones de un usuario"""
    conversations: List[ConversationResponse]
    total_count: int
    active_count: int


class ConversationHistory(BaseModel):
    """Historial completo de una conversación"""
    conversation: ConversationResponse
    messages: List[MessageResponse]
    total_messages: int
    context_summary: Optional[Dict[str, Any]] = None


# Modelos para Redis Cache
class CachedConversation(BaseModel):
    """Conversación cacheada en Redis"""
    id: str
    user_id: str
    title: str
    language: str
    messages: List[MessageResponse]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    def to_redis_format(self) -> Dict[str, Any]:
        """Convertir a formato compatible con Redis"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "language": self.language,
            "messages": [msg.model_dump() for msg in self.messages],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_redis_format(cls, data: Dict[str, Any]) -> "CachedConversation":
        """Crear desde formato Redis"""
        messages = [
            MessageResponse(**msg) for msg in data.get("messages", [])
        ]
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            title=data["title"],
            language=data["language"],
            messages=messages,
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"])
        )


class UserSession(BaseModel):
    """Sesión de usuario en Redis"""
    session_id: str
    user_id: str
    conversation_id: Optional[str] = None
    language_preferences: Dict[str, str] = Field(default_factory=dict)
    cultural_profile: Dict[str, Any] = Field(default_factory=dict)
    last_activity: datetime
    expires_at: datetime
    is_active: bool = True
    
    def to_redis_format(self) -> Dict[str, Any]:
        """Convertir a formato compatible con Redis"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "language_preferences": self.language_preferences,
            "cultural_profile": self.cultural_profile,
            "last_activity": self.last_activity.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "is_active": self.is_active
        }
    
    @classmethod
    def from_redis_format(cls, data: Dict[str, Any]) -> "UserSession":
        """Crear desde formato Redis"""
        return cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            conversation_id=data.get("conversation_id"),
            language_preferences=data.get("language_preferences", {}),
            cultural_profile=data.get("cultural_profile", {}),
            last_activity=datetime.fromisoformat(data["last_activity"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            is_active=data.get("is_active", True)
        )


# Modelos para Context Engineering
class ConversationContext(BaseModel):
    """Contexto de una conversación"""
    conversation_id: str
    detected_legal_topic: Optional[str] = None
    urgency_level: str = "normal"
    detected_location: Optional[str] = None
    cultural_context: Optional[str] = None
    formality_level: str = "formal"
    document_references: List[str] = Field(default_factory=list)
    key_entities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContextSummary(BaseModel):
    """Resumen de contexto para cache"""
    conversation_id: str
    topic_summary: str
    key_points: List[str]
    legal_areas: List[str]
    cultural_adaptations: List[str]
    last_updated: datetime
