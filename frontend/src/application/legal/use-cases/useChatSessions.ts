'use client';

import { useCallback, useEffect, useState } from 'react';
import type { ChatMessage, ChatSessionMeta, SupportedLanguage } from '../../../domain/legal/types';
import { apiService, type Conversation as BackendConversation, type Message as BackendMessage } from '../services/apiService';

// ─── Helpers de conversión ──────────────────────────────────────────────────

function backendToSessionMeta(conv: BackendConversation): ChatSessionMeta {
  return {
    id: conv.id,
    title: conv.title || 'Conversación',
    preview: '', // Se actualizará con el primer mensaje
    language: conv.language as SupportedLanguage,
    createdAt: conv.created_at,
    updatedAt: conv.updated_at || conv.created_at,
    messageCount: 0, // Se actualizará al cargar mensajes
  };
}

function backendToChatMessage(msg: BackendMessage): ChatMessage {
  return {
    id: msg.id,
    role: msg.role as 'user' | 'assistant',
    content: msg.content,
    timestamp: new Date(msg.created_at),
    metadata: msg.metadata,
  };
}

function truncate(text: string, max = 60): string {
  const clean = text.trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

// ─── Hook ──────────────────────────────────────────────────────────────────────

export function useChatSessions() {
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [loading, setLoading] = useState(false);

  // ── Cargar sesiones desde el backend al montar ─────────────────────────────
  useEffect(() => {
    const loadSessions = async () => {
      setLoading(true);
      try {
        const response = await apiService.listConversations(50, true);
        if (response.success && response.data) {
          const backendSessions = response.data.conversations;
          const sessionMetas = backendSessions.map(backendToSessionMeta);
          setSessions(sessionMetas);

          // Restaurar la sesión activa (la más reciente)
          if (sessionMetas.length > 0) {
            const mostRecent = [...sessionMetas].sort(
              (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
            )[0];
            setActiveSessionId(mostRecent.id);
          }
        }
      } catch (error) {
        console.error('Error loading sessions:', error);
      } finally {
        setLoading(false);
        setHydrated(true);
      }
    };

    loadSessions();
  }, []);

  // ── Crear nueva sesión en el backend ────────────────────────────────────────
  const createSession = useCallback(async (language: SupportedLanguage = 'spanish'): Promise<string> => {
    try {
      const response = await apiService.createConversation(language, 'Nueva consulta', 'd1d0e0f7-1b3d-43fc-875d-b6991e6c94af');
      if (response.success && response.data) {
        const newSession = backendToSessionMeta(response.data);
        setSessions((prev) => [newSession, ...prev]);
        setActiveSessionId(newSession.id);
        return newSession.id;
      }
      throw new Error('Failed to create session');
    } catch (error) {
      console.error('Error creating session:', error);
      throw error;
    }
  }, []);

  // ── Actualizar metadata de una sesión ──────────────────────────────────────
  const updateSessionMeta = useCallback(
    async (id: string, patch: Partial<Pick<ChatSessionMeta, 'title' | 'preview' | 'messageCount' | 'updatedAt' | 'language'>>) => {
      // Actualizar localmente primero para respuesta inmediata
      setSessions((prev) => {
        const updated = prev.map((s) =>
          s.id === id ? { ...s, ...patch, updatedAt: new Date().toISOString() } : s
        );
        return updated;
      });

      // Luego actualizar en el backend
      try {
        // Filtrar valores nulos/undefined
        const updateData: any = {};
        if (patch.title !== undefined) updateData.title = patch.title;
        if (patch.preview !== undefined || patch.messageCount !== undefined) {
          updateData.metadata = { 
            preview: patch.preview, 
            messageCount: patch.messageCount 
          };
        }
        
        await apiService.updateConversation(id, updateData);
      } catch (error) {
        console.error('Error updating session meta:', error);
      }
    },
    []
  );

  // ── Eliminar una sesión del backend ───────────────────────────────────────────
  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await apiService.deleteConversation(id);
        setSessions((prev) => {
          const updated = prev.filter((s) => s.id !== id);

          // Si se eliminó la activa, pasar a la más reciente
          if (activeSessionId === id) {
            if (updated.length > 0) {
              const next = [...updated].sort(
                (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
              )[0];
              setActiveSessionId(next.id);
            } else {
              setActiveSessionId(null);
            }
          }
          return updated;
        });
      } catch (error) {
        console.error('Error deleting session:', error);
        throw error;
      }
    },
    [activeSessionId]
  );

  // ── Limpiar mensajes de la sesión activa (sin eliminarla) ──────────────────
  const clearActiveSession = useCallback(async () => {
    if (!activeSessionId) return;
    try {
      // Actualizar título en el backend
      await apiService.updateConversation(activeSessionId, {
        title: 'Nueva consulta',
        metadata: { messageCount: 0 },
      });
      updateSessionMeta(activeSessionId, {
        title: 'Nueva consulta',
        preview: '',
        messageCount: 0,
      });
    } catch (error) {
      console.error('Error clearing session:', error);
    }
  }, [activeSessionId, updateSessionMeta]);

  // ── Eliminar todas las sesiones ────────────────────────────────────────────
  const clearAllSessions = useCallback(async () => {
    try {
      // Eliminar cada sesión del backend
      for (const session of sessions) {
        await apiService.deleteConversation(session.id);
      }
      setSessions([]);
      setActiveSessionId(null);
    } catch (error) {
      console.error('Error clearing all sessions:', error);
    }
  }, [sessions]);

  // ── Recargar sesiones desde el backend ───────────────────────────────────────
  const reloadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiService.listConversations(50, true);
      if (response.success && response.data) {
        const backendSessions = response.data.conversations;
        const sessionMetas = backendSessions.map(backendToSessionMeta);
        setSessions(sessionMetas);
      }
    } catch (error) {
      console.error('Error reloading sessions:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    sessions,
    activeSessionId,
    hydrated,
    loading,
    setActiveSessionId,
    createSession,
    updateSessionMeta,
    deleteSession,
    clearActiveSession,
    clearAllSessions,
    reloadSessions,
  };
}
