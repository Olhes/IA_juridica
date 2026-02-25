'use client';

import {
  Globe,
  Moon,
  Scale,
  Sun,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import type { SupportedLanguage } from '../../../domain/legal/types';

interface ChatHeaderProps {
  currentLanguage: SupportedLanguage;
  onLanguageChange: (lang: SupportedLanguage) => void;
  isOnline?: boolean;
}

const i18n = {
  spanish: {
    appName: 'IA Jurídica',
    online:  'Sistema en línea',
    offline: 'Sistema degradado',
    langES:  'Español',
    langQU:  'Quechua',
    themeLight: 'Cambiar a modo claro',
    themeDark:  'Cambiar a modo oscuro',
  },
  quechua: {
    appName: 'IA Jurídica',
    online:  'Sistema kachkan',
    offline: 'Sistema millk’aykun',
    langES:  'Español',
    langQU:  'Quechua',
    themeLight: 'Lliphlliq rikhuri',
    themeDark:  'Tutayaq rikhuri',
  },
} as const;

function ThemeToggle({ language }: { language: SupportedLanguage }) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="w-9 h-9" />;

  const isDark = resolvedTheme === 'dark';
  const t = i18n[language];
  return (
    <button
      id="theme-toggle-btn"
      type="button"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label={isDark ? t.themeLight : t.themeDark}
      className="w-9 h-9 flex items-center justify-center rounded-xl
        bg-slate-100 hover:bg-slate-200
        dark:bg-gray-800 dark:hover:bg-gray-700
        text-slate-600 dark:text-slate-300
        transition-all duration-200 hover:scale-105 active:scale-95"
    >
      {isDark
        ? <Sun className="w-4 h-4 text-amber-400" />
        : <Moon className="w-4 h-4 text-indigo-500" />}
    </button>
  );
}

export function ChatHeader({
  currentLanguage,
  onLanguageChange,
  isOnline,
}: ChatHeaderProps) {
  const t = i18n[currentLanguage];
  return (
    <header className="sticky top-0 z-30
      bg-white/80 dark:bg-gray-900/80
      backdrop-blur-md
      border-b border-slate-200 dark:border-gray-800
      shadow-sm"
    >
      <div className="max-w-4xl mx-auto flex items-center justify-between px-4 md:px-8 h-16 gap-3">

        {/* ── Brand ── */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow">
            <Scale className="w-5 h-5 text-white" />
          </div>
          <div className="leading-tight min-w-0">
            <p className="text-base font-bold text-slate-900 dark:text-slate-100 truncate">
              {t.appName}
            </p>
            <div className="flex items-center gap-1.5">
              {isOnline === false
                ? <WifiOff className="w-3 h-3 text-red-400" />
                : <Wifi className="w-3 h-3 text-emerald-400" />}
              <span className="text-xs text-slate-500 dark:text-slate-400 truncate">
                {isOnline === false ? t.offline : t.online}
              </span>
            </div>
          </div>
        </div>

        {/* ── Controls ── */}
        <div className="flex items-center gap-2 flex-shrink-0">

          {/* Language toggle */}
          <div className="flex items-center gap-1.5">
            <Globe className="w-4 h-4 text-slate-400 dark:text-slate-500 hidden sm:block" />
            <div className="flex bg-slate-100 dark:bg-gray-800 rounded-full p-0.5 gap-0.5">
              {(['spanish', 'quechua'] as SupportedLanguage[]).map((lang) => (
                <button
                  key={lang}
                  id={`lang-toggle-${lang}`}
                  type="button"
                  onClick={() => onLanguageChange(lang)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all duration-200 ${
                    currentLanguage === lang
                      ? 'bg-white dark:bg-gray-700 text-indigo-700 dark:text-indigo-300 shadow-sm'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                  }`}
                >
                  {lang === 'spanish' ? t.langES : t.langQU}
                </button>
              ))}
            </div>
          </div>

          {/* Dark mode toggle */}
          <ThemeToggle language={currentLanguage} />
        </div>
      </div>
    </header>
  );
}
