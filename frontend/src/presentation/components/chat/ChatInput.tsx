'use client';

import {
  ArrowUp,
  HelpCircle,
  Landmark,
  Scale,
  Shield,
  Square,
  Trash2,
  Users,
} from 'lucide-react';
import { type KeyboardEvent, useRef, useState } from 'react';
import type { SupportedLanguage } from '../../../domain/legal/types';

interface ChatInputProps {
  onSend: (query: string) => void;
  isLoading: boolean;
  placeholder?: string;
  onAbort?: () => void;
  onClearChat?: () => void;
  hasMessages?: boolean;
  language: SupportedLanguage;
}

const MAX_CHARS = 800;

// ─── Traducciones ─────────────────────────────────────────────────────────────

const i18n = {
  spanish: {
    clearTitle: 'Limpiar conversación',
    clearLabel: 'Limpiar',
    stopTitle: 'Detener respuesta',
    sendTitle: 'Enviar consulta (↵)',
    disclaimer: 'Esta orientación no reemplaza la asesoría de una abogada o abogado. · Shift+↵ nueva línea',
    chips: [
      { Icon: Shield,     label: '¿Cómo denuncio violencia?',  query: '¿Cómo puedo denunciar violencia familiar?' },
      { Icon: Users,      label: '¿Cómo pido pensión?',        query: '¿Cómo solicito pensión de alimentos para mis hijos?' },
      { Icon: Scale,      label: '¿Qué medidas puedo pedir?',  query: '¿Qué medidas de protección puedo pedir hoy?' },
      { Icon: Landmark,   label: '¿Cómo funciona la denuncia?',query: '¿Cómo funciona el proceso de denuncia penal?' },
      { Icon: HelpCircle, label: '¿Qué leyes me protegen?',    query: '¿Qué leyes me protegen en caso de violencia familiar en Perú?' },
    ],
  },
  quechua: {
    clearTitle: 'Rimayta pichay',
    clearLabel: 'Pichay',
    stopTitle: 'Kutichiy sayaychiy',
    sendTitle: 'Tapukuyta kachamuy (↵)',
    disclaimer: 'Kay orientacionqa mana reemplazanchu abogadopa yanapayninta. · Shift+↵ musuq siq\'i',
    chips: [
      { Icon: Shield,     label: 'Llakichikuyta willay',       query: '¿Imaynatataq llakichikuyta willaqman rini?' },
      { Icon: Users,      label: 'Alimentosta mañakuy',        query: '¿Imaynatataq wawaykunapaq alimentosta mañakuy?' },
      { Icon: Scale,      label: '¿Ima proteccionesta mañakuy?', query: '¿Qanpaq ima proteccionesta mañakuy atikuy?' },
      { Icon: Landmark,   label: 'Willaypa puriy',             query: '¿Imaynatataq willaypa puriynin kachkan?' },
      { Icon: HelpCircle, label: '¿Ima leykunam llampuyawanki?', query: '¿Ima leykunam llakichikuyta mana saqenanpaq kachkan?' },
    ],
  },
} as const;

export function ChatInput({
  onSend,
  isLoading,
  placeholder,
  onAbort,
  onClearChat,
  hasMessages,
  language,
}: ChatInputProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const t = i18n[language];

  const trimmed = text.trim();
  const canSend = trimmed.length > 0 && !isLoading;
  const charPct = text.length / MAX_CHARS;

  const handleSend = () => {
    if (!canSend) return;
    onSend(trimmed);
    setText('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  };

  return (
    <div className="border-t border-slate-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md">

      {/* ── Chips de ejemplos ── */}
      <div className="max-w-4xl mx-auto px-4 md:px-8 pt-3 pb-1 flex items-center flex-wrap gap-2">
        {t.chips.map(({ Icon, label, query }) => (
          <button
            key={label}
            id={`example-${label.slice(0, 15).replace(/\s+/g, '-').toLowerCase()}`}
            type="button"
            onClick={() => {
              setText(query);
              textareaRef.current?.focus();
            }}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full
              border border-slate-200 dark:border-gray-700
              text-slate-600 dark:text-slate-400
              hover:border-indigo-300 dark:hover:border-indigo-700
              hover:text-indigo-700 dark:hover:text-indigo-300
              hover:bg-indigo-50 dark:hover:bg-indigo-950/40
              transition-all duration-150
              disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}

        {/* Botón limpiar — solo si hay mensajes */}
        {hasMessages && onClearChat && (
          <button
            id="clear-chat-btn"
            type="button"
            onClick={onClearChat}
            disabled={isLoading}
            title={t.clearTitle}
            className="ml-auto inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full
              border border-slate-200 dark:border-gray-700
              text-slate-400 dark:text-slate-500
              hover:border-red-300 dark:hover:border-red-800
              hover:text-red-600 dark:hover:text-red-400
              hover:bg-red-50 dark:hover:bg-red-950/30
              transition-all duration-150
              disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
          >
            <Trash2 className="w-3.5 h-3.5" />
            {t.clearLabel}
          </button>
        )}
      </div>

      {/* ── Área de texto ── */}
      <div className="max-w-4xl mx-auto px-4 md:px-8 py-3">
        <div className={`flex items-end gap-3
          bg-slate-50 dark:bg-gray-800
          border rounded-2xl px-4 py-3
          transition-all duration-200
          focus-within:ring-2 focus-within:ring-indigo-100 dark:focus-within:ring-indigo-900/50
          ${charPct >= 1
            ? 'border-red-400 dark:border-red-700'
            : 'border-slate-200 dark:border-gray-700 focus-within:border-indigo-400 dark:focus-within:border-indigo-600'
          }`}
        >
          <textarea
            ref={textareaRef}
            id="chat-input"
            value={text}
            onChange={(e) => { if (e.target.value.length <= MAX_CHARS) setText(e.target.value); }}
            onKeyDown={handleKey}
            onInput={handleInput}
            placeholder={placeholder}
            rows={1}
            disabled={isLoading}
            className="flex-1 resize-none bg-transparent
              text-sm md:text-base
              text-slate-800 dark:text-slate-200
              placeholder-slate-400 dark:placeholder-slate-600
              focus:outline-none min-h-[24px] max-h-[180px] leading-relaxed
              disabled:opacity-60"
          />

          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Contador de caracteres */}
            {charPct >= 0.75 && (
              <span className={`text-xs font-mono tabular-nums ${charPct >= 1 ? 'text-red-500' : 'text-slate-400 dark:text-slate-500'}`}>
                {MAX_CHARS - text.length}
              </span>
            )}

            {/* Abort / Send */}
            {isLoading && onAbort ? (
              <button
                id="chat-abort-btn"
                type="button"
                onClick={onAbort}
                className="w-9 h-9 rounded-xl bg-red-500 hover:bg-red-600 text-white flex items-center justify-center transition-colors shadow-sm"
                title={t.stopTitle}
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
                title={t.sendTitle}
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        <p className="text-xs text-slate-400 dark:text-slate-600 text-center mt-2">
          {t.disclaimer}
        </p>
      </div>
    </div>
  );
}
