'use client';

import Link from 'next/link';
import { ArrowLeft, BarChart3 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { fetchPublishedQuality } from '../../application/legal/services/qualityService';
import type { PublishedMetric, PublishedQuality, PublishedSuite } from '../../domain/legal/quality';
import type { SupportedLanguage } from '../../domain/legal/types';
import { qualityTranslations } from '../i18n/translations';
import {
  LanguageSelect, QualityShell, chipClass, linkButtonClass, panelClass, rowClass, tableClass, tableHeadClass,
} from '../components/quality/QualityUI';

const LOWER_IS_BETTER = new Set(['forbidden_claim', 'unnecessary_abstention', 'ter']);
const SUITE_ORDER = ['legal_qa', 'retrieval', 'translation', 'stream'] as const;
type LoadState = { status: 'loading' } | { status: 'error' } | { status: 'ok'; data: PublishedQuality };

const percent = (value: number | null | undefined, locale: string) =>
  value === null || value === undefined ? 'n/a' : `${(value * 100).toLocaleString(locale, { maximumFractionDigits: 1 })} %`;

function MetricsTable({ metrics, language, locale }: { metrics: Record<string, PublishedMetric>; language: SupportedLanguage; locale: string }) {
  const t = qualityTranslations[language];
  const labels = t.metrics as Record<string, string>;
  return (
    <table className={tableClass}>
      <thead className={tableHeadClass}>
        <tr>
          <th scope="col" className="py-2 pr-2 font-semibold">{t.metricHeader}</th>
          <th scope="col" className="py-2 pr-2 font-semibold">{t.macroHeader}</th>
          <th scope="col" className="py-2 pr-2 font-semibold">{t.microHeader}</th>
          <th scope="col" className="py-2 font-semibold">{t.casesHeader}</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(metrics).map(([name, metric]) => (
          <tr key={name} className={rowClass}>
            <th scope="row" className="py-2 pr-2 font-normal text-zinc-200">
              {labels[name] ?? name}
              {LOWER_IS_BETTER.has(name) && <span className="ml-1 text-xs text-zinc-500">({t.lowerIsBetter})</span>}
            </th>
            <td className="py-2 pr-2 font-mono text-zinc-100">{percent(metric.macro, locale)}</td>
            <td className="py-2 pr-2 font-mono text-zinc-400">{percent(metric.micro, locale)}</td>
            <td className="py-2 font-mono text-zinc-400">{metric.n}</td>
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
    <section aria-labelledby={`suite-${id}`} className={panelClass}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={`suite-${id}`} className="text-lg font-semibold text-white">{names[id] ?? id}</h2>
        <span data-measured={suite.measured} className={chipClass(suite.measured ? 'success' : 'neutral')}>
          {suite.measured ? t.measured : t.notMeasured}
        </span>
      </div>
      {!suite.measured && <p className="mt-2 text-sm text-zinc-400">{suite.reason}</p>}
      {suite.measured && suite.note && <p className="mt-2 text-sm text-amber-200">{suite.note}</p>}
      {suite.measured && suite.n_cases !== undefined && <p className="mt-1 text-xs text-zinc-500">{t.cases(suite.n_cases)}</p>}
      {suite.measured && suite.metrics && <MetricsTable metrics={suite.metrics} language={language} locale={locale} />}
      {suite.measured && suite.systems &&
        Object.entries(suite.systems).map(([system, metrics]) => (
          <div key={system} className="mt-4">
            <h3 className="text-sm font-semibold text-indigo-300">{systems[system] ?? system}</h3>
            <MetricsTable metrics={metrics as Record<string, PublishedMetric>} language={language} locale={locale} />
          </div>
        ))}
      {suite.measured && suite.n_streams !== undefined && suite.metrics === undefined && suite.systems === undefined && (
        <p className="mt-2 text-sm text-zinc-300">{t.cases(suite.n_streams)}</p>
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
    <QualityShell
      icon={<BarChart3 className="h-5 w-5" />}
      title={t.title}
      subtitle={t.subtitle}
      actions={
        <>
          <Link href="/" className={linkButtonClass}><ArrowLeft aria-hidden="true" className="h-4 w-4" />{t.backToChat}</Link>
          <LanguageSelect value={language} onChange={setLanguage} label={t.language} />
        </>
      }
    >
      {state.status === 'loading' && <p role="status" className="text-sm text-zinc-400">{t.loading}</p>}
      {state.status === 'error' && (
        <div role="alert" className="rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-red-200">
          <p>{t.error}</p>
          <button type="button" onClick={load} className="mt-3 rounded-xl bg-indigo-600 px-4 py-1.5 text-sm font-semibold text-white transition-all hover:bg-indigo-500">{t.retry}</button>
        </div>
      )}

      {data && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span data-status={data.status} className={chipClass('warning')}>
              {t.status[data.status]}
            </span>
            {data.sha && <span className="font-mono text-xs text-zinc-500">{t.version(data.sha.slice(0, 10), Boolean(data.dirty))}</span>}
            {data.generated_at && <span className="text-xs text-zinc-500">{t.generatedAt(new Date(data.generated_at).toLocaleDateString(locale))}</span>}
          </div>
          <section aria-label={t.noticesTitle} className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5 backdrop-blur-xl">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-amber-300">{t.noticesTitle}</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-100/90">
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
    </QualityShell>
  );
}
