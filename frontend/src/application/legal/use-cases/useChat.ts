'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  ChatMessage,
  LegalQueryApiResponse,
  PipelineStage,
  StreamErrorCode,
  SupportedLanguage,
} from '../../../domain/legal/types';
import { apiService, type Message as BackendMessage } from '../services/apiService';
import {
  createParserState,
  finishStream,
  pushChunk,
  summarise,
  type StreamSummary,
  type TimedEvent,
} from '../stream/ndjsonParser';
import { buildStreamTelemetry, sendStreamTelemetry, type StreamOutcome } from '../stream/telemetry';

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
 * Hook central del chat con persistencia en el backend (PostgreSQL + Redis).
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
  const epochRef = useRef(0);
  const loadVersionRef = useRef(0);

  // ── Cargar mensajes desde el backend cuando cambia la sesión activa ────────
  useEffect(() => {
    epochRef.current++;
    const version = ++loadVersionRef.current;
    abortRef.current?.abort();
    abortRef.current = null;
    setIsLoading(false);
    setMessages([]);
    let active = true;
    const loadMessages = async () => {
      if (!sessionId) {
        setMessages([]);
        setHydrated(true);
        return;
      }

      try {
        const response = await apiService.getConversation(sessionId);
        if (!active || version !== loadVersionRef.current) return;
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
        if (!active || version !== loadVersionRef.current) return;
        console.error('Error loading messages:', error);
        setMessages([]);
      } finally {
        if (active && version === loadVersionRef.current) setHydrated(true);
      }
    };

    loadMessages();
    return () => {
      active = false;
      epochRef.current++;
      abortRef.current?.abort();
    };
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

  // ─── Comprobación de estado ────────────────────────────────────────────────

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, {
        credentials: 'include',
        signal: AbortSignal.timeout(4000),
      });
      const data = (await res.json()) as { status?: string };
      setIsOnline(data.status === 'healthy');
    } catch {
      setIsOnline(false);
    }
  }, []);

  // ─── Send query ────────────────────────────────────────────────────────────

  const sendQuery = useCallback(
    async (query: string) => {
      if (isLoading || abortRef.current || !query.trim() || !sessionId) return;

      const controller = new AbortController();
      abortRef.current = controller;
      const epoch = epochRef.current;
      const isCurrent = () => epoch === epochRef.current && abortRef.current === controller;
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
      if (!messages.some(m => m.role === 'user')) {
        onSessionUpdated?.({ title: query.trim().slice(0, 60) });
      }

      // ── Stream + payload final (NDJSON v1, tolerante a líneas rotas) ───
      let streamedText = '';
      let gotFinalPayload = false;
      let gotStreamError = false;
      let parser = createParserState(performance.now());
      let summary: StreamSummary | null = null;
      try {
        const streamRes = await fetch(`${API_BASE}/legal-query-stream`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: query.trim(),
            language,
            conversation_id: sessionId,
          }),
          signal: controller.signal,
        });

        if (!isCurrent()) return;
        if (!streamRes.ok) throw new Error(`HTTP ${streamRes.status}`);
        if (!streamRes.body) throw new Error('Error de conexión');

        const reader = streamRes.body.getReader();
        const decoder = new TextDecoder();
        let lastFlushAt = 0;

        const flushStreaming = (force = false) => {
          const now = performance.now();
          if (!force && now - lastFlushAt < STREAM_FLUSH_MS) return;
          lastFlushAt = now;
          updateMessage(assistantId, { streamingContent: streamedText });
        };

        const handleEvent = (event: TimedEvent) => {
          if (!isCurrent()) return;

          if (event.type === 'stage' && !event.legacy) {
            if (event.status === 'start') {
              updateMessage(assistantId, { stage: event.stage });
            } else {
              const stage = event.stage;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, stage: undefined, completedStages: [...(m.completedStages ?? []), stage] }
                    : m
                )
              );
            }
            return;
          }

          if (event.type === 'chunk') {
            if (!event.delta) return;
            streamedText += event.delta;
            flushStreaming();
            return;
          }

          if (event.type === 'final') {
            const data = event.data as unknown as LegalQueryApiResponse;
            gotFinalPayload = true;
            const finalText = resolveFinalText(data, streamedText);
            streamedText = finalText;
            updateMessage(assistantId, {
              isStreaming: false,
              streamingContent: undefined,
              content: finalText,
              apiResponse: data,
              isLoadingFull: false,
              stage: undefined,
            });
            onSessionUpdated?.({ preview: finalText.slice(0, 80) });
            return;
          }

          if (event.type === 'error') {
            gotStreamError = true;
            const code = (event as { code?: StreamErrorCode }).code;
            if (code) {
              // Error del contrato v1: la UI lo traduce según `code` y ofrece reintentar.
              updateMessage(assistantId, {
                isStreaming: false,
                isLoadingFull: false,
                stage: undefined,
                streamingContent: undefined,
                content: streamedText,
                errorInfo: { code, retryable: (event as { retryable?: boolean }).retryable === true },
              });
            } else {
              // Evento de error antiguo, sin código: se conserva el texto y se avisa.
              updateMessage(assistantId, {
                isStreaming: false,
                isLoadingFull: false,
                stage: undefined,
                streamingContent: undefined,
                content: streamedText || 'No se pudo completar la respuesta. Intenta nuevamente.',
              });
            }
          }
        };

        const consume = (accepted: TimedEvent[]) => {
          for (const event of accepted) handleEvent(event);
        };

        while (true) {
          const { value, done } = await reader.read();
          if (!isCurrent()) { await reader.cancel(); return; }
          if (done) break;
          const pushed = pushChunk(parser, decoder.decode(value, { stream: true }), performance.now());
          parser = pushed.state;
          consume(pushed.accepted);
        }

        const tail = decoder.decode();
        if (tail) {
          const pushed = pushChunk(parser, tail, performance.now());
          parser = pushed.state;
          consume(pushed.accepted);
        }
        const closed = finishStream(parser, performance.now());
        parser = closed.state;
        consume(closed.accepted);
        summary = closed.summary;

        if (!gotFinalPayload && !gotStreamError) {
          flushStreaming(true);
          if (summary.incomplete) {
            updateMessage(assistantId, {
              isStreaming: false,
              isLoadingFull: false,
              stage: undefined,
              streamingContent: undefined,
              content: 'No se pudo completar la respuesta. Intenta nuevamente.',
            });
          } else {
            // Faltó el `final` (validación y fuentes): se usa el texto recibido y se marca como degradado.
            updateMessage(assistantId, {
              isStreaming: false,
              isLoadingFull: false,
              stage: undefined,
              streamingContent: undefined,
              content: streamedText,
              degraded: true,
            });
          }
        }
        const outcome: StreamOutcome = gotFinalPayload ? 'final' : gotStreamError ? 'error' : summary.incomplete ? 'incomplete' : 'degraded';
        sendStreamTelemetry(API_BASE, buildStreamTelemetry(summary, outcome));
      } catch (err) {
        if (!isCurrent()) return;
        if ((err as Error).name === 'AbortError') {
          sendStreamTelemetry(API_BASE, buildStreamTelemetry(summarise(parser, performance.now()), 'aborted'));
          const partial = streamedText || '(Respuesta interrumpida)';
          updateMessage(assistantId, {
            isStreaming: false,
            isLoadingFull: false,
            content: partial,
            streamingContent: undefined,
          });
          setIsLoading(false);
          abortRef.current = null;
          return;
        }

        // Manejar error de conversación no encontrada (Redis reiniciado)
        const errorStr = (err as Error).toString().toLowerCase();
        if (errorStr.includes('http 404')) {
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
      if (!isCurrent()) return;
      onSessionUpdated?.({ messageCount: messages.length + 2 });

      // Nota: Los mensajes se persisten automáticamente en el backend
      // via el endpoint /legal-query-stream cuando se envía conversation_id

      setIsLoading(false);
      abortRef.current = null;
    },
    [isLoading, language, sessionId, messages, pushMessage, updateMessage, onSessionUpdated, resolveFinalText]
  );

  // ─── Reintentar una consulta fallida ───────────────────────────────────────

  const retry = useCallback(
    (assistantId: string) => {
      if (isLoading) return;
      const index = messages.findIndex((m) => m.id === assistantId);
      const question = index > 0 ? messages[index - 1] : undefined;
      if (!question || question.role !== 'user') return;
      setMessages((prev) => prev.filter((m) => m.id !== assistantId && m.id !== question.id));
      void sendQuery(question.content);
    },
    [isLoading, messages, sendQuery]
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
        credentials: 'include',
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
        try { a.click(); }
        finally { URL.revokeObjectURL(url); }
      }
    } catch { /* noop */ }
    finally { setDownloadingPdfId(null); }
  }, []);

  // ─── Clear current session ─────────────────────────────────────────────────

  const clearChat = useCallback(() => {
    epochRef.current++;
    loadVersionRef.current++;
    abortRef.current?.abort();
    abortRef.current = null;
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
    retry,
    abort,
    downloadPdf,
    clearChat,
    checkHealth,
  };
}
