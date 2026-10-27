'use client';

import type { ReactNode } from 'react';
import type { SupportedLanguage } from '../../../domain/legal/types';

/** Lenguaje visual de la app (terminal y login): vidrio oscuro, bordes sutiles y acentos índigo. */
export const panelClass = 'rounded-2xl border border-white/10 bg-zinc-900/60 p-5 shadow-xl backdrop-blur-xl';
export const tableClass = 'mt-3 w-full text-left text-sm';
export const tableHeadClass = 'text-xs uppercase tracking-wide text-zinc-500';
export const rowClass = 'border-t border-white/5';
export const linkButtonClass =
  'inline-flex items-center gap-1.5 rounded-xl border border-white/10 px-3 py-1.5 text-sm font-medium text-zinc-300 transition-all hover:bg-zinc-800 hover:text-white';

const chipTones = {
  neutral: 'border-zinc-700 bg-zinc-800/60 text-zinc-300',
  indigo: 'border-indigo-500/30 bg-indigo-500/15 text-indigo-300',
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  danger: 'border-red-500/30 bg-red-500/10 text-red-300',
} as const;

export type ChipTone = keyof typeof chipTones;

export function chipClass(tone: ChipTone) {
  return `inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${chipTones[tone]}`;
}

export function LanguageSelect({ value, onChange, label }: { value: SupportedLanguage; onChange: (value: SupportedLanguage) => void; label: string }) {
  return (
    <label className="text-sm">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as SupportedLanguage)}
        className="rounded-xl border border-zinc-700/80 bg-zinc-900 px-3 py-1.5 text-zinc-100 transition-all focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
      >
        <option value="spanish">Español</option>
        <option value="quechua">Quechua</option>
      </select>
    </label>
  );
}

/** Armazón de las páginas de calidad: el mismo fondo y cabecera que el resto de la aplicación. */
export function QualityShell({ icon, title, subtitle, actions, children }: {
  icon: ReactNode;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-950 px-4 py-10 text-zinc-100">
      <div className="mx-auto max-w-5xl space-y-6 animate-fade-in">
        <header className={`${panelClass} flex flex-wrap items-center justify-between gap-4`}>
          <div className="flex items-center gap-4">
            <div aria-hidden="true" className="flex h-11 w-11 items-center justify-center rounded-xl border border-indigo-500/30 bg-indigo-600/20 text-indigo-400">
              {icon}
            </div>
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight text-white sm:text-3xl">{title}</h1>
              {subtitle && <p className="mt-0.5 text-sm text-zinc-400">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
        {children}
      </div>
    </main>
  );
}
