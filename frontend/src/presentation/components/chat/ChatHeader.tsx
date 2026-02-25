'use client';

import { Globe, Scale } from 'lucide-react';
import type { SupportedLanguage } from '../../../domain/legal/types';

interface ChatHeaderProps {
  currentLanguage: SupportedLanguage;
  onLanguageChange: (lang: SupportedLanguage) => void;
  isOnline?: boolean;
}

export function ChatHeader({ currentLanguage, onLanguageChange, isOnline }: ChatHeaderProps) {
  return (
    <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-slate-200 shadow-sm">
      <div className="max-w-4xl mx-auto flex items-center justify-between px-4 md:px-8 h-16">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow">
            <Scale className="w-5 h-5 text-white" />
          </div>
          <div className="leading-tight">
            <p className="text-base font-bold text-slate-900">IA Jurídica</p>
            <div className="flex items-center gap-1.5">
              <span
                className={`w-2 h-2 rounded-full ${isOnline === false ? 'bg-red-400' : 'bg-emerald-400'} ${isOnline !== false ? 'animate-pulse' : ''}`}
              />
              <span className="text-xs text-slate-500">
                {isOnline === false ? 'Sistema degradado' : 'Asistente Legal Bilingüe'}
              </span>
            </div>
          </div>
        </div>

        {/* Language toggle */}
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-slate-400" />
          <div className="flex bg-slate-100 rounded-full p-0.5 gap-0.5">
            {(['spanish', 'quechua'] as SupportedLanguage[]).map((lang) => (
              <button
                key={lang}
                id={`lang-toggle-${lang}`}
                type="button"
                onClick={() => onLanguageChange(lang)}
                className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all duration-200 ${
                  currentLanguage === lang
                    ? 'bg-white text-indigo-700 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {lang === 'spanish' ? 'Español' : 'Quechua'}
              </button>
            ))}
          </div>
        </div>
      </div>
    </header>
  );
}
