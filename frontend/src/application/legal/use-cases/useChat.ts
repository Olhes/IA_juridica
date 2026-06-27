'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatMessage, LegalQueryApiResponse, SupportedLanguage } from '../../../domain/legal/types';
import { apiService, type Message as BackendMessage } from '../services/apiService';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const STREAM_FLUSH_MS = 60; // Flush de contenido en streaming cada 60ms para evitar demasiados renders, config. recomendada

let msgCounter = 0;
function newId() {
  return `msg-${Date.now()}-${msgCounter++}`;
}

interface UseChatOptions {
  sessionId: string | null;
  language: SupportedLanguage;
  /** Llamado cuando el contenido de la sesión cambia (para actualizar sidebar) */
  onSessionUpdated?: (patch: { title?: string; preview?: string; messageCount?: number }) => void;
}

/**
 * Core chat hook con persistencia en backend (PostgreSQL + Redis).
 *
 * Flujo por mensaje:
 *  1. POST /legal-query-stream → stream de chunks NDJSON
 *  2. En el mismo stream llega evento final con validación/fuentes/metadata
 *  3. Persistencia en backend via chat_service
 */
export function useChat({ sessionId, language, onSessionUpdated }: UseChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isOnline, setIsOnline] = useState<boolean | undefined>(undefined);
  const [downloadingPdfId, setDownloadingPdfId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ── Cargar mensajes desde el backend cuando cambia la sesión activa ────────
  useEffect(() => {
    const loadMessages = async () => {
      if (!sessionId) {
        setMessages([]);
        setHydrated(true);
        return;
      }

      try {
        const response = await apiService.getConversation(sessionId);
        if (response.success && response.data) {
          const backendMessages = response.data.messages;
          const chatMessages = backendMessages.map((msg: BackendMessage) => ({
            id: msg.id,
            role: msg.role as 'user' | 'assistant',
            content: msg.content,
            timestamp: new Date(msg.created_at),
            metadata: msg.metadata,
          }));
          setMessages(chatMessages);
        }
      } catch (error) {
        console.error('Error loading messages:', error);
        setMessages([]);
      } finally {
        setHydrated(true);
      }
    };

    loadMessages();
  }, [sessionId]);

  // ─── Helpers ───────────────────────────────────────────────────────────────

  const updateMessage = useCallback(
    (id: string, patch: Partial<ChatMessage>) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, ...patch } : m))
      );
    },
    []
  );

  const pushMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const resolveFinalText = useCallback(
    (payload: LegalQueryApiResponse, fallback: string): string => {
      return language === 'quechua'
        ? payload.response?.respuesta_quechua || fallback
        : payload.response?.respuesta_espanol || fallback;
    },
    [language]
  );

  // ─── Health check ──────────────────────────────────────────────────────────

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(4000) });
      const data = (await res.json()) as { status?: string };
      setIsOnline(data.status === 'healthy');
    } catch {
      setIsOnline(false);
    }
  }, []);

  // ─── Send query ────────────────────────────────────────────────────────────

  const sendQuery = useCallback(
    async (query: string) => {
      if (isLoading || !query.trim() || !sessionId) return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsLoading(true);

      // No validar sesión aquí para evitar error 404
      // sessionId es conversation_id, no session_id de Redis

      // Mensaje del usuario
      const userMsg: ChatMessage = {
        id: newId(),
        role: 'user',
        content: query.trim(),
        timestamp: new Date(),
      };
      pushMessage(userMsg);

      // Placeholder del asistente
      const assistantId = newId();
      pushMessage({
        id: assistantId,
        role: 'assistant',
        content: '',
        streamingContent: '',
        isStreaming: true,
        isLoadingFull: true,
        timestamp: new Date(),
      });

      // Notificar al sidebar (título = primer mensaje del usuario)
      setMessages((prev) => {
        const userCount = prev.filter((m) => m.role === 'user').length;
        if (userCount === 0) {
          onSessionUpdated?.({ title: query.trim().slice(0, 60) });
        }
        return prev;
      });

      // ── Stream + payload final (NDJSON) ───────────────────────────────
      let streamedText = '';
      let gotFinalPayload = false;
      let finalPayload: LegalQueryApiResponse | null = null;
      try {
        // Intentar obtener conversation_id del backend si existe
        let conversationId = sessionId;
        let userId = 'd1d0e0f7-1b3d-43fc-875d-b6991e6c94af';

        const streamRes = await fetch(`${API_BASE}/legal-query-stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: query.trim(),
            language,
            conversation_id: conversationId,
            user_id: userId
          }),
          signal: controller.signal,
        });

        if (!streamRes.ok || !streamRes.body) throw new Error('Error de conexión');

        const reader = streamRes.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let lastFlushAt = 0;

        const flushStreaming = (force = false) => {
          const now = performance.now();
          if (!force && now - lastFlushAt < STREAM_FLUSH_MS) return;
          lastFlushAt = now;
          updateMessage(assistantId, { streamingContent: streamedText });
        };

        const processLine = (line: string) => {
          if (!line.trim()) return;
          const event = JSON.parse(line) as {
            type?: 'chunk' | 'final' | 'error';
            delta?: string;
            data?: LegalQueryApiResponse;
            error?: string;
          };

          if (event.type === 'chunk') {
            const delta = typeof event.delta === 'string' ? event.delta : '';
            if (!delta) return;
            streamedText += delta;
            flushStreaming();
            return;
          }

          if (event.type === 'final' && event.data) {
            gotFinalPayload = true;
            finalPayload = event.data;
            const finalText = resolveFinalText(event.data, streamedText);
            streamedText = finalText;
            updateMessage(assistantId, {
              isStreaming: false,
              streamingContent: undefined,
              content: finalText,
              apiResponse: event.data,
              isLoadingFull: false,
            });
            onSessionUpdated?.({ preview: finalText.slice(0, 80) });
            return;
          }

          if (event.type === 'error') {
            throw new Error(event.error || 'Error procesando respuesta en streaming.');
          }
        };

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let newlineIndex = buffer.indexOf('\n');
          while (newlineIndex !== -1) {
            const line = buffer.slice(0, newlineIndex);
            buffer = buffer.slice(newlineIndex + 1);
            processLine(line);
            newlineIndex = buffer.indexOf('\n');
          }
        }

        buffer += decoder.decode();
        if (buffer.trim()) {
          processLine(buffer.trim());
        }

        if (!gotFinalPayload) {
          flushStreaming(true);
        }

        if (!gotFinalPayload) {
          updateMessage(assistantId, {
            isStreaming: false,
            content: streamedText,
            streamingContent: undefined,
            isLoadingFull: false,
          });
        }
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          const partial = streamedText || '(Respuesta interrumpida)';
          updateMessage(assistantId, {
            isStreaming: false,
            isLoadingFull: false,
            content: partial,
            streamingContent: undefined,
          });
          setIsLoading(false);
          return;
        }

        // Manejar error de conversación no encontrada (Redis reiniciado)
        const errorStr = (err as Error).toString().toLowerCase();
        if (errorStr.includes('404') || errorStr.includes('not found') || errorStr.includes('conversation')) {
          console.warn('Conversation not found, clearing state');
          updateMessage(assistantId, {
            isStreaming: false,
            isLoadingFull: false,
            content: 'La conversación ya no está disponible. Por favor, inicia una nueva consulta.',
            streamingContent: undefined,
          });
          // Limpiar estado local
          setMessages([]);
          onSessionUpdated?.({ title: 'Nueva consulta', preview: '', messageCount: 0 });
        } else {
          updateMessage(assistantId, {
            isStreaming: false,
            isLoadingFull: false,
            content: streamedText || 'No se pudo completar la respuesta. Intenta nuevamente.',
            streamingContent: undefined,
          });
        }
      }

      // Actualizar conteo de mensajes en el sidebar
      setMessages((prev) => {
        onSessionUpdated?.({ messageCount: prev.length });
        return prev;
      });

      // Nota: Los mensajes se persisten automáticamente en el backend
      // via el endpoint /legal-query-stream cuando se envía conversation_id

      setIsLoading(false);
    },
    [isLoading, language, sessionId, pushMessage, updateMessage, onSessionUpdated, resolveFinalText]
  );

  // ─── Abort ─────────────────────────────────────────────────────────────────

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
  }, []);

  // ─── PDF Download ──────────────────────────────────────────────────────────

  const downloadPdf = useCallback(async (msg: ChatMessage) => {
    if (!msg.apiResponse) return;
    setDownloadingPdfId(msg.id);
    try {
      const res = await fetch(`${API_BASE}/generate-pdf-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: msg.apiResponse.query,
          response: msg.apiResponse.response,
        }),
      });
      if (res.ok && res.headers.get('content-type')?.includes('application/pdf')) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `informe-legal-${Date.now()}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch { /* noop */ }
    finally { setDownloadingPdfId(null); }
  }, []);

  // ─── Clear current session ─────────────────────────────────────────────────

  const clearChat = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setIsLoading(false);
    // Los mensajes se limpian en el backend via useChatSessions.clearActiveSession
    onSessionUpdated?.({ title: 'Nueva consulta', preview: '', messageCount: 0 });
  }, [onSessionUpdated]);

  return {
    messages,
    isLoading,
    isOnline,
    downloadingPdfId,
    sendQuery,
    abort,
    downloadPdf,
    clearChat,
    checkHealth,
  };
}
