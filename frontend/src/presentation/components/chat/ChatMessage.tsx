'use client';

import {
  AlertCircle,
  AlertTriangle,
  BookOpen,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Download,
  FileText,
  ListChecks,
  Phone,
  Scale,
  Shield,
  ShieldAlert,
  ShieldCheck,
  User,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';
import type {
  ChatMessage as ChatMessageType,
  GeneralLegalResponse,
  LegalQueryApiResponse,
  ValidationReport,
} from '../../../domain/legal/types';
import { MarkdownRenderer } from './MarkdownRenderer';

// ─── Icons ───────────────────────────────────────────────────────────────────

function BotIcon() {
  return (
    <div className="flex-shrink-0 w-9 h-9 rounded-full bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-md">
      <Scale className="w-5 h-5 text-white" />
    </div>
  );
}

function UserIcon() {
  return (
    <div className="flex-shrink-0 w-9 h-9 rounded-full bg-gradient-to-br from-slate-500 to-slate-700 dark:from-slate-600 dark:to-slate-800 flex items-center justify-center shadow-md">
      <User className="w-5 h-5 text-white" />
    </div>
  );
}

// ─── Validation badge ─────────────────────────────────────────────────────────

function ValidationBadge({ validation }: { validation: ValidationReport }) {
  const map = {
    passed:    { icon: <ShieldCheck className="w-4 h-4" />, label: 'Validado',          cls: 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-900' },
    warned:    { icon: <Shield className="w-4 h-4" />,      label: 'Con advertencias',  cls: 'bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-900' },
    corrected: { icon: <Shield className="w-4 h-4" />,      label: 'Auto-corregido',    cls: 'bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-900' },
    failed:    { icon: <ShieldAlert className="w-4 h-4" />, label: 'No validado',       cls: 'bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-400 border-red-200 dark:border-red-900' },
  };
  const { icon, label, cls } = map[validation.status];
  const pct = Math.round(validation.confidence_score * 100);
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${cls}`}>
      {icon}{label} · {pct}% confianza
    </span>
  );
}

// ─── Pasos recomendados ───────────────────────────────────────────────────────

function StepsPanel({ response }: { response: GeneralLegalResponse }) {
  if (!response.pasos_recomendados?.length) return null;
  return (
    <div className="mt-4 rounded-xl border border-indigo-100 dark:border-indigo-900/60 bg-indigo-50/60 dark:bg-indigo-950/30 p-4">
      <div className="flex items-center gap-2 mb-3">
        <ListChecks className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
        <span className="text-sm font-semibold text-indigo-800 dark:text-indigo-300">Pasos recomendados</span>
      </div>
      <ol className="space-y-3">
        {response.pasos_recomendados.map((step) => (
          <li key={step.paso} className="flex gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-indigo-600 dark:bg-indigo-700 text-white text-xs font-bold flex items-center justify-center mt-0.5">
              {step.paso}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-indigo-900 dark:text-indigo-200 font-medium">{step.descripcion}</p>
              {(step.lugar ?? step.plazo ?? step.documentos_requeridos?.length > 0) && (
                <div className="mt-1 flex flex-wrap gap-2">
                  {step.lugar && (
                    <span className="text-xs bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 px-2 py-0.5 rounded-full">📍 {step.lugar}</span>
                  )}
                  {step.plazo && (
                    <span className="text-xs bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 px-2 py-0.5 rounded-full">⏱ {step.plazo}</span>
                  )}
                  {step.documentos_requeridos?.map((doc) => (
                    <span key={doc} className="text-xs bg-white dark:bg-gray-800 border border-indigo-200 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 px-2 py-0.5 rounded-full">📄 {doc}</span>
                  ))}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

// ─── Recursos ────────────────────────────────────────────────────────────────

function ResourcesPanel({ response }: { response: GeneralLegalResponse }) {
  if (!response.recursos?.length) return null;
  return (
    <div className="mt-4 rounded-xl border border-emerald-100 dark:border-emerald-900/60 bg-emerald-50/60 dark:bg-emerald-950/20 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Phone className="w-4 h-4 text-emerald-700 dark:text-emerald-400" />
        <span className="text-sm font-semibold text-emerald-800 dark:text-emerald-300">Recursos de ayuda</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {response.recursos.map((r) => (
          <div key={r.nombre} className="bg-white dark:bg-gray-800 rounded-lg border border-emerald-200 dark:border-emerald-900 p-3 flex flex-col gap-1">
            <span className="text-sm font-semibold text-emerald-800 dark:text-emerald-300">{r.nombre}</span>
            {r.tipo && <span className="text-xs text-emerald-600 dark:text-emerald-500">{r.tipo}</span>}
            {r.contacto && <span className="text-sm font-bold text-emerald-700 dark:text-emerald-400 mt-1">📞 {r.contacto}</span>}
            {r.horario && <span className="text-xs text-slate-500 dark:text-slate-500">🕒 {r.horario}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Advertencias ────────────────────────────────────────────────────────────

function WarningsPanel({ response }: { response: GeneralLegalResponse }) {
  if (!response.advertencias?.length) return null;
  const urgencyColor = {
    bajo:    'bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300',
    medio:   'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-900 text-amber-700 dark:text-amber-400',
    alto:    'bg-orange-50 dark:bg-orange-950/30 border-orange-200 dark:border-orange-900 text-orange-700 dark:text-orange-400',
    critico: 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-900 text-red-700 dark:text-red-400',
  };
  return (
    <div className="mt-3 space-y-2">
      {response.advertencias.map((w, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: static list
        <div key={i} className={`rounded-lg border px-3 py-2 flex items-start gap-2 text-sm ${urgencyColor[w.urgencia]}`}>
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{w.mensaje}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Fuentes ─────────────────────────────────────────────────────────────────

function SourcesPanel({ apiResponse }: { apiResponse: LegalQueryApiResponse }) {
  if (!apiResponse.sources?.length && !apiResponse.response?.fuentes?.length) return null;
  const fuentes = apiResponse.response?.fuentes ?? [];
  return (
    <div className="mt-4 rounded-xl border border-slate-200 dark:border-gray-700 bg-slate-50/80 dark:bg-gray-800/50 p-3">
      <div className="flex items-center gap-2 mb-2">
        <BookOpen className="w-4 h-4 text-slate-500 dark:text-slate-400" />
        <span className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide">Fuentes legales</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {fuentes.map((f, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: static list
          <span key={i} className="inline-flex items-center gap-1 text-xs bg-white dark:bg-gray-700 border border-slate-200 dark:border-gray-600 text-slate-700 dark:text-slate-300 px-2.5 py-1 rounded-full">
            <FileText className="w-3 h-3" />{f.nombre}{f.numero ? ` — ${f.numero}` : ''}
          </span>
        ))}
        {apiResponse.sources.map((s) => (
          <span key={s} className="inline-flex items-center gap-1 text-xs bg-white dark:bg-gray-700 border border-slate-200 dark:border-gray-600 text-slate-500 dark:text-slate-400 px-2.5 py-1 rounded-full">
            <FileText className="w-3 h-3" />{s}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Full details collapsible ─────────────────────────────────────────────────

function FullDetails({
  apiResponse,
  onDownloadPdf,
  isDownloadingPdf,
}: {
  apiResponse: LegalQueryApiResponse;
  onDownloadPdf?: () => void;
  isDownloadingPdf?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors font-medium"
      >
        {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        {open ? 'Ocultar detalles' : 'Ver pasos, recursos y fuentes'}
      </button>

      {open && (
        <div className="mt-2 animate-fade-in">
          <StepsPanel response={apiResponse.response} />
          <ResourcesPanel response={apiResponse.response} />
          <WarningsPanel response={apiResponse.response} />
          <SourcesPanel apiResponse={apiResponse} />

          {onDownloadPdf && (
            <button
              type="button"
              onClick={onDownloadPdf}
              disabled={isDownloadingPdf}
              className="mt-4 flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isDownloadingPdf ? <Clock className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              {isDownloadingPdf ? 'Generando PDF…' : 'Descargar informe PDF'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Thinking skeleton ────────────────────────────────────────────────────────

function ThinkingBubble() {
  return (
    <div className="flex items-start gap-3 px-4 md:px-8">
      <BotIcon />
      <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-2xl rounded-tl-none px-5 py-4 shadow-sm max-w-xs">
        <div className="flex gap-1.5 items-center h-5">
          <span className="w-2 h-2 rounded-full bg-indigo-400 dark:bg-indigo-600 animate-bounce [animation-delay:0ms]" />
          <span className="w-2 h-2 rounded-full bg-indigo-400 dark:bg-indigo-600 animate-bounce [animation-delay:150ms]" />
          <span className="w-2 h-2 rounded-full bg-indigo-400 dark:bg-indigo-600 animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  );
}

// ─── Main ChatMessage ─────────────────────────────────────────────────────────

interface ChatMessageProps {
  message: ChatMessageType;
  onDownloadPdf?: (message: ChatMessageType) => void;
  isDownloadingPdf?: boolean;
  language: 'spanish' | 'quechua';
}

export function ChatMessage({ message, onDownloadPdf, isDownloadingPdf, language }: ChatMessageProps) {
  const isUser = message.role === 'user';

  if (!isUser && message.isStreaming === false && message.isLoadingFull && !message.content && !message.streamingContent) {
    return <ThinkingBubble />;
  }
  if (!isUser && message.isStreaming && !message.content && !message.streamingContent) {
    return <ThinkingBubble />;
  }

  const displayText = !isUser
    ? message.content || message.streamingContent || ''
    : message.content;

  // ── Burbuja usuario ──────────────────────────────────────────────
  if (isUser) {
    return (
      <div className="flex items-start gap-3 px-4 md:px-8 flex-row-reverse">
        <UserIcon />
        <div className="bg-gradient-to-br from-indigo-600 to-violet-600 text-white rounded-2xl rounded-tr-none px-5 py-3.5 shadow-md max-w-[85%] md:max-w-xl lg:max-w-2xl">
          <p className="text-sm md:text-base leading-relaxed whitespace-pre-wrap">{displayText}</p>
          <p className="text-xs text-indigo-200 mt-1.5 text-right">
            {message.timestamp.toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
      </div>
    );
  }

  // ── Burbuja error ────────────────────────────────────────────────
  if (message.error) {
    return (
      <div className="flex items-start gap-3 px-4 md:px-8">
        <BotIcon />
        <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded-2xl rounded-tl-none px-5 py-4 shadow-sm max-w-[85%] md:max-w-xl lg:max-w-2xl">
          <div className="flex items-center gap-2 mb-2">
            <XCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
            <span className="text-sm font-semibold text-red-700 dark:text-red-300">Error en la consulta</span>
          </div>
          <p className="text-sm text-red-600 dark:text-red-400">{message.error}</p>
        </div>
      </div>
    );
  }

  // ── Burbuja asistente ────────────────────────────────────────────
  const apiResp   = message.apiResponse;
  const validation = apiResp?.validation;
  const showValidationWarning = validation?.status === 'failed' || validation?.confidence === 'low';
  const respText =
    language === 'quechua'
      ? apiResp?.response?.respuesta_quechua || displayText
      : apiResp?.response?.respuesta_espanol || displayText;

  return (
    <div className="flex items-start gap-3 px-4 md:px-8">
      <BotIcon />
      <div className="bg-white dark:bg-gray-900 border border-slate-200 dark:border-gray-800 rounded-2xl rounded-tl-none px-5 py-4 shadow-sm max-w-[85%] md:max-w-xl lg:max-w-2xl">

        {/* Validation badge */}
        {validation && (
          <div className="mb-3"><ValidationBadge validation={validation} /></div>
        )}

        {/* Validation alerts */}
        {showValidationWarning && validation?.status === 'failed' && (
          <div className="mb-3 flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-lg px-3 py-2 text-xs text-red-700 dark:text-red-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>Esta respuesta no superó el umbral de validación. Consulta a un abogado o abogada.</span>
          </div>
        )}
        {showValidationWarning && validation?.confidence === 'low' && (
          <div className="mb-3 flex items-start gap-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 rounded-lg px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>Confianza baja. Usa esta orientación como punto de partida.</span>
          </div>
        )}

        {/* Markdown content */}
        <MarkdownRenderer content={respText} isStreaming={message.isStreaming} />

        {/* Full details */}
        {apiResp && !message.isStreaming && (
          <FullDetails
            apiResponse={apiResp}
            onDownloadPdf={onDownloadPdf ? () => onDownloadPdf(message) : undefined}
            isDownloadingPdf={isDownloadingPdf}
          />
        )}

        {/* Footer: cache badge + timestamp */}
        <div className="flex items-center justify-between mt-3">
          <div className="flex items-center gap-2">
            {apiResp?.cached && (
              <span className="text-xs bg-slate-100 dark:bg-gray-800 text-slate-500 dark:text-slate-400 px-2 py-0.5 rounded-full">
                💾 Desde caché
              </span>
            )}
            {validation?.corrections_applied ? (
              <span className="text-xs bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-900 px-2 py-0.5 rounded-full">
                <CheckCircle className="w-3 h-3 inline-block mr-0.5" />Revisado
              </span>
            ) : null}
          </div>
          <span className="text-xs text-slate-400 dark:text-slate-600">
            {message.timestamp.toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>

        {/* Loading full response */}
        {message.isLoadingFull && apiResp === undefined && (
          <div className="mt-3 flex items-center gap-2 text-xs text-slate-400 dark:text-slate-600">
            <Clock className="w-3.5 h-3.5 animate-spin" />
            Obteniendo validación y fuentes…
          </div>
        )}
      </div>
    </div>
  );
}
