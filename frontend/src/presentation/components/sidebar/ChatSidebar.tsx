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
  loading: boolean;
  loadError: string | null;
  onClose: () => void;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onRetry: () => void;
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
    loadError:  'No pudimos cargar tus consultas.',
    retry:      'Reintentar',
    retrying:   'Reintentando...',
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
    loadError:  'Tapukuykunata mana apamuyta atirqanchikchu.',
    retry:      'Wakmanta ruray',
    retrying:   'Wakmanta ruraspa...',
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

// ── Fila de sesión ───────────────────────────────────────────────────────────

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
      className={`group relative flex items-start gap-2.5 px-3 py-2 rounded-md cursor-pointer transition-colors duration-150 border-l-4 ${
        isActive
          ? 'bg-[#33203F] border-amber-400 text-white'
          : 'border-transparent hover:bg-slate-800 text-slate-100'
      }`}
      onClick={onSelect}
      onKeyDown={(e) => e.key === 'Enter' && onSelect()}
      // biome-ignore lint/a11y/useSemanticElements: composite widget
      role="button"
      tabIndex={0}
    >
      {/* Icon */}
      <MessagesSquare className={`w-4 h-4 mt-1 flex-shrink-0 ${isActive ? 'text-amber-400' : 'text-slate-300'}`} />

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className={`text-[15px] truncate ${isActive ? 'font-bold text-white' : 'font-semibold text-slate-100'}`}>
          {session.title}
        </p>
        {session.preview && (
          <p className="text-xs truncate mt-0.5 text-slate-300">
            {session.preview}
          </p>
        )}
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[13px] text-slate-300">
            {formatDate(session.updatedAt, language)}
          </span>
          {session.messageCount > 0 && (
            <span className="text-[13px] text-slate-300">
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
          aria-label={`Opciones de ${session.title}`}
          onClick={() => setMenuOpen((v) => !v)}
          className={`w-7 h-7 rounded-md flex items-center justify-center transition-all opacity-0 group-hover:opacity-100 hover:bg-slate-700 text-slate-300 ${menuOpen ? 'opacity-100' : ''}`}
        >
          <MoreVertical className="w-3.5 h-3.5" />
        </button>

        {/* Dropdown */}
        {menuOpen && (
          <div className="absolute right-2 top-8 z-50 bg-slate-800 border border-slate-700 rounded-xl shadow-lg p-1 min-w-[160px]">
            {confirming ? (
              <div className="px-3 py-2">
                <div className="flex items-center gap-2 mb-2 text-xs text-amber-400">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  {t.confirmDel}
                </div>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => setConfirming(false)}
                    className="flex-1 text-xs px-2 py-1.5 rounded-lg border border-slate-600 text-slate-100 hover:bg-slate-700 transition-colors"
                  >
                    {t.cancel}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setMenuOpen(false); onDelete(); }}
                    className="flex-1 text-xs px-2 py-1.5 rounded-lg bg-red-500 hover:bg-red-600 text-white transition-colors"
                  >
                    {t.delete}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-red-300 hover:bg-red-950/40 transition-colors"
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
  loading,
  loadError,
  onClose,
  onNewSession,
  onSelectSession,
  onDeleteSession,
  onRetry,
}: ChatSidebarProps) {
  const t = i18n[language];

  // Ordenar por updatedAt desc
  const sorted = [...sessions].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
  );

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* ── Franja tejida (tocapu) del diseño A ── */}
      <svg width="100%" height="28" aria-hidden="true" className="block flex-none">
        <defs>
          <pattern id="sidebar-tocapu" width="56" height="28" patternUnits="userSpaceOnUse">
            <rect width="56" height="28" fill="#B8285F" />
            <rect width="28" height="28" fill="#F2A93B" />
            <path d="M14 4l10 10-10 10L4 14z" fill="#2B1838" />
            <path d="M14 9l5 5-5 5-5-5z" fill="#1E9C97" />
            <rect x="34" y="6" width="16" height="16" fill="none" stroke="#FFF8F0" strokeWidth="2" />
            <rect x="39" y="11" width="6" height="6" fill="#FFF8F0" />
          </pattern>
        </defs>
        <rect width="100%" height="28" fill="url(#sidebar-tocapu)" />
      </svg>

      {/* ── Header ── */}
      <div className="flex items-center justify-between px-5 pt-5 pb-2">
        <div className="flex items-center gap-3">
          <Scale className="w-7 h-7 text-amber-400" />
          <span className="font-display text-xl font-extrabold leading-tight text-white">{t.title}</span>
        </div>
        {/* Close button — mobile only */}
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar consultas"
          className="lg:hidden w-9 h-9 rounded-md flex items-center justify-center text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* ── Nueva consulta ── */}
      <div className="px-5 pt-4 pb-4">
        <button
          id="new-session-btn"
          type="button"
          onClick={onNewSession}
          className="w-full min-h-[50px] flex items-center justify-center gap-2 px-4 rounded-xl
            bg-amber-400 hover:bg-amber-300 text-slate-900 font-extrabold
            transition-colors duration-200 active:scale-[0.98]"
        >
          <MessageSquarePlus className="w-4 h-4" />
          {t.newChat}
        </button>
      </div>

      {/* ── Lista de sesiones ── */}
      <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-0.5">
        {loadError && (
          <div role="alert" className="mx-1 mb-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-amber-900 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-200">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
              <div>
                <p className="text-xs font-medium">{t.loadError}</p>
                <button
                  type="button"
                  onClick={onRetry}
                  disabled={loading}
                  className="mt-1.5 text-xs font-semibold underline underline-offset-2 disabled:cursor-wait disabled:opacity-60"
                >
                  {loading ? t.retrying : t.retry}
                </button>
              </div>
            </div>
          </div>
        )}
        {sorted.length === 0 && !loadError ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <MessagesSquare className="w-10 h-10 text-slate-600 mb-3" />
            <p className="text-sm font-semibold text-slate-100">{t.noChats}</p>
            <p className="text-xs text-slate-300 mt-1">{t.noChatsHint}</p>
          </div>
        ) : sorted.length > 0 ? (
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
        ) : null}
      </div>
    </div>
  );

  return (
    <>
      {/* ── Desktop sidebar (fixed) ── */}
      <aside className="hidden lg:flex flex-col w-64 xl:w-72 flex-shrink-0 h-screen sticky top-0 bg-slate-900 text-slate-100 overflow-hidden">
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
          <aside className="lg:hidden fixed left-0 top-0 h-full w-72 z-50 bg-slate-900 text-slate-100 shadow-2xl flex flex-col overflow-hidden animate-slide-in-left">
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
