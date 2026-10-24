'use client';

import React, { useState, useRef, useEffect } from 'react';
import { X, Send, Loader2, Bot, User, Sparkles, FileText, Image as ImageIcon, X as XIcon, Volume2, VolumeX } from 'lucide-react';
import type { FeedbackPayload } from '../../domain/legal/quality';
import type {
  LegalQueryApiResponse,
  PipelineStage,
  ResponseTimings,
  StreamErrorInfo,
  SupportedLanguage,
} from '../../domain/legal/types';
import { AssistantEvidence } from './chat/EvidencePanels';
import { FeedbackBar } from './chat/FeedbackBar';
import { MarkdownRenderer } from './chat/MarkdownRenderer';
import { DegradedNotice, ResponseTiming, StageProgress, StreamErrorCard } from './chat/PipelineStatus';
import { useTextToSpeech, useQuechuaTextToSpeech } from '../../application/legal/use-cases/useSpeech';

export interface TerminalMessage {
  id: string;
  content: string;
  isUser: boolean;
  isStreaming?: boolean;
  degraded?: boolean;
  stage?: PipelineStage;
  completedStages?: PipelineStage[];
  errorInfo?: StreamErrorInfo;
  timings?: ResponseTimings;
  apiResponse?: LegalQueryApiResponse;
  requestId?: string;
}

interface TerminalModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSend: (message: string) => void;
  messages: TerminalMessage[];
  isLoading?: boolean;
  language?: SupportedLanguage;
  onRetry?: (messageId: string) => void;
  /** Envía 👍/👎 de una respuesta; si falta, no se muestra la barra de opinión. */
  onFeedback?: (payload: Omit<FeedbackPayload, 'conversation_id' | 'language'>) => Promise<{ ok: boolean; queued: boolean }>;
  returnFocusRef?: React.RefObject<HTMLButtonElement | null>;
  attachedFile?: File | null;
  onRemoveAttachment?: () => void;
  voiceInput?: string;
  onVoiceInputChange?: (text: string) => void;
  autoPlayTTS?: boolean;
}

// Texto sin marcas de Markdown para la voz (si no, lee "asterisco", "almohadilla"…).
function toSpeechText(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/(\*\*|__|\*|_|`)/g, '')
    .replace(/\n{2,}/g, '. ')
    .trim();
}

// Barras de onda animadas mientras se reproduce la voz (keyframes `eq-bar` en globals.css).
function AudioWave({ className = '' }: { className?: string }) {
  return (
    <span aria-hidden="true" className={`inline-flex h-4 items-center gap-[3px] ${className}`}>
      {[0, 0.15, 0.3, 0.45, 0.6].map((delay) => (
        <span key={delay} className="eq-bar" style={{ animationDelay: `${delay}s` }} />
      ))}
    </span>
  );
}

export function TerminalModal({
  isOpen,
  onClose,
  onSend,
  messages,
  isLoading = false,
  language = 'spanish',
  onRetry,
  onFeedback,
  returnFocusRef,
  attachedFile,
  onRemoveAttachment,
  voiceInput = '',
  onVoiceInputChange,
  autoPlayTTS = false,
}: TerminalModalProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);

  // TTS hooks for auto-play
  const { speak: speakSpanish, speaking: spanishSpeaking, stop: stopSpanish } = useTextToSpeech();
  const { speak: speakQuechua, speaking: quechuaSpeaking, loading: quechuaLoading, stop: stopQuechua } = useQuechuaTextToSpeech();
  const lastPlayedMessageId = useRef<string | null>(null);

  const ttsSpeaking = spanishSpeaking || quechuaSpeaking;

  const stopTTS = () => {
    stopSpanish();
    stopQuechua();
  };

  // Sync voice input from parent
  useEffect(() => {
    if (voiceInput) {
      setInput((prev) => {
        const combined = prev ? prev + ' ' + voiceInput : voiceInput;
        return combined.slice(0, 800);
      });
    }
  }, [voiceInput]);

  // Notify parent that voice input was consumed
  useEffect(() => {
    if (voiceInput && onVoiceInputChange) {
      onVoiceInputChange('');
    }
  }, [voiceInput, onVoiceInputChange]);

  // Auto-play TTS when using microphone and new assistant message arrives
  useEffect(() => {
    // For Spanish: only auto-play if using microphone
    // For Quechua: always auto-play (to test TTS)
    const shouldAutoPlay = language === 'quechua' ? true : autoPlayTTS;

    if (!shouldAutoPlay || isLoading || ttsSpeaking || quechuaLoading) return;

    const lastMessage = messages[messages.length - 1];
    if (lastMessage && !lastMessage.isUser && !lastMessage.isStreaming && lastMessage.content) {
      // Only play if this is a new message
      if (lastMessage.id !== lastPlayedMessageId.current) {
        lastPlayedMessageId.current = lastMessage.id;
        // Use Quechua TTS if language is quechua, otherwise Spanish TTS
        if (language === 'quechua') {
          speakQuechua(toSpeechText(lastMessage.content));
        } else {
          speakSpanish(toSpeechText(lastMessage.content));
        }
      }
    }
  }, [messages, isLoading, autoPlayTTS, ttsSpeaking, quechuaLoading, language, speakSpanish, speakQuechua]);

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
    <div className="fixed inset-0 z-[9990] flex items-end justify-center p-4 pointer-events-none sm:items-center">

      {/* Ventana flotante (diseño A: crema, bordes rosados, esquinas amplias) */}
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="terminal-title" className="relative z-10 w-[94vw] max-w-7xl h-[92vh] bg-slate-50 text-[#26162F] border border-slate-200 rounded-3xl shadow-[0_25px_60px_-15px_rgba(43,24,56,0.55)] flex flex-col overflow-hidden font-sans pointer-events-auto">

        {/* Encabezado Superior */}
        <div className="flex items-center justify-between gap-3 px-4 sm:px-6 py-3.5 border-b border-slate-200 bg-white">
          <div className="flex flex-1 items-center gap-3.5 min-w-0">
            <div className="w-11 h-11 shrink-0 rounded-lg bg-indigo-50 flex items-center justify-center text-indigo-700">
              <Sparkles className="w-6 h-6" />
            </div>
            <div className="min-w-0">
              <h2 id="terminal-title" className="font-display text-xl font-extrabold leading-tight text-[#26162F] flex items-center gap-2">
                Asistente IA Jurídico
                <span className="font-sans text-xs px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-extrabold">
                  Online
                </span>
              </h2>
              <p className="text-sm text-slate-600">
                Modelo neural de consulta de leyes y regulaciones ·{' '}
                <a href="/calidad" className="font-bold text-indigo-700 underline hover:text-indigo-800">{language === 'quechua' ? 'Allin kayninta qhaway' : 'Ver calidad del sistema'}</a>
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {(ttsSpeaking || quechuaLoading) && (
              <div className="flex items-center gap-2 rounded-full bg-indigo-50 pl-4 pr-1 py-1 text-indigo-700">
                <AudioWave />
                <span role="status" className="hidden sm:inline text-sm font-extrabold">
                  {quechuaLoading && !ttsSpeaking
                    ? (language === 'quechua' ? 'Rimayta ruraspa…' : 'Preparando audio…')
                    : (language === 'quechua' ? 'Uyarichkan' : 'Escuchando respuesta')}
                </span>
                <button
                  onClick={stopTTS}
                  className="w-9 h-9 rounded-full flex items-center justify-center bg-white text-indigo-700 hover:bg-indigo-100 transition-colors"
                  aria-label="Detener voz"
                  title="Detener voz"
                >
                  <VolumeX className="w-4 h-4" />
                </button>
              </div>
            )}
            <button
              onClick={onClose}
              className="w-11 h-11 rounded-lg flex items-center justify-center border-2 border-slate-900 bg-white text-slate-900 hover:bg-slate-100 transition-colors"
              aria-label="Cerrar"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Área de Mensajes */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-10 py-7 space-y-6">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto space-y-3">
              <div className="w-14 h-14 rounded-2xl bg-amber-400 flex items-center justify-center text-slate-900">
                <Bot className="w-7 h-7" />
              </div>
              <h3 className="font-display text-2xl font-extrabold text-[#26162F]">¿En qué puedo ayudarte hoy?</h3>
              <p className="text-base text-slate-600">
                Puedes realizar preguntas sobre pensiones de alimentos, contratos, o legislación en general.
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex items-start gap-3.5 max-w-5xl mx-auto ${
                msg.isUser ? 'flex-row-reverse' : 'flex-row'
              }`}
            >
              {msg.isUser ? (
                <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 bg-amber-400 text-slate-900">
                  <User className="w-4 h-4" />
                </div>
              ) : (
                /* Rombo tocapu del diseño A en lugar del robot */
                <svg width="40" height="40" viewBox="0 0 24 24" aria-hidden="true" className="shrink-0">
                  <path d="M9 2h6v3h4v4h3v6h-3v4h-4v3H9v-3H5v-4H2V9h3V5h4z" fill="#B8285F" />
                  <circle cx="12" cy="12" r="3.2" fill="#FFF8F0" />
                </svg>
              )}

              <div
                className={`px-5 py-3.5 text-base leading-relaxed ${
                  msg.isUser
                    ? 'max-w-[82%] bg-slate-900 text-white rounded-[20px_20px_6px_20px]'
                    : 'min-w-0 flex-1 bg-white text-[#26162F] border border-slate-200 rounded-[6px_20px_20px_20px]'
                }`}
              >
                {!msg.isUser && msg.id === lastPlayedMessageId.current && (ttsSpeaking || quechuaLoading) && (
                  <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1.5 text-xs font-extrabold text-indigo-700">
                    <AudioWave className="h-3.5" />
                    {quechuaLoading && !ttsSpeaking ? 'Preparando audio…' : 'Reproduciendo'}
                  </div>
                )}
                {msg.isUser
                  ? <p className="whitespace-pre-wrap text-left text-[16px] leading-[1.7]">{msg.content}</p>
                  : msg.content && <MarkdownRenderer content={msg.content} isStreaming={msg.isStreaming} />}
                {!msg.isUser && msg.isStreaming && (msg.stage || msg.completedStages?.length) ? (
                  <StageProgress language={language} stage={msg.stage} completed={msg.completedStages} />
                ) : null}
                {!msg.isUser && msg.degraded && <DegradedNotice language={language} />}
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
                {!msg.isUser && msg.apiResponse && msg.requestId && !msg.isStreaming && onFeedback && (
                  <FeedbackBar
                    language={language}
                    requestId={msg.requestId}
                    context={{
                      evidence_status: msg.apiResponse.metadata?.evidence_status,
                      translation_quality: msg.apiResponse.metadata?.translation?.quality,
                    }}
                    onSubmit={(rating) => onFeedback({ request_id: msg.requestId as string, ...rating })}
                  />
                )}
                {!msg.isUser && msg.timings && <ResponseTiming language={language} timings={msg.timings} />}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex items-center gap-3 max-w-5xl mx-auto text-slate-600 text-sm font-bold pl-14">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
              <span role="status">Procesando respuesta jurídica...</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Formulario Inferior */}
        <div className="px-4 pt-3 pb-4 sm:px-6 sm:pb-5 border-t border-slate-200 bg-slate-50">
          <form
            onSubmit={handleSubmit}
            className="max-w-5xl mx-auto"
          >
            {/* Archivo adjunto */}
            {attachedFile && (
              <div className="mb-2 inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-100">
                {attachedFile.type.startsWith('image/') ? (
                  <ImageIcon className="w-4 h-4 text-indigo-700" />
                ) : (
                  <FileText className="w-4 h-4 text-indigo-700" />
                )}
                <span className="text-sm font-bold text-[#26162F] truncate max-w-[300px]">
                  {attachedFile.name}
                </span>
                <button
                  type="button"
                  onClick={onRemoveAttachment}
                  aria-label="Quitar archivo adjunto"
                  className="p-1 rounded-md hover:bg-slate-200 transition-colors"
                >
                  <XIcon className="w-3.5 h-3.5 text-slate-700" />
                </button>
              </div>
            )}

            {/* Caja de escritura del diseño A: borde berenjena y botón magenta */}
            <div className="flex items-center gap-2 bg-white border-2 border-slate-900 rounded-3xl p-2 pl-4 focus-within:ring-4 focus-within:ring-indigo-100 transition-shadow">
              <input
                ref={inputRef}
                aria-label="Consulta legal"
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Escribe tu consulta legal aquí..."
                className="flex-1 min-w-0 bg-transparent py-2.5 text-[17px] text-[#26162F] placeholder-slate-500"
                // El foco lo marca el anillo del contenedor; la regla global de outline ganaría a una clase.
                style={{ outline: 'none' }}
                disabled={isLoading}
              />
              <button
                type="submit"
                aria-label="Enviar consulta"
                disabled={!input.trim() && !attachedFile || isLoading}
                className="w-[46px] h-[46px] shrink-0 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl transition-colors disabled:opacity-40 disabled:hover:bg-indigo-600 flex items-center justify-center active:scale-95"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
