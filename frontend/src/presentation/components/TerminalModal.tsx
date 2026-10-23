'use client';

import React, { useState, useRef, useEffect } from 'react';
import { X, Send, Loader2, Bot, User, Sparkles } from 'lucide-react';
import type {
  LegalQueryApiResponse,
  PipelineStage,
  ResponseTimings,
  StreamErrorInfo,
  SupportedLanguage,
} from '../../domain/legal/types';
import { AssistantEvidence } from './chat/EvidencePanels';
import { ResponseTiming, StageProgress, StreamErrorCard } from './chat/PipelineStatus';

export interface TerminalMessage {
  id: string;
  content: string;
  isUser: boolean;
  isStreaming?: boolean;
  stage?: PipelineStage;
  completedStages?: PipelineStage[];
  errorInfo?: StreamErrorInfo;
  timings?: ResponseTimings;
  apiResponse?: LegalQueryApiResponse;
}

interface TerminalModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSend: (message: string) => void;
  messages: TerminalMessage[];
  isLoading?: boolean;
  language?: SupportedLanguage;
  onRetry?: (messageId: string) => void;
  returnFocusRef?: React.RefObject<HTMLButtonElement | null>;
}

export function TerminalModal({
  isOpen,
  onClose,
  onSend,
  messages,
  isLoading = false,
  language = 'spanish',
  onRetry,
  returnFocusRef,
}: TerminalModalProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);

  useEffect(() => {
    if (!isOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeRef.current();
      if (event.key === 'Tab') {
        const controls = dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled)');
        if (!controls?.length) return;
        const first = controls[0]; const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('keydown', closeOnEscape);
      if (previous?.isConnected && previous !== document.body && previous !== document.documentElement) previous.focus();
      else returnFocusRef?.current?.focus();
    };
  }, [isOpen, returnFocusRef]);

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen, isLoading]);
  useEffect(() => { if (isOpen) inputRef.current?.focus(); }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSend(input.trim());
    setInput('');
  };

  return (
    /* Contenedor Overlay: Transparente sin blur - Ajustado para no tapar parte superior */
    <div className="fixed inset-0 z-[9990] flex items-end justify-center p-4 pointer-events-none font-mono sm:items-center">
      
      {/* Cargar Tipografías */}
      <link
        href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@400;500;600&display=swap"
        rel="stylesheet"
      />

      {/* Ventana flotante con sombras acentuadas para dar elevación sin oscurecer la pantalla */}
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="terminal-title" className="relative z-10 w-[94vw] max-w-7xl h-[92vh] bg-zinc-950/95 border border-zinc-800/90 rounded-2xl shadow-[0_25px_60px_-15px_rgba(0,0,0,0.8)] flex flex-col overflow-hidden font-['Plus_Jakarta_Sans',sans-serif] pointer-events-auto">
        
        {/* Encabezado Superior */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800/80 bg-zinc-900/60 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 id="terminal-title" className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                Asistente IA Jurídico
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">
                  Online
                </span>
              </h2>
              <p className="text-xs text-zinc-400">Modelo neural de consulta de leyes y regulaciones</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-all"
            aria-label="Cerrar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Área de Mensajes */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-10 py-6 space-y-6 scrollbar-thin scrollbar-thumb-zinc-800">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-300 shadow-inner">
                <Bot className="w-6 h-6 text-indigo-400" />
              </div>
              <h3 className="text-lg font-medium text-zinc-200">¿En qué puedo ayudarte hoy?</h3>
              <p className="text-sm text-zinc-400">
                Puedes realizar preguntas sobre pensiones de alimentos, contratos, o legislación en general.
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex items-start gap-4 max-w-5xl mx-auto ${
                msg.isUser ? 'flex-row-reverse' : 'flex-row'
              }`}
            >
              <div
                className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 text-xs font-medium border ${
                  msg.isUser
                    ? 'bg-indigo-600 text-white border-indigo-500'
                    : 'bg-zinc-900 text-zinc-300 border-zinc-700/80'
                }`}
              >
                {msg.isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4 text-indigo-400" />}
              </div>

              <div
                className={`rounded-2xl px-5 py-3.5 text-sm leading-relaxed ${
                  msg.isUser
                    ? 'bg-indigo-600 text-white rounded-tr-none shadow-md'
                    : 'bg-zinc-900 text-zinc-200 border border-zinc-800 rounded-tl-none shadow-sm'
                }`}
              >
                {(msg.content || msg.isUser) && <p className="whitespace-pre-wrap">{msg.content}</p>}
                {!msg.isUser && msg.isStreaming && (msg.stage || msg.completedStages?.length) ? (
                  <StageProgress language={language} stage={msg.stage} completed={msg.completedStages} />
                ) : null}
                {!msg.isUser && msg.errorInfo && (
                  <StreamErrorCard
                    language={language}
                    error={msg.errorInfo}
                    onRetry={onRetry ? () => onRetry(msg.id) : undefined}
                  />
                )}
                {!msg.isUser && msg.apiResponse && !msg.isStreaming && (
                  <AssistantEvidence language={language} apiResponse={msg.apiResponse} />
                )}
                {!msg.isUser && msg.timings && <ResponseTiming language={language} timings={msg.timings} />}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex items-center gap-3 max-w-5xl mx-auto text-zinc-400 text-sm pl-12">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
              <span role="status">Procesando respuesta jurídica...</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Formulario Inferior */}
        <div className="p-4 sm:p-6 border-t border-zinc-800/80 bg-zinc-950">
          <form
            onSubmit={handleSubmit}
            className="max-w-5xl mx-auto relative flex items-center"
          >
            <input
              ref={inputRef}
              aria-label="Consulta legal"
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Escribe tu consulta legal aquí..."
              className="w-full bg-zinc-900 border border-zinc-700/80 focus:border-indigo-500 rounded-2xl pl-5 pr-14 py-3.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all"
              disabled={isLoading}
            />
            <button
              type="submit"
              aria-label="Enviar consulta"
              disabled={!input.trim() || isLoading}
              className="absolute right-2 p-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl transition-all disabled:opacity-30 disabled:hover:bg-indigo-600 flex items-center justify-center active:scale-95"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
