'use client';

import {
  AlertTriangle,
  ChevronLeft,
  MessageSquarePlus,
  MessagesSquare,
  MoreVertical,
  Scale,
  Trash2,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { ChatSessionMeta, SupportedLanguage } from '../../../domain/legal/types';

interface ChatSidebarProps {
  sessions: ChatSessionMeta[];
  activeSessionId: string | null;
  language: SupportedLanguage;
  isOpen: boolean;
  onClose: () => void;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

const i18n = {
  spanish: {
    title:      'Mis consultas',
    newChat:    'Nueva consulta',
    noChats:    'Sin consultas',
    noChatsHint:'Inicia una nueva consulta para comenzar.',
    deleteAll:  'Eliminar todas',
    confirmDel: '¿Eliminar esta consulta?',
    cancel:     'Cancelar',
    delete:     'Eliminar',
    messages:   (n: number) => `${n} mensaje${n !== 1 ? 's' : ''}`,
  },
  quechua: {
    title:      'Tapukuykuna',
    newChat:    'Musuq tapukuy',
    noChats:    'Mana tapukuychu',
    noChatsHint:'Musuq tapukuyta qallariy.',
    deleteAll:  'Llapanta pichay',
    confirmDel: '¿Kay tapukuyta pichankichu?',
    cancel:     'Mana',
    delete:     'Pichay',
    messages:   (n: number) => `${n} willay${n !== 1 ? 'kuna' : ''}`,
  },
} as const;

function formatDate(iso: string, lang: SupportedLanguage): string {
  const date = new Date(iso);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / 86_400_000);
  const locale = lang === 'quechua' ? 'es-PE' : 'es-PE';

  if (diffDays === 0) return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
  if (diffDays === 1) return 'Ayer';
  if (diffDays < 7)  return date.toLocaleDateString(locale, { weekday: 'short' });
  return date.toLocaleDateString(locale, { day: 'numeric', month: 'short' });
}

// ── Session row ──────────────────────────────────────────────────────────────

function SessionRow({
  session,
  isActive,
  language,
  onSelect,
  onDelete,
}: {
  session: ChatSessionMeta;
  isActive: boolean;
  language: SupportedLanguage;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const t = i18n[language];
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Cerrar menú al hacer click fuera
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuOpen]);

  return (
    <div
      className={`group relative flex items-start gap-2.5 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-150 ${
        isActive
          ? 'bg-indigo-600 text-white shadow-md'
          : 'hover:bg-slate-100 dark:hover:bg-gray-800 text-slate-700 dark:text-slate-300'
      }`}
      onClick={onSelect}
      onKeyDown={(e) => e.key === 'Enter' && onSelect()}
      // biome-ignore lint/a11y/useSemanticElements: composite widget
      role="button"
      tabIndex={0}
    >
      {/* Icon */}
      <MessagesSquare className={`w-4 h-4 mt-0.5 flex-shrink-0 ${isActive ? 'text-indigo-200' : 'text-slate-400 dark:text-slate-500'}`} />

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className={`text-xs font-semibold truncate ${isActive ? 'text-white' : 'text-slate-800 dark:text-slate-200'}`}>
          {session.title}
        </p>
        {session.preview && (
          <p className={`text-xs truncate mt-0.5 ${isActive ? 'text-indigo-200' : 'text-slate-400 dark:text-slate-500'}`}>
            {session.preview}
          </p>
        )}
        <div className="flex items-center gap-2 mt-1">
          <span className={`text-xs ${isActive ? 'text-indigo-300' : 'text-slate-400 dark:text-slate-600'}`}>
            {formatDate(session.updatedAt, language)}
          </span>
          {session.messageCount > 0 && (
            <span className={`text-xs ${isActive ? 'text-indigo-300' : 'text-slate-400 dark:text-slate-600'}`}>
              · {t.messages(session.messageCount)}
            </span>
          )}
        </div>
      </div>

      {/* Menu button */}
      <div
        ref={menuRef}
        className="flex-shrink-0"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          id={`session-menu-${session.id}`}
          onClick={() => setMenuOpen((v) => !v)}
          className={`w-6 h-6 rounded-lg flex items-center justify-center transition-all opacity-0 group-hover:opacity-100 ${
            isActive
              ? 'hover:bg-indigo-500 text-indigo-200'
              : 'hover:bg-slate-200 dark:hover:bg-gray-700 text-slate-400'
          } ${menuOpen ? 'opacity-100' : ''}`}
        >
          <MoreVertical className="w-3.5 h-3.5" />
        </button>

        {/* Dropdown */}
        {menuOpen && (
          <div className="absolute right-2 top-8 z-50 bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-xl shadow-lg p-1 min-w-[160px]">
            {confirming ? (
              <div className="px-3 py-2">
                <div className="flex items-center gap-2 mb-2 text-xs text-amber-600 dark:text-amber-400">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  {t.confirmDel}
                </div>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => setConfirming(false)}
                    className="flex-1 text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-gray-600 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    {t.cancel}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setMenuOpen(false); onDelete(); }}
                    className="flex-1 text-xs px-2 py-1 rounded-lg bg-red-500 hover:bg-red-600 text-white transition-colors"
                  >
                    {t.delete}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t.delete}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sidebar principal ────────────────────────────────────────────────────────

export function ChatSidebar({
  sessions,
  activeSessionId,
  language,
  isOpen,
  onClose,
  onNewSession,
  onSelectSession,
  onDeleteSession,
}: ChatSidebarProps) {
  const t = i18n[language];

  // Ordenar por updatedAt desc
  const sorted = [...sessions].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
  );

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 pt-5 pb-4 border-b border-slate-200 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <Scale className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          <span className="text-sm font-bold text-slate-800 dark:text-slate-100">{t.title}</span>
        </div>
        {/* Close button — mobile only */}
        <button
          type="button"
          onClick={onClose}
          className="lg:hidden w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-gray-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* ── Nueva consulta ── */}
      <div className="px-3 pt-3 pb-2">
        <button
          id="new-session-btn"
          type="button"
          onClick={onNewSession}
          className="w-full flex items-center gap-2.5 px-4 py-2.5 rounded-xl
            bg-gradient-to-r from-indigo-600 to-violet-600
            hover:from-indigo-700 hover:to-violet-700
            text-white text-sm font-semibold
            shadow-sm hover:shadow-md
            transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
        >
          <MessageSquarePlus className="w-4 h-4" />
          {t.newChat}
        </button>
      </div>

      {/* ── Lista de sesiones ── */}
      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-0.5">
        {sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <MessagesSquare className="w-10 h-10 text-slate-200 dark:text-gray-700 mb-3" />
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{t.noChats}</p>
            <p className="text-xs text-slate-400 dark:text-slate-600 mt-1">{t.noChatsHint}</p>
          </div>
        ) : (
          sorted.map((session) => (
            <SessionRow
              key={session.id}
              session={session}
              isActive={session.id === activeSessionId}
              language={language}
              onSelect={() => { onSelectSession(session.id); onClose(); }}
              onDelete={() => onDeleteSession(session.id)}
            />
          ))
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* ── Desktop sidebar (fixed) ── */}
      <aside className="hidden lg:flex flex-col w-64 xl:w-72 flex-shrink-0 h-screen sticky top-0 border-r border-slate-200 dark:border-gray-800 bg-white/90 dark:bg-gray-900/90 backdrop-blur-md overflow-hidden">
        {sidebarContent}
      </aside>

      {/* ── Mobile drawer ── */}
      {isOpen && (
        <>
          {/* Overlay */}
          <div
            className="lg:hidden fixed inset-0 bg-black/40 backdrop-blur-sm z-40 animate-fade-in"
            onClick={onClose}
            onKeyDown={(e) => e.key === 'Escape' && onClose()}
            aria-label="Cerrar sidebar"
            // biome-ignore lint/a11y/useSemanticElements: overlay div
            role="button"
            tabIndex={-1}
          />
          {/* Drawer */}
          <aside className="lg:hidden fixed left-0 top-0 h-full w-72 z-50 bg-white dark:bg-gray-900 border-r border-slate-200 dark:border-gray-800 shadow-2xl flex flex-col overflow-hidden animate-slide-in-left">
            {sidebarContent}
          </aside>
        </>
      )}
    </>
  );
}

// ── Botón hamburguesa para mobile ────────────────────────────────────────────

export function SidebarToggleButton({
  onClick,
  isOpen,
}: {
  onClick: () => void;
  isOpen: boolean;
}) {
  return (
    <button
      id="sidebar-toggle-btn"
      type="button"
      onClick={onClick}
      aria-label={isOpen ? 'Cerrar panel' : 'Abrir panel de consultas'}
      className="lg:hidden w-9 h-9 flex items-center justify-center rounded-xl
        bg-slate-100 hover:bg-slate-200
        dark:bg-gray-800 dark:hover:bg-gray-700
        text-slate-600 dark:text-slate-300
        transition-all duration-200 hover:scale-105 active:scale-95"
    >
      {isOpen
        ? <ChevronLeft className="w-4 h-4" />
        : <MessagesSquare className="w-4 h-4" />}
    </button>
  );
}
