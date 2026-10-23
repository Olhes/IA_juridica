'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { decideFeedback, fetchQualityOverview } from '../../application/legal/services/qualityService';
import type { QualityOverview } from '../../domain/legal/quality';
import type { SupportedLanguage } from '../../domain/legal/types';
import { useAuth } from '../components/AuthProvider';
import { qualityAdminTranslations } from '../i18n/translations';

type LoadState = { status: 'idle' } | { status: 'loading' } | { status: 'forbidden' } | { status: 'error' } | { status: 'ok'; overview: QualityOverview };

const number = (value: number | null | undefined) => (value === null || value === undefined ? 'n/a' : value.toLocaleString('es-PE', { maximumFractionDigits: 3 }));
const verdictTone = { 'MEJORÓ': 'border-emerald-800 text-emerald-300', IGUAL: 'border-slate-700 text-slate-300', 'EMPEORÓ': 'border-red-900 text-red-300' } as const;

/** /calidad/admin: solo rol admin. Regresiones entre commits, colas de revisión humana y feedback. */
export function QualityAdminPage() {
  const { isAuthenticated, mounted, user } = useAuth();
  const [language, setLanguage] = useState<SupportedLanguage>('spanish');
  const [state, setState] = useState<LoadState>({ status: 'idle' });
  const t = qualityAdminTranslations[language];
  const isAdmin = Boolean(user?.roles?.includes('admin'));

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    const result = await fetchQualityOverview();
    setState(result.status === 'ok' ? { status: 'ok', overview: result.overview } : { status: result.status });
  }, []);

  useEffect(() => {
    if (mounted && isAuthenticated && isAdmin) void load();
  }, [mounted, isAuthenticated, isAdmin, load]);

  const decide = async (id: string, decision: 'accept' | 'reject') => {
    if (await decideFeedback(id, decision)) await load();
  };

  const shell = (children: React.ReactNode) => (
    <main className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-3xl font-extrabold">{t.title}</h1>
          <label className="text-sm">
            <span className="sr-only">Idioma</span>
            <select value={language} onChange={(event) => setLanguage(event.target.value as SupportedLanguage)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1">
              <option value="spanish">Español</option>
              <option value="quechua">Quechua</option>
            </select>
          </label>
        </header>
        {children}
      </div>
    </main>
  );

  if (!mounted) return shell(<p role="status">{t.loading}</p>);
  if (!isAuthenticated) {
    return shell(
      <div role="alert" className="rounded-lg border border-slate-700 p-4">
        <p>{t.signIn}</p>
        <Link href="/login" className="mt-2 inline-block underline">{t.login}</Link>
      </div>,
    );
  }
  if (!isAdmin || state.status === 'forbidden') return shell(<p role="alert" className="rounded-lg border border-red-900 bg-red-950/40 p-4">{t.restricted}</p>);
  if (state.status === 'idle' || state.status === 'loading') return shell(<p role="status">{t.loading}</p>);
  if (state.status === 'error') {
    return shell(
      <div role="alert" className="rounded-lg border border-red-900 bg-red-950/40 p-4">
        <p>{t.error}</p>
        <button type="button" onClick={() => void load()} className="mt-2 rounded-md bg-red-900 px-3 py-1">{t.retry}</button>
      </div>,
    );
  }

  const { overview } = state;
  const { comparison, gold, feedback, stream } = overview;
  return shell(
    <>
      <section aria-labelledby="comparison" className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 id="comparison" className="text-lg font-semibold">{t.comparisonTitle}</h2>
        {!comparison && <p className="mt-2 text-sm text-slate-400">{t.noComparison}</p>}
        {comparison && (
          <>
            <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
              <span data-verdict={comparison.verdict} className={`rounded-full border px-3 py-1 font-semibold ${verdictTone[comparison.verdict]}`}>{t.verdict[comparison.verdict]}</span>
              {comparison.blocking && <span className="rounded-full border border-red-900 px-3 py-1 font-semibold text-red-300">{t.blocking}</span>}
              <span className="text-slate-500">{comparison.base.ref} ({comparison.base.sha.slice(0, 8)}) → {comparison.head.ref} ({comparison.head.sha.slice(0, 8)})</span>
            </p>
            {!comparison.comparable && <p role="note" className="mt-2 text-sm text-amber-200">{t.notComparable}</p>}
            {comparison.blocks.length > 0 && (
              <div className="mt-3">
                <h3 className="text-sm font-semibold text-red-300">{t.blocksTitle}</h3>
                <ul className="list-disc pl-5 text-sm">
                  {comparison.blocks.map((block, index) => (
                    <li key={`${block.suite}-${block.kind}-${block.case_id ?? index}`}>{block.suite} · {block.kind}{block.case_id ? ` · ${block.case_id}` : ''}{block.stratum ? ` (${block.stratum})` : ''}</li>
                  ))}
                </ul>
              </div>
            )}
            {comparison.suites.map((suite) => (
              <table key={suite.suite} className="mt-3 w-full text-left text-sm">
                <caption className="pb-1 text-left text-xs uppercase text-slate-400">{suite.suite}</caption>
                <thead className="text-xs text-slate-400">
                  <tr><th scope="col">{t.metricHeader}</th><th scope="col">{t.baseHeader}</th><th scope="col">{t.headHeader}</th><th scope="col">{t.deltaHeader}</th><th scope="col">{t.statusHeader}</th></tr>
                </thead>
                <tbody>
                  {suite.metrics.map((metric) => (
                    <tr key={metric.metric} className="border-t border-slate-800">
                      <th scope="row" className="py-1 font-normal">{metric.metric}</th>
                      <td>{number(metric.base)}</td><td>{number(metric.head)}</td><td>{number(metric.delta)}</td><td>{metric.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ))}
          </>
        )}
      </section>

      <section aria-labelledby="queues" className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 id="queues" className="text-lg font-semibold">{t.queuesTitle}</h2>
        {gold.available ? (
          <ul className="mt-2 list-disc pl-5 text-sm">
            <li>{t.lawyers(gold.pending_lawyers ?? 0)}</li>
            <li>{t.natives(gold.pending_native_speakers ?? 0)}</li>
          </ul>
        ) : (
          <p className="mt-2 text-sm text-slate-400">{t.goldUnavailable}</p>
        )}
      </section>

      <section aria-labelledby="feedback" className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 id="feedback" className="text-lg font-semibold">{t.feedbackTitle}</h2>
        <p className="mt-1 text-sm">{t.feedbackTotals(feedback.up, feedback.down)}</p>
        <h3 className="mt-3 text-sm font-semibold">{t.feedbackQueueTitle}</h3>
        <p className="text-xs text-slate-500">{t.acceptHint}</p>
        {overview.feedback_queue.length === 0 && <p className="mt-2 text-sm text-slate-400">{t.emptyQueue}</p>}
        <ul className="mt-2 space-y-3">
          {overview.feedback_queue.map((item) => (
            <li key={item.id} className="rounded-lg border border-slate-800 p-3 text-sm">
              <p className="font-semibold">{item.query}</p>
              <p className="mt-1 text-slate-400">{item.reason}{item.comment ? ` — ${item.comment}` : ''}</p>
              <div className="mt-2 flex gap-2">
                <button type="button" onClick={() => void decide(item.id, 'accept')} className="rounded-md bg-emerald-800 px-3 py-1">{t.accept}</button>
                <button type="button" onClick={() => void decide(item.id, 'reject')} className="rounded-md border border-slate-700 px-3 py-1">{t.reject}</button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="stream" className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 id="stream" className="text-lg font-semibold">{t.streamTitle}</h2>
        {stream.n === 0 ? (
          <p className="mt-2 text-sm text-slate-400">{t.streamEmpty}</p>
        ) : (
          <table className="mt-2 w-full text-left text-sm">
            <thead className="text-xs text-slate-400"><tr><th scope="col">{t.stageHeader}</th><th scope="col">p50</th><th scope="col">p95</th></tr></thead>
            <tbody>
              <tr className="border-t border-slate-800"><th scope="row" className="py-1 font-normal">{t.ttfb}</th><td>{number(stream.ttfb_ms.p50)}</td><td>{number(stream.ttfb_ms.p95)}</td></tr>
              {Object.entries(stream.stage_ms).map(([stage, value]) => (
                <tr key={stage} className="border-t border-slate-800">
                  <th scope="row" className="py-1 font-normal">{(t.stages as Record<string, string>)[stage] ?? stage}</th><td>{number(value.p50)}</td><td>{number(value.p95)}</td>
                </tr>
              ))}
              <tr className="border-t border-slate-800"><th scope="row" className="py-1 font-normal">{t.total}</th><td>{number(stream.total_ms.p50)}</td><td>{number(stream.total_ms.p95)}</td></tr>
            </tbody>
          </table>
        )}
      </section>
    </>,
  );
}
