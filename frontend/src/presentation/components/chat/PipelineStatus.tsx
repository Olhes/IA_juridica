'use client';

import { AlertCircle, CheckCircle2, Loader2, RotateCcw } from 'lucide-react';
import type {
  PipelineStage,
  ResponseTimings,
  StreamErrorInfo,
  SupportedLanguage,
} from '../../../domain/legal/types';
import { chatTranslations } from '../../i18n/translations';

type VisibleStep = 'retrieval' | 'generation' | 'validation' | 'translating';

/** Las dos traducciones (entrada y salida) se muestran como un solo paso. */
const toVisibleStep = (stage: PipelineStage): VisibleStep =>
  stage === 'translate_in' || stage === 'translate_out' ? 'translating' : stage;

interface StageProgressProps {
  language: SupportedLanguage;
  stage?: PipelineStage;
  completed?: PipelineStage[];
}

/** "Buscando en el corpus → Redactando → Verificando → Traduciendo" en vivo. */
export function StageProgress({ language, stage, completed = [] }: StageProgressProps) {
  const t = chatTranslations[language];
  const current = stage ? toVisibleStep(stage) : undefined;
  const finished = new Set(completed.map(toVisibleStep));
  const seenTranslation = current === 'translating' || finished.has('translating');
  const steps: VisibleStep[] = ['retrieval', 'generation', 'validation'];
  if (seenTranslation) steps.push('translating');
  return (
    <ol aria-label={t.stagesLabel} className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
      {steps.map((step, index) => {
        const active = step === current;
        const done = !active && finished.has(step);
        return (
          <li key={step} className="flex items-center gap-2" aria-current={active ? 'step' : undefined}>
            {index > 0 && <span aria-hidden="true">→</span>}
            <span className={`inline-flex items-center gap-1 ${active ? 'text-indigo-300' : done ? 'text-emerald-400' : ''}`}>
              {active && <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />}
              {done && <CheckCircle2 className="w-3 h-3" aria-hidden="true" />}
              {t.stageLabels[step]}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

interface StreamErrorCardProps {
  language: SupportedLanguage;
  error: StreamErrorInfo;
  onRetry?: () => void;
}

/** Error del stream traducido según su `code`; no repite texto técnico del servidor. */
export function StreamErrorCard({ language, error, onRetry }: StreamErrorCardProps) {
  const t = chatTranslations[language];
  const message = t.errors[error.code] ?? t.errors.DEFAULT;
  return (
    <div role="alert" className="mt-3 flex items-start gap-2 rounded-lg border border-red-900 bg-red-950/30 px-3 py-2 text-xs text-red-300">
      <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
      <div className="flex-1">
        <p className="font-semibold">{t.errorTitle}</p>
        <p>{message}</p>
        {error.retryable && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 inline-flex items-center gap-1 rounded-md bg-red-900/60 px-2.5 py-1 font-semibold text-red-100 hover:bg-red-800"
          >
            <RotateCcw className="w-3 h-3" aria-hidden="true" />
            {t.retry}
          </button>
        )}
      </div>
    </div>
  );
}

const formatSeconds = (ms: number) => (ms / 1000).toFixed(ms < 10_000 ? 1 : 0);

interface ResponseTimingProps {
  language: SupportedLanguage;
  timings: ResponseTimings;
}

/** "Respondió en X s" con desglose por etapa. */
export function ResponseTiming({ language, timings }: ResponseTimingProps) {
  const t = chatTranslations[language];
  const entries = Object.entries(timings.stages) as [PipelineStage, number][];
  return (
    <details className="mt-2 text-xs text-zinc-500">
      <summary className="cursor-pointer" aria-label={t.timingsDetail}>
        {timings.cache_hit ? t.answeredFromCache : t.answeredIn(formatSeconds(timings.total_ms))}
      </summary>
      {entries.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {entries.map(([name, ms]) => (
            <li key={name}>
              {t.timingStageLabels[name]}: {formatSeconds(ms)} s
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}
