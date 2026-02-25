'use client';

import { useCallback, useEffect, useState } from 'react';
import type { ChatMessage, ChatSessionMeta, SupportedLanguage } from '../../../domain/legal/types';

// ─── Claves de almacenamiento ──────────────────────────────────────────────────

const SESSIONS_META_KEY = 'ia_juridica_sessions_v1';
const sessionMessagesKey = (id: string) => `ia_juridica_session_${id}_v1`;

/** Clave del chat único anterior (pre-sidebar) — se migra automáticamente */
const LEGACY_KEY = 'ia_juridica_chat_v1';

// ─── Helpers de serialización ──────────────────────────────────────────────────

function loadSessionsMeta(): ChatSessionMeta[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(SESSIONS_META_KEY);
    return raw ? (JSON.parse(raw) as ChatSessionMeta[]) : [];
  } catch {
    return [];
  }
}

function saveSessionsMeta(sessions: ChatSessionMeta[]) {
  try {
    localStorage.setItem(SESSIONS_META_KEY, JSON.stringify(sessions));
  } catch { /* storage lleno */ }
}

export function loadSessionMessages(sessionId: string): ChatMessage[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(sessionMessagesKey(sessionId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Array<ChatMessage & { timestamp: string }>;
    return parsed.map((m) => ({
      ...m,
      timestamp: new Date(m.timestamp),
      isStreaming: false,
      isLoadingFull: false,
      streamingContent: undefined,
    }));
  } catch {
    return [];
  }
}

export function saveSessionMessages(sessionId: string, messages: ChatMessage[]) {
  try {
    const stable = messages
      .filter((m) => !m.isStreaming && !m.isLoadingFull)
      .map((m) => ({
        ...m,
        timestamp: m.timestamp.toISOString(),
        streamingContent: undefined,
        content: m.content || '(Respuesta interrumpida)',
      }));
    localStorage.setItem(sessionMessagesKey(sessionId), JSON.stringify(stable));
  } catch { /* noop */ }
}

function deleteSessionMessages(sessionId: string) {
  try {
    localStorage.removeItem(sessionMessagesKey(sessionId));
  } catch { /* noop */ }
}

function generateId() {
  return `sess-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function truncate(text: string, max = 60): string {
  const clean = text.trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

// ─── Migración de datos legacy ─────────────────────────────────────────────────

function migrateLegacyChat(): ChatSessionMeta | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(LEGACY_KEY);
    if (!raw) return null;
    const msgs = JSON.parse(raw) as Array<ChatMessage & { timestamp: string }>;
    if (!msgs?.length) return null;

    const id = generateId();
    const firstUser = msgs.find((m) => m.role === 'user');
    const firstAssistant = msgs.find((m) => m.role === 'assistant');

    const meta: ChatSessionMeta = {
      id,
      title: truncate(firstUser?.content ?? 'Consulta importada'),
      preview: truncate(firstAssistant?.content ?? ''),
      language: 'spanish',
      createdAt: firstUser?.timestamp ?? new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messageCount: msgs.length,
    };

    // Mover mensajes a la nueva clave
    localStorage.setItem(sessionMessagesKey(id), raw);
    localStorage.removeItem(LEGACY_KEY);

    return meta;
  } catch {
    return null;
  }
}

// ─── Hook ──────────────────────────────────────────────────────────────────────

export function useChatSessions() {
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  // ── Cargar sesiones al montar ──────────────────────────────────────────────
  useEffect(() => {
    let loaded = loadSessionsMeta();

    // Migrar datos del chat anterior (single-thread)
    if (!loaded.length) {
      const migrated = migrateLegacyChat();
      if (migrated) {
        loaded = [migrated];
        saveSessionsMeta(loaded);
      }
    }

    setSessions(loaded);

    // Restaurar la sesión activa (la más reciente)
    if (loaded.length > 0) {
      const mostRecent = [...loaded].sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      )[0];
      setActiveSessionId(mostRecent.id);
    }

    setHydrated(true);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Crear nueva sesión ──────────────────────────────────────────────────────
  const createSession = useCallback((language: SupportedLanguage = 'spanish'): string => {
    const id = generateId();
    const now = new Date().toISOString();
    const meta: ChatSessionMeta = {
      id,
      title: 'Nueva consulta',
      preview: '',
      language,
      createdAt: now,
      updatedAt: now,
      messageCount: 0,
    };
    setSessions((prev) => {
      const updated = [meta, ...prev];
      saveSessionsMeta(updated);
      return updated;
    });
    setActiveSessionId(id);
    return id;
  }, []);

  // ── Actualizar metadata de una sesión ──────────────────────────────────────
  const updateSessionMeta = useCallback(
    (id: string, patch: Partial<Pick<ChatSessionMeta, 'title' | 'preview' | 'messageCount' | 'updatedAt' | 'language'>>) => {
      setSessions((prev) => {
        const updated = prev.map((s) =>
          s.id === id ? { ...s, ...patch, updatedAt: new Date().toISOString() } : s
        );
        saveSessionsMeta(updated);
        return updated;
      });
    },
    []
  );

  // ── Eliminar una sesión ────────────────────────────────────────────────────
  const deleteSession = useCallback(
    (id: string) => {
      deleteSessionMessages(id);
      setSessions((prev) => {
        const updated = prev.filter((s) => s.id !== id);
        saveSessionsMeta(updated);

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
    },
    [activeSessionId]
  );

  // ── Limpiar mensajes de la sesión activa (sin eliminarla) ──────────────────
  const clearActiveSession = useCallback(() => {
    if (!activeSessionId) return;
    deleteSessionMessages(activeSessionId);
    updateSessionMeta(activeSessionId, {
      title: 'Nueva consulta',
      preview: '',
      messageCount: 0,
    });
  }, [activeSessionId, updateSessionMeta]);

  // ── Eliminar todas las sesiones ────────────────────────────────────────────
  const clearAllSessions = useCallback(() => {
    setSessions((prev) => {
      for (const s of prev) deleteSessionMessages(s.id);
      saveSessionsMeta([]);
      return [];
    });
    setActiveSessionId(null);
  }, []);

  return {
    sessions,
    activeSessionId,
    hydrated,
    setActiveSessionId,
    createSession,
    updateSessionMeta,
    deleteSession,
    clearActiveSession,
    clearAllSessions,
  };
}
