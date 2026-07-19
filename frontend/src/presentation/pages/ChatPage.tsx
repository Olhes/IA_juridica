'use client';

import { Compass, MessageSquare, ShieldCheck, Sparkles } from 'lucide-react';
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

const landingI18n = {
  spanish: {
    badge: 'Asistente legal bilingue',
    title: 'Orientacion legal clara para actuar hoy',
    description:
      'Consulta sobre violencia familiar, pension de alimentos, medidas de proteccion y procesos legales en Peru. IA Juridica te guia paso a paso con lenguaje simple.',
    ctaPrimary: 'Comenzar consulta',
    ctaSecondary: 'Ver temas frecuentes',
    sectionTitle: 'Como te ayudamos',
    bullets: [
      { Icon: ShieldCheck, text: 'Respuestas estructuradas con pasos recomendados.' },
      { Icon: Compass, text: 'Orientacion por idioma: espanol y quechua.' },
      { Icon: MessageSquare, text: 'Flujo de chat rapido para resolver tu caso.' },
    ],
  },
  quechua: {
    badge: 'Iskay simipi yanapaq legal',
    title: 'Kunan punchawpi ruray atina legal orientacion',
    description:
      'Llakichikuy, alimentos, proteccion, proceso legal Peru suyumanta tapukuy. IA Juridicaqa sutinchasqa simipi pusasunki, paso paso.',
    ctaPrimary: 'Tapukuyta qallariy',
    ctaSecondary: 'Sapa kuti tapukuykunata qhaway',
    sectionTitle: 'Imaynatam yanapasunki',
    bullets: [
      { Icon: ShieldCheck, text: 'Ordenasqa kutichiykunawan, paso rekomendasqa.' },
      { Icon: Compass, text: 'Iskay simi yanapay: espanol, quechua.' },
      { Icon: MessageSquare, text: 'Utqay chat puriy, kasuyki allinta hamutananpaq.' },
    ],
  },
} as const;

export function ChatPage() {
  const [language, setLanguage] = useState<SupportedLanguage>('spanish');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showLanding, setShowLanding] = useState(true);

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
    loading: sessionsLoading,
    sessionsLoadError,
    setActiveSessionId,
    createSession,
    updateSessionMeta,
    deleteSession,
    reloadSessions,
  } = useChatSessions();

  // NO crear sesión automáticamente - esperar a que el usuario haga clic en "Nueva consulta"

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

  const t = landingI18n[language];

  const focusChatInput = () => {
    const input = document.getElementById('chat-input') as HTMLTextAreaElement | null;
    input?.focus();
    input?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleNewSession = async () => {
    await createSession(language);
    setShowLanding(false);
    setSidebarOpen(false);
  };

  const handleSelectSession = (id: string) => {
    setActiveSessionId(id);
    setShowLanding(false);
    setSidebarOpen(false);
  };

  const handleStartChat = () => {
    setShowLanding(false);
    requestAnimationFrame(() => {
      focusChatInput();
    });
  };

  const showLandingScreen = showLanding && messages.length === 0;

  return (
    <div className="flex h-screen overflow-hidden bg-gradient-to-br from-slate-50 via-indigo-50/30 to-violet-50/20 dark:bg-none dark:bg-gray-950 transition-colors duration-300">

      {/* ── Sidebar ── */}
      <ChatSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        language={language}
        isOpen={sidebarOpen}
        loading={sessionsLoading}
        loadError={sessionsLoadError}
        onClose={() => setSidebarOpen(false)}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
        onDeleteSession={deleteSession}
        onRetry={reloadSessions}
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
            {showLandingScreen ? (
              <section className="px-4 md:px-8 py-10 md:py-14 animate-fade-in">
                <div className="relative overflow-hidden rounded-3xl border border-indigo-100 dark:border-indigo-900/60 bg-white/85 dark:bg-gray-900/90 shadow-xl shadow-indigo-100/40 dark:shadow-black/20 p-6 md:p-10">
                  <div className="absolute -top-20 -right-20 w-56 h-56 rounded-full bg-indigo-500/10 blur-3xl" />
                  <div className="absolute -bottom-24 -left-20 w-64 h-64 rounded-full bg-violet-500/10 blur-3xl" />

                  <div className="relative">
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-900">
                      <Sparkles className="w-3.5 h-3.5" />
                      {t.badge}
                    </span>

                    <h1 className="mt-4 text-3xl md:text-5xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 leading-tight">
                      {t.title}
                    </h1>
                    <p className="mt-4 text-sm md:text-base text-slate-600 dark:text-slate-300 max-w-2xl leading-relaxed">
                      {t.description}
                    </p>

                    <div className="mt-7 flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={handleStartChat}
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-all"
                      >
                        <MessageSquare className="w-4 h-4" />
                        {t.ctaPrimary}
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setShowLanding(false);
                          requestAnimationFrame(() => {
                            bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                          });
                        }}
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold border border-slate-300 dark:border-gray-700 bg-white/70 dark:bg-gray-900 text-slate-700 dark:text-slate-200 hover:border-indigo-400 dark:hover:border-indigo-600 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors"
                      >
                        <Compass className="w-4 h-4" />
                        {t.ctaSecondary}
                      </button>
                    </div>

                    <div className="mt-8">
                      <p className="text-xs uppercase tracking-widest text-slate-400 dark:text-slate-500 font-semibold mb-3">
                        {t.sectionTitle}
                      </p>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        {t.bullets.map(({ Icon, text }) => (
                          <div
                            key={text}
                            className="rounded-2xl border border-slate-200 dark:border-gray-800 bg-slate-50/70 dark:bg-gray-950/60 px-4 py-3"
                          >
                            <Icon className="w-4 h-4 text-indigo-600 dark:text-indigo-400 mb-2" />
                            <p className="text-sm text-slate-700 dark:text-slate-300">{text}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </section>
            ) : messages.length === 0 ? (
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
