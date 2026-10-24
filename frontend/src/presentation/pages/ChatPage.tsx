'use client';

import { Compass, MessageSquare, ShieldCheck, Sparkles } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useChat } from '../../application/legal/use-cases/useChat';
import { useChatSessions } from '../../application/legal/use-cases/useChatSessions';
import { useAuth } from '../components/AuthProvider';
import { sendFeedback } from '../../application/legal/services/qualityService';
import { AuthModal } from '../components/AuthModal';
import type { SupportedLanguage } from '../../domain/legal/types';
import { ChatHeader } from '../components/chat/ChatHeader';
import { ChatSidebar, SidebarToggleButton } from '../components/sidebar/ChatSidebar';
import { SandAnimation } from '../components/SandAnimation';
import { FloatingRadialHub } from '../components/FloatingRadialHub';
import { TerminalModal, type TerminalMessage } from '../components/TerminalModal';
import { HistoryPanel } from '../components/HistoryPanel';
import { useSpeechToText } from '../../application/legal/use-cases/useSpeech';

const LANGUAGE_KEY = 'preferredLanguage';
const ANIMATION_COMPLETE_KEY = 'animationComplete';

interface Point {
  x: number;
  y: number;
  originX: number;
  originY: number;
  closest?: Point[];
}

const landingI18n = {
  spanish: {
    badge: 'Asistente legal bilingüe',
    title: 'Orientación legal clara para actuar hoy',
    description:
      'Consulta sobre violencia familiar, pensión de alimentos, medidas de protección y procesos legales en Perú. IA Jurídica te guía paso a paso con lenguaje simple.',
    ctaPrimary: 'Comenzar consulta',
    ctaSecondary: 'Ver temas frecuentes',
    sectionTitle: 'Cómo te ayudamos',
    bullets: [
      { Icon: ShieldCheck, text: 'Respuestas estructuradas con pasos recomendados.' },
      { Icon: Compass, text: 'Orientación por idioma: español y quechua.' },
      { Icon: MessageSquare, text: 'Flujo de chat rápido para resolver tu caso.' },
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
  const router = useRouter();
  const { isAuthenticated, mounted } = useAuth();
  
  const [language, setLanguage] = useState<SupportedLanguage>('spanish');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showLanding, setShowLanding] = useState(true);
  const [animationComplete, setAnimationComplete] = useState(false);

  const [terminalOpen, setTerminalOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [terminalMessages, setTerminalMessages] = useState<TerminalMessage[]>([]);
  const [isUploadingDocument, setIsUploadingDocument] = useState(false);
  const [uploadingFileName, setUploadingFileName] = useState<string | null>(null);
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [voiceInput, setVoiceInput] = useState('');

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const terminalButtonRef = useRef<HTMLButtonElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Voice-to-text hook (solo español)
  const { supported: voiceSupported, listening: voiceListening, start: voiceStart, stop: voiceStop } = useSpeechToText(
    (spoken) => setVoiceInput((prev) => ((prev ? prev + ' ' : '') + spoken).slice(0, 800)),
  );

  useEffect(() => {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (saved === 'spanish' || saved === 'quechua') setLanguage(saved);

    // Comentado temporalmente para que la animación siempre se muestre durante desarrollo
    // const savedAnimation = localStorage.getItem(ANIMATION_COMPLETE_KEY);
    // if (savedAnimation === 'true') {
    //   setAnimationComplete(true);
    // }

    // SIEMPRE mostrar la animación en desarrollo
    setAnimationComplete(false);
  }, []);

  const handleLanguageChange = (lang: SupportedLanguage) => {
    setLanguage(lang);
    localStorage.setItem(LANGUAGE_KEY, lang);
  };

  // ── Red Neuronal / Partículas en Fondo Global de ChatPage ────────────────
  useEffect(() => {
    if (!animationComplete || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    window.addEventListener('resize', handleResize);

    const points: Point[] = [];
    const stepX = width / 14;
    const stepY = height / 14;

    for (let x = 0; x < width; x += stepX) {
      for (let y = 0; y < height; y += stepY) {
        const px = x + Math.random() * (stepX * 0.8);
        const py = y + Math.random() * (stepY * 0.8);
        points.push({ x: px, originX: px, y: py, originY: py });
      }
    }

    const getDistance = (p1: { x: number; y: number }, p2: { x: number; y: number }) => {
      return Math.pow(p1.x - p2.x, 2) + Math.pow(p1.y - p2.y, 2);
    };

    for (let i = 0; i < points.length; i++) {
      const closest: Point[] = [];
      const p1 = points[i];
      for (let j = 0; j < points.length; j++) {
        const p2 = points[j];
        if (p1 !== p2) {
          let placed = false;
          for (let k = 0; k < 5; k++) {
            if (!placed && closest[k] === undefined) {
              closest[k] = p2;
              placed = true;
            }
          }
          for (let k = 0; k < 5; k++) {
            if (!placed && getDistance(p1, p2) < getDistance(p1, closest[k])) {
              closest[k] = p2;
              placed = true;
            }
          }
        }
      }
      p1.closest = closest;
    }

    const shiftPoint = (p: Point) => {
      const targetX = p.originX - 35 + Math.random() * 70;
      const targetY = p.originY - 35 + Math.random() * 70;
      const duration = 2500 + Math.random() * 2500;
      const startX = p.x;
      const startY = p.y;
      const startTime = performance.now();

      const animateShift = (now: number) => {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const ease = 0.5 - Math.cos(progress * Math.PI) / 2;

        p.x = startX + (targetX - startX) * ease;
        p.y = startY + (targetY - startY) * ease;

        if (progress < 1) {
          requestAnimationFrame(animateShift);
        } else {
          shiftPoint(p);
        }
      };

      requestAnimationFrame(animateShift);
    };

    points.forEach((p) => shiftPoint(p));

    const animate = () => {
      ctx.clearRect(0, 0, width, height);

      for (let i = 0; i < points.length; i++) {
        const p = points[i];

        if (p.closest) {
          for (let j = 0; j < p.closest.length; j++) {
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p.closest[j].x, p.closest[j].y);
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
            ctx.lineWidth = 0.75;
            ctx.stroke();
          }
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, 1.8, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
        ctx.fill();
      }

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, [animationComplete]);

  // ── Sesiones ───────────────────────────────────────────────────────────────
  const {
    sessions,
    activeSessionId,
    loading: sessionsLoading,
    sessionsLoadError,
    setActiveSessionId,
    createSession,
    updateSessionMeta,
    deleteSession,
    reloadSessions,
  } = useChatSessions();

  const onSessionUpdated = useCallback(
    (patch: { title?: string; preview?: string; messageCount?: number }) => {
      if (activeSessionId) updateSessionMeta(activeSessionId, patch);
    },
    [activeSessionId, updateSessionMeta]
  );

  // ── Hook del chat ─────────────────────────────────────────────────────────
  const {
    messages,
    isLoading,
    isOnline,
    sendQuery,
    retry,
    checkHealth,
  } = useChat({ sessionId: activeSessionId, language, onSessionUpdated });

  useEffect(() => { checkHealth(); }, [checkHealth]);

  useEffect(() => {
      const formatted = messages.map((m) => ({
        id: m.id,
        content: m.content || m.streamingContent || '',
        isUser: m.role === 'user',
        isStreaming: m.isStreaming,
        degraded: m.degraded,
        stage: m.stage,
        completedStages: m.completedStages,
        errorInfo: m.errorInfo,
        timings: m.apiResponse?.metadata?.timings,
        apiResponse: m.apiResponse,
        requestId: m.requestId,
      }));
      setTerminalMessages(formatted);
  }, [messages]);

  const t = landingI18n[language];

  // ── Handlers ───────────────────────────────────────────────────────────────
  const handleNewSession = async () => {
    if (!isAuthenticated) {
      setAuthModalOpen(true);
      return;
    }
    await createSession(language);
    setShowLanding(false);
    setSidebarOpen(false);
    setTerminalOpen(true);
  };

  const handleSelectSession = (id: string) => {
    if (!isAuthenticated) {
      setAuthModalOpen(true);
      return;
    }
    setActiveSessionId(id);
    setShowLanding(false);
    setSidebarOpen(false);
    setTerminalOpen(true);
  };

  const handleStartChat = () => { void handleNewSession(); };

  const handleSendTerminalMessage = async (message: string) => {
    if (!isAuthenticated) {
      setAuthModalOpen(true);
      return;
    }
    setShowLanding(false);

    // Si hay un archivo adjunto, procesarlo primero
    if (attachedFile) {
      setIsUploadingDocument(true);
      setUploadingFileName(attachedFile.name);

      try {
        const { apiService } = await import('../../application/legal/services/apiService');
        const result = await apiService.queryDocument(attachedFile, message, language);

        if (result.success && result.data) {
          // Mostrar el documento en el chat como attachment
          const userMessage = message || `[Documento: ${attachedFile.name}]`;
          sendQuery(userMessage);
        } else {
          console.error('Error al procesar documento:', result.error);
        }
      } catch (error) {
        console.error('Error al procesar documento:', error);
      } finally {
        setIsUploadingDocument(false);
        setUploadingFileName(null);
        setAttachedFile(null); // Limpiar el attachment después de procesar
      }
    } else {
      // Solo enviar el mensaje si no hay archivo adjunto
      sendQuery(message);
    }
  };

  const handleRemoveAttachment = () => {
    setAttachedFile(null);
  };

  const handleCameraOpen = () => {
    if (!isAuthenticated) {
      setAuthModalOpen(true);
      return;
    }
  };

  const handleMicToggle = () => {
    if (!isAuthenticated) {
      setAuthModalOpen(true);
      return;
    }
    if (language !== 'spanish') {
      alert('Voz solo disponible en español');
      return;
    }
    if (voiceListening) voiceStop();
    else voiceStart();
  };

  const handleFileUpload = () => {
    if (!isAuthenticated) {
      setAuthModalOpen(true);
      return;
    }
    // Abrir el selector de archivos
    fileInputRef.current?.click();
  };

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Verificar tipo de archivo
    const validTypes = [
      'application/pdf',
      'image/png',
      'image/jpeg',
      'image/jpg',
      'image/tiff',
      'image/webp',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    ];

    if (!validTypes.includes(file.type)) {
      console.error('Formato no soportado:', file.type);
      return;
    }

    // Verificar tamaño (max 50MB)
    if (file.size > 50 * 1024 * 1024) {
      console.error('Archivo demasiado grande:', file.size);
      return;
    }

    // Verificar si hay una sesión activa
    if (!activeSessionId) {
      // Crear nueva sesión si no hay ninguna
      await createSession(language);
      setShowLanding(false);
      setTerminalOpen(true);
    }

    // Almacenar el archivo como adjunto sin procesar
    setAttachedFile(file);

    // Limpiar el input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/auth/google`;
  };

  const showLandingScreen = showLanding && messages.length === 0;
  const showAnimation = showLandingScreen && !animationComplete;

  return (
    <div className={`relative flex h-screen overflow-hidden transition-colors duration-300 ${
      showAnimation 
        ? 'bg-transparent' 
        : 'bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 text-slate-100'
    }`}>

      {/* Canvas Neuronal Global de Fondo */}
      {animationComplete && (
        <canvas
          ref={canvasRef}
          className="fixed inset-0 pointer-events-none z-0 opacity-90"
        />
      )}

      {/* Sand Animation */}
      {showAnimation && <SandAnimation onComplete={() => {
        setAnimationComplete(true);
        localStorage.setItem(ANIMATION_COMPLETE_KEY, 'true');
      }} />}

      {!showAnimation && (
        <>
          {/* Sidebar */}
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

          {/* Área Principal */}
          <div className="relative z-10 flex flex-col flex-1 min-w-0 overflow-hidden">
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

            <main className="flex-1 flex items-center justify-center p-4">
              {isUploadingDocument ? (
                <div className="flex flex-col items-center gap-4 p-8 rounded-2xl border border-white/10 bg-slate-900/60 backdrop-blur-xl shadow-2xl">
                  <div className="relative w-16 h-16">
                    <div className="absolute inset-0 border-4 border-indigo-500/30 rounded-full"></div>
                    <div className="absolute inset-0 border-4 border-indigo-500 rounded-full border-t-transparent animate-spin"></div>
                  </div>
                  <div className="text-center">
                    <p className="text-white font-semibold">Procesando documento</p>
                    <p className="text-sm text-slate-300 mt-1">{uploadingFileName}</p>
                    <p className="text-xs text-slate-400 mt-2">Esto puede tomar unos minutos...</p>
                  </div>
                </div>
              ) : showLandingScreen ? (
                <section className="max-w-3xl w-full p-8 rounded-3xl border border-white/10 bg-slate-900/60 backdrop-blur-xl shadow-2xl">
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                    <Sparkles className="w-3.5 h-3.5" />
                    {t.badge}
                  </span>

                  <h1 className="mt-4 text-3xl md:text-5xl font-extrabold tracking-tight leading-tight text-white">
                    {t.title}
                  </h1>
                  <p className="mt-4 text-sm md:text-base text-slate-300 leading-relaxed">
                    {t.description}
                  </p>

                  <div className="mt-6 flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={handleStartChat}
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg transition-all"
                    >
                      <MessageSquare className="w-4 h-4" />
                      {t.ctaPrimary}
                    </button>
                  </div>
                </section>
              ) : !terminalOpen ? (
                <button
                  onClick={() => setTerminalOpen(true)}
                  className="px-6 py-3 bg-indigo-600/80 hover:bg-indigo-600 text-white rounded-2xl shadow-xl backdrop-blur-md border border-white/10 flex items-center gap-2 font-medium transition-all hover:scale-105"
                >
                  <Sparkles className="w-4 h-4" />
                  Abrir Ventana de Consulta
                </button>
              ) : null}
            </main>
          </div>
        </>
      )}

      {/* Floating Hub */}
      {animationComplete && (
        <FloatingRadialHub
          terminalButtonRef={terminalButtonRef}
          onTerminalOpen={() => setTerminalOpen(true)}
          onHistoryOpen={() => setHistoryOpen(true)}
          onFileUpload={handleFileUpload}
          onCameraOpen={handleCameraOpen}
          onMicToggle={handleMicToggle}
        />
      )}

      {/* Modal / Ventana Terminal */}
      <TerminalModal
        returnFocusRef={terminalButtonRef}
        isOpen={terminalOpen}
        onClose={() => setTerminalOpen(false)}
        onSend={handleSendTerminalMessage}
        messages={terminalMessages}
        isLoading={isLoading}
        attachedFile={attachedFile}
        onRemoveAttachment={handleRemoveAttachment}
        language={language}
        onRetry={retry}
        onFeedback={(payload) =>
          sendFeedback({ ...payload, language, conversation_id: activeSessionId ?? undefined })
        }
        voiceInput={voiceInput}
        onVoiceInputChange={setVoiceInput}
      />

      {/* Historial */}
      <HistoryPanel
        isOpen={historyOpen}
        onClose={() => setHistoryOpen(false)}
        sessions={sessions.map((s) => ({
          id: s.id,
          title: s.title || 'Sin título',
          preview: s.preview || '',
          timestamp: new Date(s.updatedAt || Date.now()),
        }))}
        onSelectSession={handleSelectSession}
        onDeleteSession={deleteSession}
      />

      {/* Modal de Autenticación */}
      <AuthModal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onGoogleLogin={handleGoogleLogin}
      />

      {/* Input de archivo oculto */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.tiff,.webp,.docx,.doc,.pptx,.ppt"
        onChange={handleFileSelected}
        className="hidden"
        aria-label="Subir documento"
      />
    </div>
  );
}
