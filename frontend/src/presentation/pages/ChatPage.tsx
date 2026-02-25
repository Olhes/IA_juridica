'use client';

import { useEffect, useRef, useState } from 'react';
import { useChat } from '../../application/legal/use-cases/useChat';
import type { SupportedLanguage } from '../../domain/legal/types';
import { ChatHeader } from '../components/chat/ChatHeader';
import { ChatInput } from '../components/chat/ChatInput';
import { ChatMessage } from '../components/chat/ChatMessage';
import { ChatWelcome } from '../components/chat/ChatWelcome';

const LANGUAGE_KEY = 'preferredLanguage';

export function ChatPage() {
  const [language, setLanguage] = useState<SupportedLanguage>('spanish');

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

  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  // Auto-scroll al último mensaje
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const placeholder =
    language === 'quechua'
      ? 'Tapukuyta qillqay… (↵ kachamuy)'
      : 'Escribe tu consulta legal aquí… (↵ para enviar)';

  return (
    <div className="flex flex-col h-screen overflow-hidden
      bg-gradient-to-br from-slate-50 via-indigo-50/30 to-violet-50/20
      dark:bg-none dark:bg-gray-950
      transition-colors duration-300"
    >
      <ChatHeader
        currentLanguage={language}
        onLanguageChange={handleLanguageChange}
        isOnline={isOnline}
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
  );
}
