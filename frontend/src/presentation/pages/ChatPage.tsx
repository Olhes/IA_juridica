'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useChat } from '../../application/legal/use-cases/useChat';
import { useChatSessions } from '../../application/legal/use-cases/useChatSessions';
import type { SupportedLanguage } from '../../domain/legal/types';
import { ChatHeader } from '../components/chat/ChatHeader';
import { ChatInput } from '../components/chat/ChatInput';
import { ChatMessage } from '../components/chat/ChatMessage';
import { ChatWelcome } from '../components/chat/ChatWelcome';
import { ChatSidebar, SidebarToggleButton } from '../components/sidebar/ChatSidebar';

const LANGUAGE_KEY = 'preferredLanguage';

export function ChatPage() {
  const [language, setLanguage] = useState<SupportedLanguage>('spanish');
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (saved === 'spanish' || saved === 'quechua') setLanguage(saved);
  }, []);

  const handleLanguageChange = (lang: SupportedLanguage) => {
    setLanguage(lang);
    localStorage.setItem(LANGUAGE_KEY, lang);
  };

  // ── Sesiones ───────────────────────────────────────────────────────────────
  const {
    sessions,
    activeSessionId,
    hydrated: sessionsHydrated,
    setActiveSessionId,
    createSession,
    updateSessionMeta,
    deleteSession,
  } = useChatSessions();

  // Crear primera sesión si no hay ninguna (post-hidratación)
  useEffect(() => {
    if (!sessionsHydrated) return;
    if (sessions.length === 0) {
      createSession(language);
    }
  }, [sessionsHydrated, sessions.length, createSession, language]);

  // Callback para que useChat actualice la metadata del sidebar
  const onSessionUpdated = useCallback(
    (patch: { title?: string; preview?: string; messageCount?: number }) => {
      if (activeSessionId) updateSessionMeta(activeSessionId, patch);
    },
    [activeSessionId, updateSessionMeta]
  );

  // ── Chat (opera sobre la sesión activa) ───────────────────────────────────
  const {
    messages,
    isLoading,
    isOnline,
    downloadingPdfId,
    sendQuery,
    abort,
    downloadPdf,
    clearChat,
    checkHealth,
  } = useChat({ sessionId: activeSessionId, language, onSessionUpdated });

  useEffect(() => { checkHealth(); }, [checkHealth]);

  // Auto-scroll al último mensaje
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const placeholder =
    language === 'quechua'
      ? 'Tapukuyta qillqay… (↵ kachamuy)'
      : 'Escribe tu consulta legal aquí… (↵ para enviar)';

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleNewSession = () => {
    createSession(language);
    setSidebarOpen(false);
  };

  const handleSelectSession = (id: string) => {
    setActiveSessionId(id);
    setSidebarOpen(false);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-gradient-to-br from-slate-50 via-indigo-50/30 to-violet-50/20 dark:bg-none dark:bg-gray-950 transition-colors duration-300">

      {/* ── Sidebar ── */}
      <ChatSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        language={language}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
        onDeleteSession={deleteSession}
      />

      {/* ── Main area ── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <ChatHeader
          currentLanguage={language}
          onLanguageChange={handleLanguageChange}
          isOnline={isOnline}
          sidebarToggle={
            <SidebarToggleButton
              onClick={() => setSidebarOpen((v) => !v)}
              isOpen={sidebarOpen}
            />
          }
        />

        {/* Messages */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto w-full">
            {messages.length === 0 ? (
              <ChatWelcome language={language} onSelectQuery={sendQuery} />
            ) : (
              <div className="py-8 space-y-6">
                {messages.map((msg) => (
                  <ChatMessage
                    key={msg.id}
                    message={msg}
                    language={language}
                    onDownloadPdf={msg.apiResponse ? downloadPdf : undefined}
                    isDownloadingPdf={downloadingPdfId === msg.id}
                  />
                ))}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </main>

        {/* Input */}
        <div className="max-w-4xl mx-auto w-full">
          <ChatInput
            onSend={sendQuery}
            isLoading={isLoading}
            placeholder={placeholder}
            onAbort={abort}
            onClearChat={clearChat}
            hasMessages={messages.length > 0}
            language={language}
          />
        </div>
      </div>
    </div>
  );
}
