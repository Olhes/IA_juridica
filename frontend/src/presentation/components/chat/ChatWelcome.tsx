'use client';

import { MessageSquare, Scale } from 'lucide-react';
import type { SupportedLanguage } from '../../../domain/legal/types';

const TOPIC_SUGGESTIONS = [
  {
    icon: '🛡️',
    label: 'Violencia familiar',
    query: '¿Cómo puedo denunciar violencia familiar?',
  },
  {
    icon: '👶',
    label: 'Pensión de alimentos',
    query: '¿Cómo solicito pensión de alimentos para mis hijos?',
  },
  {
    icon: '⚖️',
    label: 'Medidas de protección',
    query: '¿Qué medidas de protección puedo pedir hoy?',
  },
  {
    icon: '📋',
    label: 'Denuncias y procesos',
    query: '¿Cómo funciona el proceso de denuncia penal?',
  },
];

interface ChatWelcomeProps {
  language: SupportedLanguage;
  onSelectQuery: (query: string) => void;
}

export function ChatWelcome({ language, onSelectQuery }: ChatWelcomeProps) {
  const isQuechua = language === 'quechua';

  return (
    <div className="flex flex-col items-center justify-center flex-1 px-4 py-16 text-center animate-fade-in">
      {/* Logo */}
      <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-xl mb-6">
        <Scale className="w-10 h-10 text-white" />
      </div>

      {/* Title */}
      <h1 className="text-3xl md:text-4xl font-bold text-slate-900 mb-3">
        {isQuechua ? 'IA Jurídica' : 'IA Jurídica'}
      </h1>
      <p className="text-lg text-slate-600 mb-2">
        {isQuechua ? 'Iskay Simi Yachachiq Legal' : 'Asistente Legal Bilingüe'}
      </p>
      <p className="text-sm text-slate-500 max-w-md mb-10">
        {isQuechua
          ? 'Violencia familiar, pension, denuncias utaq proceso legalmanta tapukuy atikuy.'
          : 'Resuelvo tus dudas sobre violencia familiar, pensión de alimentos, medidas de protección y procesos legales en Perú.'}
      </p>

      {/* Topic cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-xl">
        {TOPIC_SUGGESTIONS.map(({ icon, label, query }) => (
          <button
            key={label}
            id={`topic-card-${label.replace(/\s+/g, '-').toLowerCase()}`}
            type="button"
            onClick={() => onSelectQuery(query)}
            className="group flex items-center gap-3 bg-white border border-slate-200 rounded-2xl p-4 text-left hover:border-indigo-300 hover:shadow-md hover:bg-indigo-50/40 transition-all duration-200 cursor-pointer"
          >
            <span className="text-2xl">{icon}</span>
            <div>
              <p className="text-sm font-semibold text-slate-800 group-hover:text-indigo-800 transition-colors">
                {label}
              </p>
              <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">{query}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Disclaimer */}
      <div className="mt-10 flex items-start gap-2 text-xs text-slate-400 max-w-sm text-left">
        <MessageSquare className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <span>
          {isQuechua
            ? 'Kay orientacionqa mana reemplazanchu abogadopa profesional yanapayninta.'
            : 'Esta orientación no reemplaza la asesoría de una abogada o abogado. Ante emergencias, llama al 113.'}
        </span>
      </div>
    </div>
  );
}
