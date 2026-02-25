'use client';

import { ArrowUp, Mic, Square } from 'lucide-react';
import { type KeyboardEvent, useRef, useState } from 'react';

interface ChatInputProps {
  onSend: (query: string) => void;
  isLoading: boolean;
  placeholder?: string;
  onAbort?: () => void;
}

const MAX_CHARS = 800;

const EXAMPLE_QUERIES = [
  '¿Qué hago si mi pareja me golpea?',
  '¿Cómo solicito pensión de alimentos?',
  '¿Qué medidas de protección puedo pedir?',
  '¿Cómo puedo denunciar violencia familiar?',
];

export function ChatInput({ onSend, isLoading, placeholder, onAbort }: ChatInputProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const trimmed = text.trim();
  const canSend = trimmed.length > 0 && !isLoading;

  const handleSend = () => {
    if (!canSend) return;
    onSend(trimmed);
    setText('');
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  };

  const selectExample = (q: string) => {
    setText(q);
    textareaRef.current?.focus();
  };

  return (
    <div className="border-t border-slate-200 bg-white/80 backdrop-blur-md">
      {/* Example queries */}
      <div className="max-w-4xl mx-auto px-4 md:px-8 pt-3 pb-1">
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_QUERIES.map((q) => (
            <button
              key={q}
              id={`example-${q.slice(0, 20).replace(/\s+/g, '-').toLowerCase()}`}
              type="button"
              onClick={() => selectExample(q)}
              disabled={isLoading}
              className="text-xs px-3 py-1.5 rounded-full border border-slate-200 text-slate-600 hover:border-indigo-300 hover:text-indigo-700 hover:bg-indigo-50 transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Input area */}
      <div className="max-w-4xl mx-auto px-4 md:px-8 py-4">
        <div className="flex items-end gap-3 bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100 transition-all duration-200">
          <textarea
            ref={textareaRef}
            id="chat-input"
            value={text}
            onChange={(e) => {
              if (e.target.value.length <= MAX_CHARS) setText(e.target.value);
            }}
            onKeyDown={handleKey}
            onInput={handleInput}
            placeholder={placeholder ?? 'Escribe tu consulta legal aquí… (↵ para enviar)'}
            rows={1}
            disabled={isLoading}
            className="flex-1 resize-none bg-transparent text-sm md:text-base text-slate-800 placeholder-slate-400 focus:outline-none min-h-[24px] max-h-[180px] leading-relaxed disabled:opacity-60"
          />

          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Char counter */}
            {text.length > MAX_CHARS * 0.8 && (
              <span
                className={`text-xs font-mono ${text.length >= MAX_CHARS ? 'text-red-500' : 'text-slate-400'}`}
              >
                {MAX_CHARS - text.length}
              </span>
            )}

            {/* Abort / Send button */}
            {isLoading && onAbort ? (
              <button
                id="chat-abort-btn"
                type="button"
                onClick={onAbort}
                className="w-9 h-9 rounded-xl bg-red-500 hover:bg-red-600 text-white flex items-center justify-center transition-colors shadow-sm"
                title="Detener respuesta"
              >
                <Square className="w-4 h-4 fill-current" />
              </button>
            ) : (
              <button
                id="chat-send-btn"
                type="button"
                onClick={handleSend}
                disabled={!canSend}
                className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white flex items-center justify-center transition-all shadow-sm disabled:opacity-40 disabled:cursor-not-allowed hover:shadow-md hover:scale-105 active:scale-95"
                title="Enviar consulta"
              >
                {isLoading ? (
                  <Mic className="w-4 h-4 animate-pulse" />
                ) : (
                  <ArrowUp className="w-4 h-4" />
                )}
              </button>
            )}
          </div>
        </div>
        <p className="text-xs text-slate-400 text-center mt-2">
          Esta orientación no reemplaza la asesoría de una abogada o abogado.
        </p>
      </div>
    </div>
  );
}
