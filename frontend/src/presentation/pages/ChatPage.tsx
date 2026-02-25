'use client';

import { Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { SupportedLanguage } from '../../domain/legal/types';
import { useChat } from '../../application/legal/use-cases/useChat';
import { ChatHeader } from '../components/chat/ChatHeader';
import { ChatInput } from '../components/chat/ChatInput';
import { ChatMessage } from '../components/chat/ChatMessage';
import { ChatWelcome } from '../components/chat/ChatWelcome';

const LANGUAGE_KEY = 'preferredLanguage';

export function ChatPage() {
  const [language, setLanguage] = useState<SupportedLanguage>('spanish');

  // Restore language preference
  useEffect(() => {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (saved === 'spanish' || saved === 'quechua') setLanguage(saved);
  }, []);

  const handleLanguageChange = (lang: SupportedLanguage) => {
    setLanguage(lang);
    localStorage.setItem(LANGUAGE_KEY, lang);
  };

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
  } = useChat(language);

  // Health check on mount
  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  // Auto-scroll to bottom
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const placeholder =
    language === 'quechua'
      ? 'Tapukuyta qillqay… (↵ kachamuy)'
      : 'Escribe tu consulta legal aquí… (↵ para enviar)';

  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-slate-50 via-indigo-50/30 to-violet-50/20 overflow-hidden">
      {/* Header */}
      <ChatHeader
        currentLanguage={language}
        onLanguageChange={handleLanguageChange}
        isOnline={isOnline}
      />

      {/* Messages area */}
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

      {/* Input area */}
      <div className="max-w-4xl mx-auto w-full">
        {/* Clear chat button (only visible when there are messages) */}
        {messages.length > 0 && (
          <div className="flex justify-end px-4 md:px-8 pt-1">
            <button
              id="clear-chat-btn"
              type="button"
              onClick={clearChat}
              disabled={isLoading}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-red-500 transition-colors disabled:opacity-40"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Limpiar chat
            </button>
          </div>
        )}
        <ChatInput
          onSend={sendQuery}
          isLoading={isLoading}
          placeholder={placeholder}
          onAbort={abort}
        />
      </div>
    </div>
  );
}
