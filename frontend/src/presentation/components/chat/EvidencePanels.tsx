'use client';

import { BadgeCheck, Phone, Scale, ShieldQuestion, TriangleAlert } from 'lucide-react';
import type { LegalQueryApiResponse, SupportedLanguage } from '../../../domain/legal/types';
import { chatTranslations } from '../../i18n/translations';

/** Tarjeta de evidencia insuficiente: el sistema se abstiene y ofrece recursos de ayuda. */
export function InsufficientEvidenceCard({ language }: { language: SupportedLanguage }) {
  const t = chatTranslations[language].insufficient;
  return (
    <section
      aria-label={t.title}
      className="mt-3 rounded-xl border border-amber-900/70 bg-amber-950/30 p-4 text-sm text-amber-100"
    >
      <h3 className="flex items-center gap-2 font-semibold">
        <ShieldQuestion className="w-4 h-4" aria-hidden="true" />
        {t.title}
      </h3>
      <p className="mt-1 text-amber-200/90">{t.body}</p>
      <h4 className="mt-3 text-xs font-semibold uppercase tracking-wide text-amber-300">{t.resourcesLabel}</h4>
      <ul className="mt-2 grid gap-2 sm:grid-cols-3">
        {t.resources.map((resource) => (
          <li key={resource.name} className="rounded-lg border border-amber-900/60 bg-zinc-950/60 p-3">
            <p className="font-semibold text-amber-100">{resource.name}</p>
            <p className="text-xs text-amber-200/80">{resource.detail}</p>
            <p className="mt-1 flex items-center gap-1 font-mono text-xs text-amber-300">
              <Phone className="w-3 h-3" aria-hidden="true" />
              <a href={`tel:${resource.contact}`} className="underline">
                {resource.contact}
              </a>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Chips de citas legales: ✓ verificada o ⚠ sin respaldo, con el extracto del corpus. */
export function CitationChips({ language, apiResponse }: { language: SupportedLanguage; apiResponse: LegalQueryApiResponse }) {
  const citations = apiResponse.metadata?.citations ?? [];
  if (!citations.length) return null;
  const t = chatTranslations[language].citations;
  return (
    <section aria-label={t.label} className="mt-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">{t.label}</h3>
      <ul className="mt-1 flex flex-wrap gap-2">
        {citations.map((citation) => {
          const verified = citation.status === 'verified';
          const title = verified
            ? `${t.verified}${citation.source ? ` — ${t.excerptFrom(citation.source)}` : ''}${citation.excerpt ? `: ${citation.excerpt}` : ''}`
            : t.unverified;
          return (
            <li key={citation.key}>
              <details className="group">
                <summary
                  title={title}
                  aria-label={`${citation.text}: ${verified ? t.verified : t.unverified}`}
                  className={`inline-flex cursor-pointer list-none items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${
                    verified
                      ? 'border-emerald-800 bg-emerald-950/40 text-emerald-300'
                      : 'border-amber-800 bg-amber-950/40 text-amber-300'
                  }`}
                >
                  {verified ? (
                    <BadgeCheck className="w-3 h-3" aria-hidden="true" />
                  ) : (
                    <TriangleAlert className="w-3 h-3" aria-hidden="true" />
                  )}
                  <span aria-hidden="true">{verified ? '✓' : '⚠'}</span>
                  {citation.text}
                </summary>
                <p className="mt-1 max-w-md rounded-md bg-zinc-900 p-2 text-xs text-zinc-300">
                  {verified && citation.excerpt ? (
                    <>
                      <span className="block font-semibold text-zinc-200">{citation.source ? t.excerptFrom(citation.source) : t.verified}</span>
                      “{citation.excerpt}”
                    </>
                  ) : (
                    t.unverified
                  )}
                </p>
              </details>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Jurisprudencia relacionada: fragmentos recuperados que citan una Casación, con su relevancia y camino. */
export function RelatedJurisprudence({ language, apiResponse }: { language: SupportedLanguage; apiResponse: LegalQueryApiResponse }) {
  const t = chatTranslations[language].related;
  const items = (apiResponse.metadata?.evidence ?? []).filter((item) => item.jurisprudence?.length);
  if (!items.length) return null;
  const methods = t.methods as Record<string, string>;
  const method = methods[apiResponse.metadata?.retrieval_method ?? ''] ?? t.methods.unknown;
  return (
    <section aria-label={t.title} className="mt-3">
      <h3 className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">
        <Scale className="w-3 h-3" aria-hidden="true" />
        {t.title}
      </h3>
      <ul className="mt-1 space-y-2">
        {items.map((item) => {
          const percent = typeof item.relevance === 'number' ? Math.round(item.relevance * 100) : null;
          return (
            <li key={`${item.source}-${item.jurisprudence?.join(',')}`} className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3 text-xs text-zinc-300">
              <p className="font-semibold text-zinc-200">{item.source}</p>
              <p className="mt-0.5 text-zinc-400">
                {t.citedCases}: {item.jurisprudence?.map((key) => key.replace('casacion:', 'Casación ')).join(', ')}
              </p>
              <div className="mt-1 flex items-center gap-2">
                {percent !== null ? (
                  <>
                    <div role="meter" aria-label={t.relevance(String(percent))} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} className="h-1.5 w-24 rounded bg-zinc-800">
                      <div className="h-1.5 rounded bg-indigo-500" style={{ width: `${percent}%` }} />
                    </div>
                    <span>{t.relevance(String(percent))}</span>
                  </>
                ) : (
                  <span>{t.unknownRelevance}</span>
                )}
              </div>
              <p className="mt-1 text-zinc-500">
                {t.pathLabel}: {t.origins[item.origin ?? 'lexical']}, {method}.
              </p>
              <p className="mt-1 text-zinc-400">“{item.excerpt}”</p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** "¿Por qué confiar en esta respuesta?": solo hechos medidos por el pipeline, sin adjetivos propios. */
export function TrustPanel({ language, apiResponse }: { language: SupportedLanguage; apiResponse: LegalQueryApiResponse }) {
  const t = chatTranslations[language].trust;
  const validation = apiResponse.validation;
  const evidence = apiResponse.metadata?.evidence ?? [];
  const citations = apiResponse.metadata?.citations ?? [];
  const verified = citations.filter((c) => c.status === 'verified').length;
  const reliable = validation?.is_reliable;
  return (
    <details className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950/50 text-xs text-zinc-300">
      <summary className="cursor-pointer px-3 py-2 font-semibold text-zinc-200">{t.summary}</summary>
      <ul className="space-y-1 px-3 pb-3 pt-1">
        <li>{evidence.length ? t.evidence(evidence.length) : t.noEvidence}</li>
        {validation && <li>{validation.is_grounded ? t.grounded : t.notGrounded}</li>}
        {validation && typeof validation.hallucination_risk === 'number' && (
          <li>{t.risk((validation.hallucination_risk * 100).toFixed(0))}</li>
        )}
        <li>{citations.length ? t.citations(verified, citations.length) : t.noCitations}</li>
        {typeof reliable === 'boolean' && <li className={reliable ? 'text-emerald-300' : 'text-amber-300'}>{reliable ? t.reliable : t.notReliable}</li>}
        <li className="pt-1 text-zinc-500">{t.disclaimer}</li>
      </ul>
    </details>
  );
}

/** Todo lo que acompaña a una respuesta final del asistente. */
export function AssistantEvidence({ language, apiResponse }: { language: SupportedLanguage; apiResponse: LegalQueryApiResponse }) {
  if (apiResponse.metadata?.evidence_status === 'insufficient_evidence') {
    return <InsufficientEvidenceCard language={language} />;
  }
  return (
    <>
      <CitationChips language={language} apiResponse={apiResponse} />
      <RelatedJurisprudence language={language} apiResponse={apiResponse} />
      <TrustPanel language={language} apiResponse={apiResponse} />
    </>
  );
}
