'use client';

import { useCallback, useEffect, useState } from 'react';
import type { ChatSessionMeta, SupportedLanguage } from '../../../domain/legal/types';
import { apiService } from '../services/apiService';
import { loadChatSessions, sessionsAfterLoad } from './chatSessionLoad';
import { backendToSessionMeta } from './chatSessionMeta';

// ─── Hook ──────────────────────────────────────────────────────────────────────

export function useChatSessions() {
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sessionsLoadError, setSessionsLoadError] = useState<string | null>(null);

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

      const response = await apiService.createConversation(language, 'Nueva consulta');
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

  const reloadSessions = useCallback(async () => {
    setLoading(true);
    try {
      await apiService.initializeSession();
    } catch {
      setSessionsLoadError('No se pudo iniciar la sesión anónima.');
      setLoading(false);
      setHydrated(true);
      return;
    }
    const result = await loadChatSessions(
      apiService.listConversations.bind(apiService),
      backendToSessionMeta
    );

    if (result.success) {
      setSessions((current) => sessionsAfterLoad(current, result));
      setSessionsLoadError(null);
    } else {
      setSessionsLoadError(result.error);
      console.warn('Unable to load conversations:', result.error);
    }

    setLoading(false);
    setHydrated(true);
  }, []);

  // ── Cargar sesiones desde el backend al montar ─────────────────────────────
  useEffect(() => {
    void reloadSessions();
  }, [reloadSessions]);

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

  return {
    sessions,
    activeSessionId,
    hydrated,
    loading,
    sessionsLoadError,
    setActiveSessionId,
    createSession,
    updateSessionMeta,
    deleteSession,
    clearActiveSession,
    clearAllSessions,
    reloadSessions,
  };
}
