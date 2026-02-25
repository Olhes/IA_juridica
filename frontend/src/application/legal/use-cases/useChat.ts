'use client';

import { useCallback, useRef, useState } from 'react';
import type { ChatMessage, LegalQueryApiResponse, SupportedLanguage } from '../../../domain/legal/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

let msgCounter = 0;
function newId() {
  return `msg-${Date.now()}-${msgCounter++}`;
}

/**
 * Core chat hook: handles streaming + full query + PDF download.
 *
 * Flow per message:
 *  1. POST /legal-query-stream → stream text into assistant bubble
 *  2. POST /legal-query       → get validation, sources, structured fields
 *  3. Merge both into the same chat message
 */
export function useChat(language: SupportedLanguage) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isOnline, setIsOnline] = useState<boolean | undefined>(undefined);
  const [downloadingPdfId, setDownloadingPdfId] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  // ───────────────────────────────────────────────────────────────
  // Helpers
  // ───────────────────────────────────────────────────────────────

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

  // ───────────────────────────────────────────────────────────────
  // Health check (optional, run once on mount)
  // ───────────────────────────────────────────────────────────────

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(4000) });
      const data = (await res.json()) as { status?: string };
      setIsOnline(data.status === 'healthy');
    } catch {
      setIsOnline(false);
    }
  }, []);

  // ───────────────────────────────────────────────────────────────
  // Send a query
  // ───────────────────────────────────────────────────────────────

  const sendQuery = useCallback(
    async (query: string) => {
      if (isLoading || !query.trim()) return;

      // Abort any in-flight request
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsLoading(true);

      // Push user message
      const userMsg: ChatMessage = {
        id: newId(),
        role: 'user',
        content: query.trim(),
        timestamp: new Date(),
      };
      pushMessage(userMsg);

      // Push placeholder assistant message
      const assistantId = newId();
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        streamingContent: '',
        isStreaming: true,
        isLoadingFull: true,
        timestamp: new Date(),
      };
      pushMessage(assistantMsg);

      // ── 1. Stream response ──────────────────────────────────────
      let streamedText = '';
      try {
        const streamRes = await fetch(`${API_BASE}/legal-query-stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: query.trim(), language }),
          signal: controller.signal,
        });

        if (!streamRes.ok || !streamRes.body) {
          throw new Error('No se pudo conectar con el servidor.');
        }

        const reader = streamRes.body.getReader();
        const decoder = new TextDecoder();

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          streamedText += chunk;
          updateMessage(assistantId, { streamingContent: streamedText });
        }
        streamedText += decoder.decode();
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          updateMessage(assistantId, {
            isStreaming: false,
            isLoadingFull: false,
            content: streamedText || '(Respuesta interrumpida)',
            streamingContent: undefined,
          });
          setIsLoading(false);
          return;
        }
        // Fall through to error handling after stream fails
      }

      // Mark streaming done, keep isLoadingFull while we fetch validation
      updateMessage(assistantId, {
        isStreaming: false,
        content: streamedText,
        streamingContent: undefined,
      });

      // ── 2. Full query for validation + sources ──────────────────
      try {
        const fullRes = await fetch(`${API_BASE}/legal-query`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: query.trim(), language }),
          signal: controller.signal,
        });

        if (fullRes.ok) {
          const data = (await fullRes.json()) as LegalQueryApiResponse;
          // Use the structured Spanish/Quechua text if available, else keep streamed
          const structuredText =
            language === 'quechua'
              ? data.response?.respuesta_quechua || streamedText
              : data.response?.respuesta_espanol || streamedText;

          updateMessage(assistantId, {
            content: structuredText,
            apiResponse: data,
            isLoadingFull: false,
          });
        } else {
          // Validation unavailable but we still have streamed text
          updateMessage(assistantId, { isLoadingFull: false });
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          // Non-critical: we still have the streamed answer
        }
        updateMessage(assistantId, { isLoadingFull: false });
      }

      setIsLoading(false);
    },
    [isLoading, language, pushMessage, updateMessage]
  );

  // ───────────────────────────────────────────────────────────────
  // Abort
  // ───────────────────────────────────────────────────────────────

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
  }, []);

  // ───────────────────────────────────────────────────────────────
  // PDF Download
  // ───────────────────────────────────────────────────────────────

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
    } catch {
      // Silently ignore
    } finally {
      setDownloadingPdfId(null);
    }
  }, []);

  // ───────────────────────────────────────────────────────────────
  // Clear
  // ───────────────────────────────────────────────────────────────

  const clearChat = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setIsLoading(false);
  }, []);

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
