'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiService } from '../services/apiService';
import type { ChatMessage, ChatSessionMeta, SupportedLanguage } from '../../../domain/legal/types';
import type { Conversation as BackendConversation, Message as BackendMessage } from '../services/apiService';

interface UsePersistentChatOptions {
  conversationId?: string;
  language: SupportedLanguage;
  userId?: string;
  onConversationUpdated?: (conversation: BackendConversation) => void;
}

function mapBackendMessageToChatMessage(msg: any): ChatMessage {
  return {
    id: msg.id,
    role: msg.role as 'user' | 'assistant',
    content: msg.content,
    timestamp: msg.created_at ? new Date(msg.created_at) : new Date(),
    tokens: 0,
    metadata: msg.metadata || {},
    isStreaming: false,
    isLoadingFull: false,
    streamingContent: ''
  };
}

interface ChatState {
  messages: ChatMessage[];
  conversation: BackendConversation | null;
  isLoading: boolean;
  isOnline: boolean;
  error: string | null;
}

/**
 * Hook para chat persistente con backend (Redis + PostgreSQL)
 * Reemplaza localStorage por llamadas API reales
 */
export function usePersistentChat({
  conversationId,
  language = 'spanish',
  userId = 'd1d0e0f7-1b3d-43fc-875d-b6991e6c94af',
  onConversationUpdated
}: UsePersistentChatOptions) {
  const [state, setState] = useState<ChatState>({
    messages: [],
    conversation: null,
    isLoading: false,
    isOnline: false,
    error: null
  });

  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  // ── Cargar conversación ─────────────────────────────────────────────
  const loadConversation = useCallback(async () => {
    if (!conversationId) {
      setState(prev => ({ ...prev, conversation: null, messages: [] }));
      return;
    }

    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await apiService.getConversation(conversationId);
      
      if (response.success && response.data) {
        const { conversation, messages } = response.data;
        setState(prev => ({
          ...prev,
          conversation,
          messages: (messages as BackendMessage[] || []).map(m => mapBackendMessageToChatMessage(m as any)),
          isLoading: false
        }));
        onConversationUpdated?.(conversation);
      } else {
        setState(prev => ({
          ...prev,
          error: response.error || 'Error cargando conversación',
          isLoading: false
        }));
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Error desconocido',
        isLoading: false
      }));
    }
  }, [conversationId, onConversationUpdated]);

  // ── Enviar mensaje ─────────────────────────────────────────────────
  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || state.isLoading) return;

    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await apiService.sendChatMessage(
        content.trim(),
        conversationId,
        language,
        currentSessionId || undefined
      );

      if (response.success && response.data) {
        const { message, conversation_history, conversation_id, session_id } = response.data;
        
        // Actualizar sesión
        if (session_id && session_id !== currentSessionId) {
          setCurrentSessionId(session_id);
        }

        // Si es una nueva conversación, actualizar el ID
        const finalConversationId = conversation_id || conversationId;
        
        setState(prev => ({
          ...prev,
          messages: (conversation_history as BackendMessage[] || []).map(m => mapBackendMessageToChatMessage(m as any)),
          isLoading: false
        }));

        // Notificar actualización solo si tenemos conversación cargada
        if (state.conversation) {
          onConversationUpdated?.(state.conversation);
        }

        return {
          success: true,
          conversationId: finalConversationId,
          sessionId: session_id,
          message
        };
      } else {
        setState(prev => ({
          ...prev,
          error: response.error || 'Error enviando mensaje',
          isLoading: false
        }));
        return { success: false, error: response.error };
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Error desconocido';
      setState(prev => ({
        ...prev,
        error: errorMessage,
        isLoading: false
      }));
      return { success: false, error: errorMessage };
    }
  }, [conversationId, language, currentSessionId, state.isLoading, onConversationUpdated]);

  // ── Continuar conversación existente ───────────────────────────────
  const continueConversation = useCallback(async (content: string) => {
    if (!conversationId || !content.trim() || state.isLoading) return;

    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await apiService.continueConversation(conversationId, content);

      if (response.success) {
        // Recargar conversación para obtener mensajes actualizados
        await loadConversation();
      } else {
        setState(prev => ({
          ...prev,
          error: response.error || 'Error continuando conversación',
          isLoading: false
        }));
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Error desconocido',
        isLoading: false
      }));
    }
  }, [conversationId, state.isLoading, loadConversation]);

  // ── Crear nueva conversación ───────────────────────────────────────
  const createNewConversation = useCallback(async (title?: string) => {
    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await apiService.createConversation(language, title, userId);

      if (response.success && response.data) {
        const newConversation = response.data;
        setState(prev => ({
          ...prev,
          conversation: newConversation,
          messages: [],
          isLoading: false
        }));
        onConversationUpdated?.(newConversation);
        return newConversation;
      } else {
        setState(prev => ({
          ...prev,
          error: response.error || 'Error creando conversación',
          isLoading: false
        }));
        return null;
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Error desconocido',
        isLoading: false
      }));
      return null;
    }
  }, [language, userId, onConversationUpdated]);

  // ── Health check ───────────────────────────────────────────────────
  const checkHealth = useCallback(async () => {
    try {
      const response = await apiService.chatHealthCheck();
      setState(prev => ({
        ...prev,
        isOnline: response.success && response.data?.status === 'healthy'
      }));
    } catch {
      setState(prev => ({ ...prev, isOnline: false }));
    }
  }, []);

  // ── Limpiar estado ─────────────────────────────────────────────────
  const clearError = useCallback(() => {
    setState(prev => ({ ...prev, error: null }));
  }, []);

  const resetChat = useCallback(() => {
    setState({
      messages: [],
      conversation: null,
      isLoading: false,
      isOnline: false,
      error: null
    });
    setCurrentSessionId(null);
  }, []);

  // ── Effects ───────────────────────────────────────────────────────
  useEffect(() => {
    loadConversation();
  }, [loadConversation]);

  useEffect(() => {
    // Health check periódico
    checkHealth();
    const interval = setInterval(checkHealth, 30000); // 30 segundos
    return () => clearInterval(interval);
  }, [checkHealth]);

  return {
    // Estado
    ...state,
    
    // Acciones
    sendMessage,
    continueConversation,
    createNewConversation,
    loadConversation,
    checkHealth,
    clearError,
    resetChat,
    
    // Metadatos
    currentSessionId,
    conversationId: state.conversation?.id || conversationId,
    messageCount: state.messages.length,
    hasMessages: state.messages.length > 0
  };
}
