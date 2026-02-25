'use client';

import {
  BookOpen,
  ClipboardList,
  HelpCircle,
  PhoneCall,
  Scale,
  ShieldAlert,
  Users,
} from 'lucide-react';
import type { SupportedLanguage } from '../../../domain/legal/types';

// ─── Traducciones ─────────────────────────────────────────────────────────────

const i18n = {
  spanish: {
    subtitle:    'Asistente Legal Bilingüe',
    description: 'Resuelvo tus dudas sobre violencia familiar, pensión de alimentos, medidas de protección y procesos legales en Perú.',
    topicsLabel: 'Temas frecuentes',
    disclaimer:  'Esta orientación no reemplaza la asesoría de un abogado. Ante emergencias llama al 113 (MIMP).',
    topics: [
      { Icon: ShieldAlert,  iconBg: 'bg-red-100 dark:bg-red-950/50',     iconColor: 'text-red-600 dark:text-red-400',     label: 'Violencia familiar',    query: '¿Cómo puedo denunciar violencia familiar?' },
      { Icon: Users,        iconBg: 'bg-amber-100 dark:bg-amber-950/50', iconColor: 'text-amber-600 dark:text-amber-400', label: 'Pensión de alimentos',   query: '¿Cómo solicito pensión de alimentos para mis hijos?' },
      { Icon: Scale,        iconBg: 'bg-indigo-100 dark:bg-indigo-950/50',iconColor: 'text-indigo-600 dark:text-indigo-400',label: 'Medidas de protección', query: '¿Qué medidas de protección puedo pedir hoy?' },
      { Icon: ClipboardList,iconBg: 'bg-emerald-100 dark:bg-emerald-950/50',iconColor:'text-emerald-600 dark:text-emerald-400',label:'Denuncias y procesos',query: '¿Cómo funciona el proceso de denuncia penal?' },
      { Icon: PhoneCall,    iconBg: 'bg-rose-100 dark:bg-rose-950/50',   iconColor: 'text-rose-600 dark:text-rose-400',   label: 'Recursos de emergencia',query: '¿A qué números llamo en caso de emergencia por violencia?' },
      { Icon: BookOpen,     iconBg: 'bg-violet-100 dark:bg-violet-950/50',iconColor:'text-violet-600 dark:text-violet-400',label: 'Derechos y leyes',      query: '¿Qué leyes me protegen en caso de violencia familiar en Perú?' },
    ],
  },
  quechua: {
    subtitle:    'Iskay Simi Yachachiq Legal',
    description: 'Llakichikuymanta, alimentosmanta, proteccionmanta, utaq proceso legalmanta tapukuyta atikuy.',
    topicsLabel: 'Yuyaykunapa sunqun',
    disclaimer:  'Kay orientacionqa mana reemplazanchu abogadopa yanapayninta. Llakipi kaspayki 113-ta waqay (MIMP).',
    topics: [
      { Icon: ShieldAlert,  iconBg: 'bg-red-100 dark:bg-red-950/50',     iconColor: 'text-red-600 dark:text-red-400',     label: 'Llakichikuymanta willay',   query: '¿Imaynatataq llakichikuyta willaqman rini?' },
      { Icon: Users,        iconBg: 'bg-amber-100 dark:bg-amber-950/50', iconColor: 'text-amber-600 dark:text-amber-400', label: 'Alimentosta mañakuy',        query: '¿Imaynatataq wawaykunapaq alimentosta mañakuy?' },
      { Icon: Scale,        iconBg: 'bg-indigo-100 dark:bg-indigo-950/50',iconColor:'text-indigo-600 dark:text-indigo-400',label: 'Ima proteccionesta mañakuy', query: '¿Qanpaq ima proteccionesta mañakuy atikuy?' },
      { Icon: ClipboardList,iconBg: 'bg-emerald-100 dark:bg-emerald-950/50',iconColor:'text-emerald-600 dark:text-emerald-400',label:'Willaypa puriynin',     query: '¿Imaynatataq willaypa puriynin kachkan?' },
      { Icon: PhoneCall,    iconBg: 'bg-rose-100 dark:bg-rose-950/50',   iconColor: 'text-rose-600 dark:text-rose-400',   label: 'Yanapakuy telefonos',        query: '¿Ima telefonosman waqay atikuy llakipi kaspayki?' },
      { Icon: BookOpen,     iconBg: 'bg-violet-100 dark:bg-violet-950/50',iconColor:'text-violet-600 dark:text-violet-400',label: 'Leykunam llampuyawanki',    query: '¿Ima leykunam llakichikuyta mana saqenanpaq kachkan?' },
    ],
  },
} as const;

// ─── Componente ───────────────────────────────────────────────────────────────

interface ChatWelcomeProps {
  language: SupportedLanguage;
  onSelectQuery: (query: string) => void;
}

export function ChatWelcome({ language, onSelectQuery }: ChatWelcomeProps) {
  const t = i18n[language];

  return (
    <div className="flex flex-col items-center justify-center flex-1 px-4 py-12 text-center animate-fade-in">

      {/* ── Logo ── */}
      <div className="relative mb-6">
        <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-xl">
          <Scale className="w-10 h-10 text-white" />
        </div>
        <div className="absolute inset-0 rounded-3xl bg-gradient-to-br from-indigo-600/30 to-violet-600/30 blur-xl -z-10 animate-pulse" />
      </div>

      {/* ── Título ── */}
      <h1 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-slate-50 mb-2">
        IA Jurídica
      </h1>
      <p className="text-base font-medium text-indigo-600 dark:text-indigo-400 mb-2">
        {t.subtitle}
      </p>
      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-md mb-10 leading-relaxed">
        {t.description}
      </p>

      {/* ── Cards de temas ── */}
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-600 mb-4">
        {t.topicsLabel}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 w-full max-w-2xl">
        {t.topics.map(({ Icon, iconBg, iconColor, label, query }) => (
          <button
            key={label}
            id={`topic-card-${label.slice(0, 20).replace(/\s+/g, '-').toLowerCase()}`}
            type="button"
            onClick={() => onSelectQuery(query)}
            className="group flex items-center gap-3
              bg-white dark:bg-gray-900
              border border-slate-200 dark:border-gray-800
              rounded-2xl p-4 text-left
              hover:border-indigo-300 dark:hover:border-indigo-700
              hover:shadow-lg dark:hover:shadow-indigo-950/40
              hover:-translate-y-0.5
              transition-all duration-200 cursor-pointer"
          >
            <div className={`flex-shrink-0 w-10 h-10 rounded-xl ${iconBg} flex items-center justify-center transition-transform duration-200 group-hover:scale-110`}>
              <Icon className={`w-5 h-5 ${iconColor}`} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 group-hover:text-indigo-700 dark:group-hover:text-indigo-300 transition-colors">
                {label}
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5 truncate">
                {query}
              </p>
            </div>
          </button>
        ))}
      </div>

      {/* ── Disclaimer ── */}
      <div className="mt-10 flex items-center gap-2 text-xs text-slate-400 dark:text-slate-600 max-w-sm">
        <HelpCircle className="w-4 h-4 flex-shrink-0 text-slate-300 dark:text-slate-700" />
        <span className="text-left">{t.disclaimer}</span>
      </div>
    </div>
  );
}
