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

  // ── Limpiar sesión al refrescar la página ───────────────────────────────
  useEffect(() => {
    const handleBeforeUnload = () => {
      // Limpiar sesión activa en el backend antes de recargar
      if (activeSessionId) {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
        const data = new Blob([JSON.stringify({ session_token: activeSessionId })], { 
          type: 'application/json' 
        });
        
        navigator.sendBeacon(`${apiUrl}/chat/clear-session`, data);
        console.log('Session cleanup sent for:', activeSessionId);
      }
    };

    const handleVisibilityChange = () => {
      // También limpiar cuando la página se oculta (tab change, minimize)
      if (document.visibilityState === 'hidden' && activeSessionId) {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
        const data = new Blob([JSON.stringify({ session_token: activeSessionId })], { 
          type: 'application/json' 
        });
        
        navigator.sendBeacon(`${apiUrl}/chat/clear-session`, data);
        console.log('Session cleanup sent on visibility change for:', activeSessionId);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [activeSessionId]);

  // ── Crear nueva sesión en el backend ────────────────────────────────────────
  const createSession = useCallback(async (language: SupportedLanguage = 'spanish'): Promise<string> => {
    try {
      // Verificar si ya existe una sesión "Nueva consulta" sin mensajes
      const existingEmptySession = sessions.find(s => 
        s.title === 'Nueva consulta' && s.messageCount === 0
      );
      
      if (existingEmptySession) {
        console.log('Reusing existing empty session:', existingEmptySession.id);
        setActiveSessionId(existingEmptySession.id);
        return existingEmptySession.id;
      }

      const response = await apiService.createConversation(language, 'Nueva consulta', 'd1d0e0f7-1b3d-43fc-875d-b6991e6c94af');
      if (response.success && response.data) {
        const newSession = backendToSessionMeta(response.data);
        setSessions((prev) => [newSession, ...prev]);
        setActiveSessionId(newSession.id);
        console.log('Created new session:', newSession.id);
        return newSession.id;
      }
      throw new Error('Failed to create session');
    } catch (error) {
      console.error('Error creating session:', error);
      throw error;
    }
  }, [sessions]);

  // ── Cargar sesiones desde el backend al montar ─────────────────────────────
  useEffect(() => {
    const loadSessions = async () => {
      setLoading(true);
      try {
        console.log('Loading sessions from backend...');
        
        // Limpiar cualquier sesión residual al cargar
        try {
          await apiService.clearSession();
          console.log('Cleared any residual session');
        } catch (clearError) {
          console.warn('Could not clear session:', clearError);
        }
        
        const response = await apiService.listConversations(50, true);
        console.log('Sessions API response:', response);
        
        if (response.success && response.data) {
          const backendSessions = response.data.conversations;
          const sessionMetas = backendSessions.map(backendToSessionMeta);
          setSessions(sessionMetas);
          console.log('Loaded sessions:', sessionMetas);

          // Solo activar la más reciente si hay sesiones con mensajes
          const sessionsWithMessages = sessionMetas.filter(s => s.messageCount > 0);
          
          if (sessionsWithMessages.length > 0) {
            const mostRecent = [...sessionsWithMessages].sort(
              (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
            )[0];
            setActiveSessionId(mostRecent.id);
            console.log('Set active session (has messages):', mostRecent.id);
          } else {
            // No hay sesiones con mensajes, dejar activa la primera si existe
            if (sessionMetas.length > 0) {
              setActiveSessionId(sessionMetas[0].id);
              console.log('Set first session as active:', sessionMetas[0].id);
            } else {
              console.log('No sessions at all');
              setActiveSessionId(null);
            }
          }
        } else {
          console.log('No sessions found');
          setSessions([]);
          setActiveSessionId(null);
        }
      } catch (error) {
        console.error('Error loading sessions:', error);
        setSessions([]);
        setActiveSessionId(null);
      } finally {
        setLoading(false);
        setHydrated(true);
      }
    };

    loadSessions();
  }, []); // Sin dependencias para evitar loops

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
        console.log('Attempting to delete session:', id);
        const result = await apiService.deleteConversation(id);
        console.log('Delete API result:', result);
        
        setSessions((prev) => {
          const updated = prev.filter((s) => s.id !== id);
          console.log('Updated sessions after filter:', updated);

          // Si se eliminó la activa, pasar a la más reciente o crear nueva
          if (activeSessionId === id) {
            if (updated.length > 0) {
              const next = [...updated].sort(
                (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
              )[0];
              setActiveSessionId(next.id);
              console.log('Set new active session:', next.id);
            } else {
              setActiveSessionId(null);
              console.log('No sessions left, set active to null');
              // NO crear sesión automáticamente - esperar a que el usuario haga clic
            }
          }
          return updated;
        });
      } catch (error) {
        console.error('Error deleting session:', error);
        throw error;
      }
    },
    [activeSessionId, createSession]
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
