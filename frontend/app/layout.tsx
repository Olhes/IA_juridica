import type { Metadata } from 'next';
import { Bricolage_Grotesque, Nunito_Sans } from 'next/font/google';
import type { ReactNode } from 'react';
import { ThemeProvider } from '../src/presentation/components/ThemeProvider';
import { AuthProvider } from '../src/presentation/components/AuthProvider';
import './globals.css';

// Tipografías del diseño A, servidas desde el propio dominio (next/font).
const bricolage = Bricolage_Grotesque({
  subsets: ['latin', 'latin-ext'],
  variable: '--font-bricolage',
  display: 'swap',
});
const nunito = Nunito_Sans({
  subsets: ['latin', 'latin-ext'],
  variable: '--font-nunito',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'IA Jurídica — Asistente Legal Bilingüe',
  description: 'Asistente legal bilingüe (Español / Quechua) para comunidades andinas.',
};

interface RootLayoutProps {
  children: ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="es" className={`${bricolage.variable} ${nunito.variable} h-full dark`} suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                function getTheme() {
                  try {
                    return localStorage.getItem('ia-juridica-theme') || 'dark';
                  } catch (e) {
                    return 'dark';
                  }
                }
                function setTheme(theme) {
                  var root = window.document.documentElement;
                  root.classList.remove('light', 'dark');
                  root.classList.add(theme);
                }
                setTheme(getTheme());
              })();
            `,
          }}
        />
      </head>
      <body className="h-full bg-gradient-to-br from-slate-50 via-indigo-50/30 to-violet-50/20 dark:from-gray-950 dark:via-slate-900 dark:to-indigo-950 transition-colors duration-300" suppressHydrationWarning>
        <AuthProvider>
          <ThemeProvider>{children}</ThemeProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
