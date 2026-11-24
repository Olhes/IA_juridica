'use client';

import { BadgeCheck, Languages, Phone, Scale, ShieldQuestion, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import type { CitationCheck, EvidenceItem, LegalQueryApiResponse, SupportedLanguage } from '../../../domain/legal/types';
import { chatTranslations } from '../../i18n/translations';
import { MarkdownRenderer } from './MarkdownRenderer';

function officialLink(value?: string | null) {
  try {
    const url = new URL(value ?? '');
    return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

/** Tarjeta de evidencia insuficiente: el sistema se abstiene y ofrece recursos de ayuda. */
export function InsufficientEvidenceCard({ language }: { language: SupportedLanguage }) {
  const t = chatTranslations[language].insufficient;
  return (
    <section
      aria-label={t.title}
      className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800"
    >
      <h3 className="flex items-center gap-2 font-semibold">
        <ShieldQuestion className="w-4 h-4" aria-hidden="true" />
        {t.title}
      </h3>
      <p className="mt-1 text-amber-800">{t.body}</p>
      <h4 className="mt-3 text-xs font-semibold uppercase tracking-wide text-amber-700">{t.resourcesLabel}</h4>
      <ul className="mt-2 grid gap-2 sm:grid-cols-3">
        {t.resources.map((resource) => (
          <li key={resource.name} className="rounded-lg border border-amber-200 bg-white p-3">
            <p className="font-semibold text-amber-800">{resource.name}</p>
            <p className="text-xs text-amber-800">{resource.detail}</p>
            <p className="mt-1 flex items-center gap-1 font-mono text-xs text-amber-700">
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

/** Nodo del árbol de citas: una norma con sus artículos/fragmentos recuperados. */
type TreeEntry = {
  key: string;
  label: string | null;
  status: 'verified' | 'unverified' | 'retrieved';
  item?: EvidenceItem;
  section?: NonNullable<CitationCheck['sat_section']>;
  citation?: CitationCheck;
};

type TreeLaw = { source: string; entries: TreeEntry[]; checks: number; verified: number };

/** Norma → fragmentos: agrupa la evidencia recuperada y le enlaza las citas verificadas. */
function buildCitationTree(citations: CitationCheck[], evidence: EvidenceItem[], unknownSource: string) {
  const laws = new Map<string, TreeLaw>();
  const byVersion = new Map<string, TreeEntry>();
  const lawFor = (source?: string | null) => {
    const name = source?.trim() || unknownSource;
    if (!laws.has(name)) laws.set(name, { source: name, entries: [], checks: 0, verified: 0 });
    return laws.get(name)!;
  };

  for (const item of evidence) {
    const law = lawFor(item.document ?? item.source);
    const entry: TreeEntry = {
      key: `evidence:${item.version_id ?? `${law.source}:${law.entries.length}`}`,
      label: item.section ?? null,
      status: 'retrieved',
      item,
    };
    law.entries.push(entry);
    if (item.version_id) byVersion.set(item.version_id, entry);
  }

  const unmatched: CitationCheck[] = [];
  for (const citation of citations) {
    const section = citation.sat_section;
    if (section) {
      const existing = byVersion.get(section.version_id);
      const law = lawFor(existing?.item?.document ?? existing?.item?.source ?? section.path[0] ?? citation.source);
      law.checks += 1;
      if (citation.status === 'verified') law.verified += 1;
      if (existing) {
        existing.label = section.title;
        existing.status = citation.status;
        existing.section = section;
        existing.citation = citation;
      } else {
        const entry: TreeEntry = {
          key: citation.key,
          label: section.title,
          status: citation.status,
          section,
          citation,
        };
        law.entries.push(entry);
        byVersion.set(section.version_id, entry);
      }
      continue;
    }
    if (citation.status === 'unverified') {
      unmatched.push(citation);
      continue;
    }
    const law = lawFor(citation.source);
    law.checks += 1;
    law.verified += 1;
    // Una cita de ley/Casación/D.S. acredita la norma completa: no inventa un
    // fragmento. Solo una cita de artículo puede corresponder a un fragmento suelto.
    if (!citation.key.includes(':art:')) continue;
    const free = law.entries.find((entry) => entry.item && !entry.citation && !entry.section);
    if (free) {
      free.label = citation.text;
      free.status = 'verified';
      free.citation = citation;
    } else {
      law.entries.push({ key: citation.key, label: citation.text, status: 'verified', citation });
    }
  }

  return {
    laws: [...laws.values()].filter((law) => law.entries.length > 0),
    unmatched,
  };
}

/** Citas legales en árbol: cada norma recuperada con sus artículos y su estado. */
export function CitationTree({ language, apiResponse }: { language: SupportedLanguage; apiResponse: LegalQueryApiResponse }) {
  const citations = apiResponse.metadata?.citations ?? [];
  const evidence = apiResponse.metadata?.evidence ?? [];
  const t = chatTranslations[language].citations;
  const related = chatTranslations[language].related;
  if (!citations.length && !evidence.length) return null;
  const { laws, unmatched } = buildCitationTree(citations, evidence, t.unknownSource);
  return (
    <section aria-label={t.label} className="mt-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">{t.label}</h3>
      <ul className="mt-1 space-y-2">
        {laws.map((law) => (
          <li key={law.source}>
            <details className="rounded-lg border border-slate-200 bg-white">
              <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-semibold text-slate-900">
                <Scale className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                <span className="flex-1">{law.source}</span>
                <span className="text-xs font-normal text-slate-500">
                  {t.fragments(law.entries.length)}
                  {law.checks > 0 && ` · ${t.verifiedCount(law.verified, law.checks)}`}
                </span>
              </summary>
              <ul className="space-y-1 border-t border-slate-200 px-2 py-2">
                {law.entries.map((entry) => {
                  // Bajo el nodo de la norma, el hijo se rotula por su provisión
                  // ("Artículo 7 · Numeral 7.2"), no repitiendo el nombre de la ley.
                  const label = entry.section
                    ? entry.section.path.slice(1).join(' · ') || entry.section.title
                    : entry.label ?? t.fragment;
                  if (entry.section) {
                    const href = officialLink(entry.section.source_url);
                    return (
                      <li key={entry.key}>
                        <details className="rounded-md border border-emerald-200 bg-emerald-50/50 text-slate-900">
                          <summary
                            aria-label={`${label}: ${entry.status === 'verified' ? t.verified : t.retrievedOnly}`}
                            className="flex cursor-pointer items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-emerald-800"
                          >
                            <BadgeCheck className="w-3 h-3 shrink-0" aria-hidden="true" />
                            <span className="flex-1">{label}</span>
                            <span className="font-normal">{t.fullSection}</span>
                          </summary>
                          <div className="border-t border-emerald-200 bg-white px-2.5 py-2">
                            <p className="mb-2 break-words text-xs font-medium text-slate-600">{entry.section.path.join(' → ')}</p>
                            <div className="max-h-[28rem] overflow-auto break-words rounded bg-slate-50 px-3 py-2">
                              <MarkdownRenderer content={entry.section.text} />
                            </div>
                            {href && <a href={href} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-xs underline">{t.sourceLink}</a>}
                          </div>
                        </details>
                      </li>
                    );
                  }
                  const verified = entry.status === 'verified';
                  const excerpt = entry.citation?.excerpt ?? entry.item?.excerpt;
                  const itemHref = officialLink(entry.item?.source_url);
                  return (
                    <li key={entry.key}>
                      <details className="rounded-md border border-slate-200">
                        <summary
                          aria-label={`${label}: ${verified ? t.verified : t.retrievedOnly}`}
                          className={`flex cursor-pointer items-center gap-1 px-2.5 py-1.5 text-xs font-medium ${verified ? 'text-emerald-700' : 'text-slate-600'}`}
                        >
                          {verified ? <BadgeCheck className="w-3 h-3 shrink-0" aria-hidden="true" /> : <span aria-hidden="true">·</span>}
                          <span className="flex-1">{label}</span>
                        </summary>
                        <div className="border-t border-slate-200 px-2.5 py-2 text-xs text-slate-700">
                          {entry.item?.relevance != null && (
                            <p className="mb-1 text-slate-500">{related.relevance(`${Math.round(entry.item.relevance * 100)}`)}</p>
                          )}
                          {excerpt && <p className="break-words">“{excerpt}”</p>}
                          {!verified && <p className="mt-1 text-slate-500">{t.retrievedOnly}</p>}
                          {itemHref && <a href={itemHref} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block underline">{t.sourceLink}</a>}
                        </div>
                      </details>
                    </li>
                  );
                })}
              </ul>
            </details>
          </li>
        ))}
        {unmatched.length > 0 && (
          <li>
            <ul className="space-y-1">
              {unmatched.map((citation) => (
                <li key={citation.key}>
                  <details>
                    <summary
                      aria-label={`${citation.text}: ${t.unverified}`}
                      className="inline-flex cursor-pointer list-none items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700"
                    >
                      <TriangleAlert className="w-3 h-3" aria-hidden="true" />
                      <span aria-hidden="true">⚠</span>
                      {citation.text}
                    </summary>
                    <p className="mt-1 max-w-md rounded-md bg-slate-100 p-2 text-xs text-slate-700">{t.unverified}</p>
                  </details>
                </li>
              ))}
            </ul>
          </li>
        )}
      </ul>
    </section>
  );
}

/** Calidad estimada del quechua, aviso de revisión y acceso al original en español. */
export function TranslationNotice({ language, apiResponse }: { language: SupportedLanguage; apiResponse: LegalQueryApiResponse }) {
  const [showOriginal, setShowOriginal] = useState(false);
  const translation = apiResponse.metadata?.translation;
  if (!translation) return null;
  const t = chatTranslations[language].translation;
  const quality = translation.quality;
  const original = apiResponse.response?.respuesta_espanol;
  const failed = translation.fallback_to_spanish || translation.success === false;
  const tone = quality === 'alta' ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : quality === 'media' ? 'border-amber-200 bg-amber-50 text-amber-700'
    : 'border-red-200 bg-red-50 text-red-700';
  return (
    <section aria-label={t.reviewNotice} className="mt-3 text-xs text-slate-700">
      <div className="flex flex-wrap items-center gap-2">
        {quality && !failed && (
          <span data-quality={quality} title={t.qualityHints[quality]} className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 font-medium ${tone}`}>
            <Languages className="w-3 h-3" aria-hidden="true" />
            {t.qualityLabel(t.qualities[quality])}
          </span>
        )}
        {original && (
          <button type="button" aria-expanded={showOriginal} onClick={() => setShowOriginal((v) => !v)} className="rounded-md border border-slate-300 px-2 py-1 text-slate-900 hover:bg-slate-100">
            {showOriginal ? t.hideOriginal : t.showOriginal}
          </button>
        )}
      </div>
      <p role="note" className="mt-2 text-slate-600">{failed ? t.fallback : t.reviewNotice}</p>
      {showOriginal && original && (
        <blockquote className="mt-2 rounded-md bg-slate-100 p-2 text-slate-700">
          <span className="block font-semibold text-slate-900">{t.originalLabel}</span>
          {original}
        </blockquote>
      )}
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
      <h3 className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
        <Scale className="w-3 h-3" aria-hidden="true" />
        {t.title}
      </h3>
      <ul className="mt-1 space-y-2">
        {items.map((item) => {
          const percent = typeof item.relevance === 'number' ? Math.round(item.relevance * 100) : null;
          return (
            <li key={`${item.source}-${item.jurisprudence?.join(',')}`} className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">
              <p className="font-semibold text-slate-900">{item.source}</p>
              <p className="mt-0.5 text-slate-600">
                {t.citedCases}: {item.jurisprudence?.map((key) => key.replace('casacion:', 'Casación ')).join(', ')}
              </p>
              <div className="mt-1 flex items-center gap-2">
                {percent !== null ? (
                  <>
                    <div role="meter" aria-label={t.relevance(String(percent))} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} className="h-1.5 w-24 rounded bg-slate-200">
                      <div className="h-1.5 rounded bg-indigo-600" style={{ width: `${percent}%` }} />
                    </div>
                    <span>{t.relevance(String(percent))}</span>
                  </>
                ) : (
                  <span>{t.unknownRelevance}</span>
                )}
              </div>
              <p className="mt-1 text-slate-500">
                {t.pathLabel}: {t.origins[item.origin ?? 'lexical']}, {method}.
              </p>
              <p className="mt-1 text-slate-600">“{item.excerpt}”</p>
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
  const evidence = apiResponse.metadata?.evidence ?? [];
  const citations = apiResponse.metadata?.citations ?? [];
  const documents = new Set(evidence.map((item) => item.document ?? item.source)).size;
  const verified = citations.filter((c) => c.status === 'verified').length;
  return (
    <details className="mt-3 rounded-lg border border-slate-200 bg-white text-xs text-slate-700">
      <summary className="cursor-pointer px-3 py-2 font-semibold text-slate-900">{chatTranslations[language].citations.label}</summary>
      <ul className="space-y-1 px-3 pb-3 pt-1">
        <li>{evidence.length ? t.evidence(evidence.length, documents) : t.noEvidence}</li>
        <li>{citations.length ? t.citations(verified, citations.length) : t.noCitations}</li>
        <li className="pt-1 text-slate-500">{t.disclaimer}</li>
      </ul>
    </details>
  );
}

/** Todo lo que acompaña a una respuesta final del asistente. */
export function AssistantEvidence({ language, apiResponse }: { language: SupportedLanguage; apiResponse: LegalQueryApiResponse }) {
  if (apiResponse.metadata?.evidence_status === 'insufficient_evidence') {
    return <><InsufficientEvidenceCard language={language} />{apiResponse.metadata?.sat_warning && <p role="note" className="mt-3 text-xs text-amber-800">{apiResponse.metadata.sat_warning} {apiResponse.metadata.sat_as_of && `(${apiResponse.metadata.sat_as_of})`}</p>}</>;
  }
  return (
    <>
      {apiResponse.metadata?.sat_warning && <p role="note" className="mt-3 text-xs text-amber-800">{apiResponse.metadata.sat_warning} {apiResponse.metadata.sat_as_of && `(${apiResponse.metadata.sat_as_of})`}</p>}
      <TranslationNotice language={language} apiResponse={apiResponse} />
      <CitationTree language={language} apiResponse={apiResponse} />
      <RelatedJurisprudence language={language} apiResponse={apiResponse} />
      <TrustPanel language={language} apiResponse={apiResponse} />
    </>
  );
}
