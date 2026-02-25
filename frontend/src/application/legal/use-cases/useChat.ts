'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatMessage, LegalQueryApiResponse, SupportedLanguage } from '../../../domain/legal/types';
import { loadSessionMessages, saveSessionMessages } from './useChatSessions';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

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
 * Core chat hook con persistencia por sesión.
 *
 * Flujo por mensaje:
 *  1. POST /legal-query-stream → stream texto en la burbuja del asistente
 *  2. POST /legal-query        → validación, fuentes y campos estructurados
 *  3. Merge + guardado en localStorage bajo la clave de la sesión
 */
export function useChat({ sessionId, language, onSessionUpdated }: UseChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isOnline, setIsOnline] = useState<boolean | undefined>(undefined);
  const [downloadingPdfId, setDownloadingPdfId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ── Cargar mensajes cuando cambia la sesión activa ────────────────────────
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      setHydrated(true);
      return;
    }
    const saved = loadSessionMessages(sessionId);
    setMessages(saved);
    setHydrated(true);
  }, [sessionId]);

  // ── Persistir cambios (solo post-hidratación y sin streaming) ─────────────
  useEffect(() => {
    if (!hydrated || !sessionId) return;
    if (messages.some((m) => m.isStreaming || m.isLoadingFull)) return;
    saveSessionMessages(sessionId, messages);
  }, [messages, hydrated, sessionId]);

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

      // ── 1. Stream ──────────────────────────────────────────────────────
      let streamedText = '';
      try {
        const streamRes = await fetch(`${API_BASE}/legal-query-stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: query.trim(), language }),
          signal: controller.signal,
        });

        if (!streamRes.ok || !streamRes.body) throw new Error('Error de conexión');

        const reader = streamRes.body.getReader();
        const decoder = new TextDecoder();
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          streamedText += decoder.decode(value, { stream: true });
          updateMessage(assistantId, { streamingContent: streamedText });
        }
        streamedText += decoder.decode();
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
      }

      updateMessage(assistantId, {
        isStreaming: false,
        content: streamedText,
        streamingContent: undefined,
      });

      // ── 2. Validación completa ─────────────────────────────────────────
      try {
        const fullRes = await fetch(`${API_BASE}/legal-query`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: query.trim(), language }),
          signal: controller.signal,
        });

        if (fullRes.ok) {
          const data = (await fullRes.json()) as LegalQueryApiResponse;
          const finalText =
            language === 'quechua'
              ? data.response?.respuesta_quechua || streamedText
              : data.response?.respuesta_espanol || streamedText;

          updateMessage(assistantId, {
            content: finalText,
            apiResponse: data,
            isLoadingFull: false,
          });

          // Actualizar preview del sidebar con la respuesta del asistente
          onSessionUpdated?.({ preview: finalText.slice(0, 80) });
        } else {
          updateMessage(assistantId, { isLoadingFull: false });
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') { /* no crítico */ }
        updateMessage(assistantId, { isLoadingFull: false });
      }

      // Actualizar conteo de mensajes en el sidebar
      setMessages((prev) => {
        onSessionUpdated?.({ messageCount: prev.length });
        return prev;
      });

      setIsLoading(false);
    },
    [isLoading, language, sessionId, pushMessage, updateMessage, onSessionUpdated]
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
    if (sessionId) saveSessionMessages(sessionId, []);
    onSessionUpdated?.({ title: 'Nueva consulta', preview: '', messageCount: 0 });
  }, [sessionId, onSessionUpdated]);

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
