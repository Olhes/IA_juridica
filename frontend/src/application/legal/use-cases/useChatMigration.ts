'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiService } from '../services/apiService';
import { loadSessionMessages, saveSessionMessages, loadSessionsMeta, saveSessionsMeta } from './useChatSessions';
import type { ChatMessage, ChatSessionMeta, SupportedLanguage } from '../../../domain/legal/types';

/**
 * Hook de migración gradual de localStorage a backend
 * Mantiene compatibilidad con localStorage mientras añade persistencia en backend
 */
export function useChatMigration() {
  const [isMigrating, setIsMigrating] = useState(false);
  const [migrationStatus, setMigrationStatus] = useState<'idle' | 'migrating' | 'completed' | 'error'>('idle');
  const [backendOnline, setBackendOnline] = useState(false);

  // ── Verificar estado del backend ─────────────────────────────────────
  const checkBackendHealth = useCallback(async () => {
    try {
      const response = await apiService.chatHealthCheck();
      setBackendOnline(response.success && response.data?.status === 'healthy');
      return response.success;
    } catch {
      setBackendOnline(false);
      return false;
    }
  }, []);

  // ── Migrar sesión individual al backend ───────────────────────────────
  const migrateSession = useCallback(async (sessionId: string) => {
    if (!backendOnline) return false;

    try {
      // Cargar mensajes desde localStorage
      const messages = loadSessionMessages(sessionId);
      if (!messages.length) return true; // Sesión vacía, no necesita migración

      // Crear conversación en backend
      const firstUserMessage = messages.find(m => m.role === 'user');
      const response = await apiService.createConversation(
        firstUserMessage?.content?.includes('quechua') ? 'quechua' : 'spanish',
        `Migrado: ${firstUserMessage?.content?.slice(0, 30) || 'Sin título'}`,
        'demo-user'
      );

      if (!response.success || !response.data) {
        console.error('Error creando conversación en backend:', response.error);
        return false;
      }

      const conversation = response.data;
      let migratedMessages = 0;

      // Migrar mensajes uno por uno
      for (const message of messages) {
        if (message.role === 'user') {
          const msgResponse = await apiService.sendChatMessage(
            message.content,
            conversation.id,
            message.content.includes('quechua') ? 'quechua' : 'spanish'
          );

          if (msgResponse.success) {
            migratedMessages++;
          }
        }
        // Los mensajes de asistente se generan automáticamente
      }

      console.log(`Sesión ${sessionId} migrada: ${migratedMessages} mensajes`);
      return true;
    } catch (error) {
      console.error(`Error migrando sesión ${sessionId}:`, error);
      return false;
    }
  }, [backendOnline]);

  // ── Migrar todas las sesiones ─────────────────────────────────────────
  const migrateAllSessions = useCallback(async () => {
    if (!backendOnline) {
      setMigrationStatus('error');
      return;
    }

    setIsMigrating(true);
    setMigrationStatus('migrating');

    try {
      const sessions = loadSessionsMeta();
      let migratedCount = 0;
      let errorCount = 0;

      for (const session of sessions) {
        const success = await migrateSession(session.id);
        if (success) {
          migratedCount++;
          // Opcional: eliminar de localStorage después de migrar
          // localStorage.removeItem(`ia_juridica_session_${session.id}_v1`);
        } else {
          errorCount++;
        }
      }

      console.log(`Migración completada: ${migratedCount} exitosas, ${errorCount} errores`);
      setMigrationStatus('completed');
    } catch (error) {
      console.error('Error en migración masiva:', error);
      setMigrationStatus('error');
    } finally {
      setIsMigrating(false);
    }
  }, [backendOnline, migrateSession]);

  // ── Sincronizar sesión activa con backend ───────────────────────────
  const syncActiveSession = useCallback(async (sessionId: string, messages: ChatMessage[]) => {
    if (!backendOnline || !sessionId) return;

    try {
      // Buscar si ya existe en backend
      const sessions = await apiService.listConversations(100);
      if (!sessions.success || !sessions.data) return;

      const existingSession = sessions.data.conversations.find(
        (conv: any) => conv.metadata?.localStorageId === sessionId
      );

      if (existingSession) {
        // Sincronizar mensajes nuevos
        const response = await apiService.getConversation(existingSession.id);
        if (response.success && response.data) {
          const backendMessages = response.data.messages;
          const localMessages = messages;
          
          // Enviar mensajes que no están en backend
          for (const localMsg of localMessages) {
            const existsInBackend = backendMessages.some(
              (backendMsg: any) => backendMsg.content === localMsg.content && 
                                   backendMsg.role === localMsg.role &&
                                   Math.abs(new Date(backendMsg.created_at).getTime() - localMsg.timestamp.getTime()) < 5000
            );

            if (!existsInBackend && localMsg.role === 'user') {
              await apiService.sendChatMessage(
                localMsg.content,
                existingSession.id,
                localMsg.content.includes('quechua') ? 'quechua' : 'spanish'
              );
            }
          }
        }
      }
    } catch (error) {
      console.error('Error sincronizando sesión activa:', error);
    }
  }, [backendOnline]);

  // ── Health check periódico ─────────────────────────────────────────────
  useEffect(() => {
    checkBackendHealth();
    const interval = setInterval(checkBackendHealth, 30000); // 30 segundos
    return () => clearInterval(interval);
  }, [checkBackendHealth]);

  return {
    // Estado
    isMigrating,
    migrationStatus,
    backendOnline,
    
    // Acciones
    checkBackendHealth,
    migrateSession,
    migrateAllSessions,
    syncActiveSession
  };
}
