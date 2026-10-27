'use client';

import type { ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import {
  Globe,
  Moon,
  Scale,
  Sun,
  Wifi,
  WifiOff,
  LogIn,
  LogOut,
  User,
} from 'lucide-react';
import { useTheme } from '../ThemeProvider';
import { useEffect, useState } from 'react';
import type { SupportedLanguage } from '../../../domain/legal/types';
import { useAuth } from '../AuthProvider';
import { openGoogleLoginPopup } from '../googleLoginPopup';

interface ChatHeaderProps {
  currentLanguage: SupportedLanguage;
  onLanguageChange: (lang: SupportedLanguage) => void;
  isOnline?: boolean;
  /** Slot para el botón de toggle del sidebar (solo mobile) */
  sidebarToggle?: ReactNode;
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
    login: 'Acceder',
    logout: 'Cerrar sesión',
  },
  quechua: {
    appName: 'IA Jurídica',
    online:  'Sistema kachkan',
    offline: 'Sistema millk\'aykun',
    langES:  'Español',
    langQU:  'Quechua',
    themeLight: 'Lliphlliq rikhuri',
    themeDark:  'Tutayaq rikhuri',
    login: 'Yaykuy',
    logout: 'Lluqsiy',
  },
} as const;

function ThemeToggle({ language }: { language: SupportedLanguage }) {
  const { theme, toggleTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="w-9 h-9" />;

  const isDark = theme === 'dark';
  const t = i18n[language];
  return (
    <button
      id="theme-toggle-btn"
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? t.themeLight : t.themeDark}
      className="w-11 h-11 flex items-center justify-center rounded-lg
        border-2 border-slate-900 dark:border-slate-300
        bg-white hover:bg-slate-100
        dark:bg-slate-900 dark:hover:bg-slate-800
        text-slate-900 dark:text-slate-100
        transition-colors duration-200 active:scale-95"
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
  sidebarToggle,
}: ChatHeaderProps) {
  const t = i18n[currentLanguage];
  const { user, isAuthenticated, logout } = useAuth();
  const router = useRouter();
  const [isAuthenticating, setIsAuthenticating] = useState(false);

  const handleAuth = () => {
    if (isAuthenticated) {
      logout();
    } else {
      // Google OAuth en popup; la sesión se abre en esta pestaña sin recargar.
      openGoogleLoginPopup();
    }
  };

  return (
    <header className="sticky top-0 z-30
      bg-white/80 dark:bg-gray-900/80
      backdrop-blur-md
      border-b border-slate-200 dark:border-gray-800
      shadow-sm"
    >
      <div className="max-w-4xl mx-auto flex items-center justify-between px-4 md:px-8 h-16 gap-3">

        {/* ── Sidebar toggle (mobile) + Brand ── */}
        <div className="flex items-center gap-2.5 min-w-0">
          {sidebarToggle}
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex-shrink-0 w-11 h-11 rounded-lg bg-indigo-50 dark:bg-indigo-950 flex items-center justify-center">
              <Scale className="w-6 h-6 text-indigo-700 dark:text-indigo-300" />
            </div>
            <div className="leading-tight min-w-0">
              <p className="font-display text-lg font-extrabold text-slate-900 dark:text-slate-100 truncate">
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
        </div>

        {/* ── Controls ── */}
        <div className="flex items-center gap-2 flex-shrink-0">

          {/* Language toggle */}
          <div className="flex items-center gap-1.5">
            <Globe className="w-4 h-4 text-slate-400 dark:text-slate-500 hidden sm:block" />
            <div className="flex bg-slate-100 dark:bg-slate-800 rounded-full p-1 gap-1">
              {(['spanish', 'quechua'] as SupportedLanguage[]).map((lang) => (
                <button
                  key={lang}
                  id={`lang-toggle-${lang}`}
                  type="button"
                  onClick={() => onLanguageChange(lang)}
                  className={`min-h-[40px] px-4 rounded-full text-sm transition-colors duration-200 ${
                    currentLanguage === lang
                      ? 'bg-slate-900 text-white dark:bg-amber-400 dark:text-slate-900 font-extrabold'
                      : 'font-bold text-slate-900 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  {lang === 'spanish' ? t.langES : t.langQU}
                </button>
              ))}
            </div>
          </div>

          {/* Dark mode toggle */}
          <ThemeToggle language={currentLanguage} />

          {/* Auth button */}
          <button
            type="button"
            onClick={handleAuth}
            disabled={isAuthenticating}
            aria-label={isAuthenticated ? t.logout : t.login}
            className="flex items-center gap-2 min-h-[44px] px-4 rounded-lg text-sm font-extrabold
              border-2 border-slate-900 dark:border-slate-300
              bg-white hover:bg-slate-100
              dark:bg-slate-900 dark:hover:bg-slate-800
              text-slate-900 dark:text-slate-100
              transition-colors duration-200 active:scale-95
              disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isAuthenticating ? (
              <>
                <div className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
                <span className="hidden sm:inline">Autenticando...</span>
              </>
            ) : isAuthenticated ? (
              <>
                {user?.picture ? (
                  <img
                    src={user.picture}
                    alt={user.username || 'Usuario'}
                    className="w-6 h-6 rounded-full object-cover"
                  />
                ) : (
                  <User className="w-4 h-4" />
                )}
                <span className="hidden sm:inline">{user?.full_name || user?.username || 'Usuario'}</span>
                <LogOut className="w-4 h-4" />
              </>
            ) : (
              <>
                <LogIn className="w-4 h-4" />
                <span className="hidden sm:inline">{t.login}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
