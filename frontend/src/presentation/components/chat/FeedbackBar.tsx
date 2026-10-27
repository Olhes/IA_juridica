'use client';

import { ThumbsDown, ThumbsUp } from 'lucide-react';
import { useId, useState } from 'react';
import type { FeedbackPayload, FeedbackReason } from '../../../domain/legal/quality';
import type { SupportedLanguage } from '../../../domain/legal/types';
import { feedbackTranslations } from '../../i18n/translations';

const REASONS: FeedbackReason[] = ['incorrecta', 'incompleta', 'sin_fuentes', 'mala_traduccion', 'confusa', 'otro'];

type Phase = 'idle' | 'reason' | 'done' | 'error';

interface FeedbackBarProps {
  language: SupportedLanguage;
  requestId: string;
  context: Pick<FeedbackPayload, 'evidence_status' | 'translation_quality'>;
  onSubmit: (payload: Omit<FeedbackPayload, 'request_id' | 'language' | 'conversation_id'>) => Promise<{ ok: boolean; queued: boolean }>;
}

/** 👍/👎 con motivo. El texto de la consulta solo se comparte si la persona lo autoriza expresamente. */
export function FeedbackBar({ language, requestId, context, onSubmit }: FeedbackBarProps) {
  const t = feedbackTranslations[language];
  const groupId = useId();
  const [phase, setPhase] = useState<Phase>('idle');
  const [sending, setSending] = useState(false);
  const [reason, setReason] = useState<FeedbackReason | ''>('');
  const [comment, setComment] = useState('');
  const [share, setShare] = useState(false);
  const [queued, setQueued] = useState(false);

  const submit = async (rating: 'up' | 'down') => {
    setSending(true);
    const result = await onSubmit({
      rating,
      ...(rating === 'down' ? { reason: reason as FeedbackReason, comment: comment.trim() || undefined, share_text: share } : {}),
      ...context,
    });
    setSending(false);
    setQueued(result.queued);
    setPhase(result.ok ? 'done' : 'error');
  };

  if (phase === 'done') {
    return (
      <p role="status" data-request-id={requestId} className="mt-3 text-xs text-emerald-300">
        {queued ? t.thanksQueued : t.thanks}
      </p>
    );
  }

  return (
    <section aria-label={t.question} data-request-id={requestId} className="mt-3 text-xs text-zinc-300">
      <div className="flex flex-wrap items-center gap-2">
        <span>{t.question}</span>
        <button type="button" aria-label={t.up} disabled={sending} onClick={() => submit('up')}
          className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2 py-1 hover:bg-zinc-800 disabled:opacity-50">
          <ThumbsUp className="w-3 h-3" aria-hidden="true" />
          {t.up}
        </button>
        <button type="button" aria-label={t.down} aria-expanded={phase === 'reason'} disabled={sending}
          onClick={() => setPhase(phase === 'reason' ? 'idle' : 'reason')}
          className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2 py-1 hover:bg-zinc-800 disabled:opacity-50">
          <ThumbsDown className="w-3 h-3" aria-hidden="true" />
          {t.down}
        </button>
      </div>
      {phase === 'error' && <p role="alert" className="mt-2 text-red-300">{t.error}</p>}
      {(phase === 'reason' || phase === 'error') && (
        <form
          className="mt-2 space-y-2 rounded-lg border border-zinc-800 bg-zinc-950/60 p-3"
          onSubmit={(event) => { event.preventDefault(); if (reason) void submit('down'); }}
        >
          <fieldset>
            <legend className="font-semibold text-zinc-200">{t.reasonLabel}</legend>
            <div className="mt-1 grid gap-1 sm:grid-cols-2">
              {REASONS.map((value) => (
                <label key={value} className="flex items-center gap-2">
                  <input type="radio" name={`${groupId}-reason`} value={value} checked={reason === value} onChange={() => setReason(value)} />
                  {t.reasons[value]}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="block">
            <span className="text-zinc-400">{t.commentLabel}</span>
            <textarea value={comment} maxLength={500} rows={2} onChange={(event) => setComment(event.target.value)}
              className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-900 p-2 text-zinc-100" />
          </label>
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={share} onChange={(event) => setShare(event.target.checked)} className="mt-0.5" />
            <span>{t.share}</span>
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={!reason || sending}
              className="rounded-md bg-indigo-600 px-3 py-1 font-semibold text-white disabled:opacity-40">{t.send}</button>
            <button type="button" onClick={() => setPhase('idle')} className="rounded-md border border-zinc-700 px-3 py-1">{t.cancel}</button>
          </div>
        </form>
      )}
    </section>
  );
}
