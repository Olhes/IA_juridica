'use client';

import Link from 'next/link';
import { BarChart3, ShieldCheck } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { decideFeedback, fetchQualityOverview } from '../../application/legal/services/qualityService';
import type { QualityOverview } from '../../domain/legal/quality';
import type { SupportedLanguage } from '../../domain/legal/types';
import { useAuth } from '../components/AuthProvider';
import { qualityAdminTranslations, qualityTranslations } from '../i18n/translations';
import {
  LanguageSelect, QualityShell, chipClass, linkButtonClass, panelClass, rowClass, tableClass, tableHeadClass,
  type ChipTone,
} from '../components/quality/QualityUI';

type LoadState = { status: 'idle' } | { status: 'loading' } | { status: 'forbidden' } | { status: 'error' } | { status: 'ok'; overview: QualityOverview };

const number = (value: number | null | undefined) => (value === null || value === undefined ? 'n/a' : value.toLocaleString('es-PE', { maximumFractionDigits: 3 }));
const verdictTone: Record<'MEJORÓ' | 'IGUAL' | 'EMPEORÓ', ChipTone> = { 'MEJORÓ': 'success', IGUAL: 'neutral', 'EMPEORÓ': 'danger' };
const sectionTitle = 'text-lg font-semibold text-white';
const muted = 'mt-2 text-sm text-zinc-400';

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
    <QualityShell
      icon={<ShieldCheck className="h-5 w-5" />}
      title={t.title}
      actions={
        <>
          <Link href="/calidad" className={linkButtonClass}><BarChart3 aria-hidden="true" className="h-4 w-4" />{qualityTranslations[language].title}</Link>
          <LanguageSelect value={language} onChange={setLanguage} label="Idioma" />
        </>
      }
    >
      {children}
    </QualityShell>
  );

  if (!mounted) return shell(<p role="status" className="text-sm text-zinc-400">{t.loading}</p>);
  if (!isAuthenticated) {
    return shell(
      <div role="alert" className={panelClass}>
        <p className="text-zinc-200">{t.signIn}</p>
        <Link href="/login" className="mt-3 inline-flex rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg transition-all hover:bg-indigo-500">{t.login}</Link>
      </div>,
    );
  }
  if (!isAdmin || state.status === 'forbidden') {
    return shell(<p role="alert" className="rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-red-200">{t.restricted}</p>);
  }
  if (state.status === 'idle' || state.status === 'loading') return shell(<p role="status" className="text-sm text-zinc-400">{t.loading}</p>);
  if (state.status === 'error') {
    return shell(
      <div role="alert" className="rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-red-200">
        <p>{t.error}</p>
        <button type="button" onClick={() => void load()} className="mt-3 rounded-xl bg-indigo-600 px-4 py-1.5 text-sm font-semibold text-white transition-all hover:bg-indigo-500">{t.retry}</button>
      </div>,
    );
  }

  const { overview } = state;
  const { comparison, gold, feedback, stream } = overview;
  return shell(
    <>
      <section aria-labelledby="comparison" className={panelClass}>
        <h2 id="comparison" className={sectionTitle}>{t.comparisonTitle}</h2>
        {!comparison && <p className={muted}>{t.noComparison}</p>}
        {comparison && (
          <>
            <p className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              <span data-verdict={comparison.verdict} className={chipClass(verdictTone[comparison.verdict])}>{t.verdict[comparison.verdict]}</span>
              {comparison.blocking && <span className={chipClass('danger')}>{t.blocking}</span>}
              <span className="font-mono text-xs text-zinc-500">{comparison.base.ref} ({comparison.base.sha.slice(0, 8)}) → {comparison.head.ref} ({comparison.head.sha.slice(0, 8)})</span>
            </p>
            {!comparison.comparable && <p role="note" className="mt-2 text-sm text-amber-200">{t.notComparable}</p>}
            {comparison.blocks.length > 0 && (
              <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/5 p-3">
                <h3 className="text-sm font-semibold text-red-300">{t.blocksTitle}</h3>
                <ul className="mt-1 list-disc pl-5 text-sm text-zinc-200">
                  {comparison.blocks.map((block, index) => (
                    <li key={`${block.suite}-${block.kind}-${block.case_id ?? index}`}>{block.suite} · {block.kind}{block.case_id ? ` · ${block.case_id}` : ''}{block.stratum ? ` (${block.stratum})` : ''}</li>
                  ))}
                </ul>
              </div>
            )}
            {comparison.suites.map((suite) => (
              <table key={suite.suite} className={tableClass}>
                <caption className="pb-1 text-left text-xs font-semibold uppercase tracking-wide text-indigo-300">{suite.suite}</caption>
                <thead className={tableHeadClass}>
                  <tr><th scope="col" className="py-2">{t.metricHeader}</th><th scope="col">{t.baseHeader}</th><th scope="col">{t.headHeader}</th><th scope="col">{t.deltaHeader}</th><th scope="col">{t.statusHeader}</th></tr>
                </thead>
                <tbody>
                  {suite.metrics.map((metric) => (
                    <tr key={metric.metric} className={rowClass}>
                      <th scope="row" className="py-2 font-normal text-zinc-200">{metric.metric}</th>
                      <td className="font-mono">{number(metric.base)}</td><td className="font-mono">{number(metric.head)}</td><td className="font-mono">{number(metric.delta)}</td><td>{metric.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ))}
          </>
        )}
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section aria-labelledby="queues" className={panelClass}>
          <h2 id="queues" className={sectionTitle}>{t.queuesTitle}</h2>
          {gold.available ? (
            <ul className="mt-3 space-y-2 text-sm text-zinc-200">
              <li className="rounded-xl border border-white/5 bg-zinc-950/40 px-3 py-2">{t.lawyers(gold.pending_lawyers ?? 0)}</li>
              <li className="rounded-xl border border-white/5 bg-zinc-950/40 px-3 py-2">{t.natives(gold.pending_native_speakers ?? 0)}</li>
            </ul>
          ) : (
            <p className={muted}>{t.goldUnavailable}</p>
          )}
        </section>

        <section aria-labelledby="stream" className={panelClass}>
          <h2 id="stream" className={sectionTitle}>{t.streamTitle}</h2>
          {stream.n === 0 ? (
            <p className={muted}>{t.streamEmpty}</p>
          ) : (
            <table className={tableClass}>
              <thead className={tableHeadClass}><tr><th scope="col" className="py-2">{t.stageHeader}</th><th scope="col">p50</th><th scope="col">p95</th></tr></thead>
              <tbody>
                <tr className={rowClass}><th scope="row" className="py-2 font-normal text-zinc-200">{t.ttfb}</th><td className="font-mono">{number(stream.ttfb_ms.p50)}</td><td className="font-mono">{number(stream.ttfb_ms.p95)}</td></tr>
                {Object.entries(stream.stage_ms).map(([stage, value]) => (
                  <tr key={stage} className={rowClass}>
                    <th scope="row" className="py-2 font-normal text-zinc-200">{(t.stages as Record<string, string>)[stage] ?? stage}</th><td className="font-mono">{number(value.p50)}</td><td className="font-mono">{number(value.p95)}</td>
                  </tr>
                ))}
                <tr className={rowClass}><th scope="row" className="py-2 font-normal text-zinc-200">{t.total}</th><td className="font-mono">{number(stream.total_ms.p50)}</td><td className="font-mono">{number(stream.total_ms.p95)}</td></tr>
              </tbody>
            </table>
          )}
        </section>
      </div>

      <section aria-labelledby="feedback" className={panelClass}>
        <h2 id="feedback" className={sectionTitle}>{t.feedbackTitle}</h2>
        <p className="mt-1 text-sm text-zinc-300">{t.feedbackTotals(feedback.up, feedback.down)}</p>
        <h3 className="mt-4 text-sm font-semibold text-indigo-300">{t.feedbackQueueTitle}</h3>
        <p className="text-xs text-zinc-500">{t.acceptHint}</p>
        {overview.feedback_queue.length === 0 && <p className={muted}>{t.emptyQueue}</p>}
        <ul className="mt-3 space-y-3">
          {overview.feedback_queue.map((item) => (
            <li key={item.id} className="rounded-xl border border-white/10 bg-zinc-950/40 p-4 text-sm transition-all hover:border-indigo-500/40">
              <p className="font-semibold text-zinc-100">{item.query}</p>
              <p className="mt-1 text-zinc-400">{item.reason}{item.comment ? ` — ${item.comment}` : ''}</p>
              <div className="mt-3 flex gap-2">
                <button type="button" onClick={() => void decide(item.id, 'accept')} className="rounded-xl bg-indigo-600 px-3 py-1.5 font-semibold text-white transition-all hover:bg-indigo-500">{t.accept}</button>
                <button type="button" onClick={() => void decide(item.id, 'reject')} className="rounded-xl border border-white/10 px-3 py-1.5 text-zinc-300 transition-all hover:bg-zinc-800">{t.reject}</button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>,
  );
}
