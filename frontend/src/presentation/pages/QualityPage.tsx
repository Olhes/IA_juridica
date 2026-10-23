'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { fetchPublishedQuality } from '../../application/legal/services/qualityService';
import type { PublishedMetric, PublishedQuality, PublishedSuite } from '../../domain/legal/quality';
import type { SupportedLanguage } from '../../domain/legal/types';
import { qualityTranslations } from '../i18n/translations';

const LOWER_IS_BETTER = new Set(['forbidden_claim', 'unnecessary_abstention', 'ter']);
const SUITE_ORDER = ['legal_qa', 'retrieval', 'translation', 'stream'] as const;
type LoadState = { status: 'loading' } | { status: 'error' } | { status: 'ok'; data: PublishedQuality };

const percent = (value: number | null | undefined, locale: string) =>
  value === null || value === undefined ? 'n/a' : `${(value * 100).toLocaleString(locale, { maximumFractionDigits: 1 })} %`;

function MetricsTable({ metrics, language, locale }: { metrics: Record<string, PublishedMetric>; language: SupportedLanguage; locale: string }) {
  const t = qualityTranslations[language];
  const labels = t.metrics as Record<string, string>;
  return (
    <table className="mt-2 w-full text-left text-sm">
      <thead className="text-xs uppercase text-slate-400">
        <tr>
          <th scope="col" className="py-1 pr-2">{t.metricHeader}</th>
          <th scope="col" className="py-1 pr-2">{t.macroHeader}</th>
          <th scope="col" className="py-1 pr-2">{t.microHeader}</th>
          <th scope="col" className="py-1">{t.casesHeader}</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(metrics).map(([name, metric]) => (
          <tr key={name} className="border-t border-slate-800">
            <th scope="row" className="py-1 pr-2 font-normal">
              {labels[name] ?? name}
              {LOWER_IS_BETTER.has(name) && <span className="ml-1 text-xs text-slate-500">({t.lowerIsBetter})</span>}
            </th>
            <td className="py-1 pr-2">{percent(metric.macro, locale)}</td>
            <td className="py-1 pr-2">{percent(metric.micro, locale)}</td>
            <td className="py-1">{metric.n}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SuiteCard({ id, suite, language, locale }: { id: string; suite: PublishedSuite; language: SupportedLanguage; locale: string }) {
  const t = qualityTranslations[language];
  const names = t.suites as Record<string, string>;
  const systems = t.systems as Record<string, string>;
  return (
    <section aria-labelledby={`suite-${id}`} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={`suite-${id}`} className="text-lg font-semibold text-white">{names[id] ?? id}</h2>
        <span data-measured={suite.measured} className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${suite.measured ? 'border-emerald-800 text-emerald-300' : 'border-slate-700 text-slate-400'}`}>
          {suite.measured ? t.measured : t.notMeasured}
        </span>
      </div>
      {!suite.measured && <p className="mt-2 text-sm text-slate-400">{suite.reason}</p>}
      {suite.measured && suite.note && <p className="mt-2 text-sm text-amber-200">{suite.note}</p>}
      {suite.measured && suite.n_cases !== undefined && <p className="mt-1 text-xs text-slate-500">{t.cases(suite.n_cases)}</p>}
      {suite.measured && suite.metrics && <MetricsTable metrics={suite.metrics} language={language} locale={locale} />}
      {suite.measured && suite.systems &&
        Object.entries(suite.systems).map(([system, metrics]) => (
          <div key={system} className="mt-3">
            <h3 className="text-sm font-semibold text-slate-200">{systems[system] ?? system}</h3>
            <MetricsTable metrics={metrics as Record<string, PublishedMetric>} language={language} locale={locale} />
          </div>
        ))}
      {suite.measured && suite.n_streams !== undefined && suite.metrics === undefined && suite.systems === undefined && (
        <p className="mt-2 text-sm text-slate-300">{t.cases(suite.n_streams)}</p>
      )}
    </section>
  );
}

/** Página pública /calidad: las métricas publicadas, con lo medido y lo que aún no se midió. */
export function QualityPage() {
  const [language, setLanguage] = useState<SupportedLanguage>('spanish');
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const t = qualityTranslations[language];
  const locale = 'es-PE';

  const load = useCallback(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    fetchPublishedQuality(controller.signal)
      .then((data) => setState({ status: 'ok', data }))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== 'AbortError') setState({ status: 'error' });
      });
    return () => controller.abort();
  }, []);

  useEffect(() => load(), [load]);

  const data = state.status === 'ok' ? state.data : null;
  return (
    <main className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100">
      <div className="mx-auto max-w-4xl space-y-6">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-3xl font-extrabold">{t.title}</h1>
            <p className="mt-1 text-slate-400">{t.subtitle}</p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Link href="/" className="underline">{t.backToChat}</Link>
            <label className="flex items-center gap-1">
              <span className="sr-only">{t.language}</span>
              <select value={language} onChange={(event) => setLanguage(event.target.value as SupportedLanguage)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1">
                <option value="spanish">Español</option>
                <option value="quechua">Quechua</option>
              </select>
            </label>
          </div>
        </header>

        {state.status === 'loading' && <p role="status">{t.loading}</p>}
        {state.status === 'error' && (
          <div role="alert" className="rounded-lg border border-red-900 bg-red-950/40 p-4">
            <p>{t.error}</p>
            <button type="button" onClick={load} className="mt-2 rounded-md bg-red-900 px-3 py-1">{t.retry}</button>
          </div>
        )}

        {data && (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span data-status={data.status} className="rounded-full border border-amber-800 bg-amber-950/40 px-3 py-1 font-medium text-amber-200">
                {t.status[data.status]}
              </span>
              {data.sha && <span className="text-slate-500">{t.version(data.sha.slice(0, 10), Boolean(data.dirty))}</span>}
              {data.generated_at && <span className="text-slate-500">{t.generatedAt(new Date(data.generated_at).toLocaleDateString(locale))}</span>}
            </div>
            <section aria-label={t.noticesTitle} className="rounded-2xl border border-amber-900/60 bg-amber-950/20 p-4">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-300">{t.noticesTitle}</h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-100">
                {data.notices.map((notice) => <li key={notice}>{notice}</li>)}
              </ul>
            </section>
            <div className="grid gap-4">
              {SUITE_ORDER.filter((id) => data.suites[id]).map((id) => (
                <SuiteCard key={id} id={id} suite={data.suites[id]} language={language} locale={locale} />
              ))}
            </div>
          </>
        )}
      </div>
    </main>
  );
}

