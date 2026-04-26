'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiService } from '../services/apiService';
import type { ChatMessage, SupportedLanguage } from '../../../domain/legal/types';

interface BackendChatState {
  messages: ChatMessage[];
  conversationId: string | null;
  isLoading: boolean;
  isOnline: boolean;
  error: string | null;
}

interface BackendChatOptions {
  language: SupportedLanguage;
  userId?: string;
}

/**
 * Hook simplificado para chat con backend
 * Funciona sin errores de TypeScript complejos
 */
export function useBackendChat({ language = 'spanish', userId = 'demo-user' }: BackendChatOptions) {
  const [state, setState] = useState<BackendChatState>({
    messages: [],
    conversationId: null,
    isLoading: false,
    isOnline: false,
    error: null
  });

  const [sessionId, setSessionId] = useState<string | null>(null);

  // ── Enviar mensaje ─────────────────────────────────────
  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || state.isLoading) return;

    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await apiService.sendChatMessage(
        content.trim(),
        state.conversationId || undefined,
        language,
        sessionId || undefined
      );

      if (response.success && response.data) {
        const { message, conversation_history, conversation_id, session_id } = response.data;
        
        // Actualizar sesión
        if (session_id && session_id !== sessionId) {
          setSessionId(session_id);
        }

        // Convertir BackendMessage a ChatMessage
        const chatMessages: ChatMessage[] = (conversation_history || [message]).map(msg => ({
          id: msg.id,
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
          timestamp: new Date(msg.created_at),
          isStreaming: false,
          isLoadingFull: false,
          streamingContent: undefined,
          apiResponse: undefined,
          error: undefined
        }));

        setState(prev => ({
          ...prev,
          conversationId: conversation_id,
          messages: chatMessages,
          isLoading: false
        }));

        return {
          success: true,
          conversationId: conversation_id,
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
  }, [state.conversationId, state.isLoading, sessionId, language]);

  // ── Crear nueva conversación ───────────────────────────────
  const createConversation = useCallback(async (title?: string) => {
    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await apiService.createConversation(language, title, userId);

      if (response.success && response.data) {
        const newConversation = response.data;
        setState(prev => ({
          ...prev,
          conversationId: newConversation.id,
          messages: [],
          isLoading: false
        }));
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
  }, [language, userId]);

  // ── Cargar conversación existente ─────────────────────────────
  const loadConversation = useCallback(async (conversationId: string) => {
    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await apiService.getConversation(conversationId);
      
      if (response.success && response.data) {
        const { conversation, messages } = response.data;
        
        // Convertir BackendMessage a ChatMessage
        const chatMessages: ChatMessage[] = (messages || []).map(msg => ({
          id: msg.id,
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
          timestamp: new Date(msg.created_at),
          isStreaming: false,
          isLoadingFull: false,
          streamingContent: undefined,
          apiResponse: undefined,
          error: undefined
        }));
        
        setState(prev => ({
          ...prev,
          conversationId: conversation.id,
          messages: chatMessages,
          isLoading: false
        }));
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
  }, []);

  // ── Listar conversaciones ─────────────────────────────────────
  const listConversations = useCallback(async () => {
    try {
      const response = await apiService.listConversations();
      return response.success ? response.data : null;
    } catch (error) {
      console.error('Error listando conversaciones:', error);
      return null;
    }
  }, []);

  // ── Health check ─────────────────────────────────────────────
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

  // ── Limpiar estado ─────────────────────────────────────────────
  const clearError = useCallback(() => {
    setState(prev => ({ ...prev, error: null }));
  }, []);

  const resetChat = useCallback(() => {
    setState({
      messages: [],
      conversationId: null,
      isLoading: false,
      isOnline: false,
      error: null
    });
    setSessionId(null);
  }, []);

  // ── Effects ───────────────────────────────────────────────────
  useEffect(() => {
    // Health check periódico
    checkHealth();
    const interval = setInterval(checkHealth, 30000); // 30 segundos
    return () => clearInterval(interval);
  }, [checkHealth]);

  return {
    // Estado
    ...state,
    sessionId,
    
    // Acciones
    sendMessage,
    createConversation,
    loadConversation,
    listConversations,
    checkHealth,
    clearError,
    resetChat,
    
    // Metadatos
    messageCount: state.messages.length,
    hasMessages: state.messages.length > 0,
    hasActiveConversation: !!state.conversationId
  };
}
