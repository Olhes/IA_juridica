import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { ThemeProvider } from '../src/presentation/components/ThemeProvider';
import { AuthProvider } from '../src/presentation/components/AuthProvider';
import './globals.css';

export const metadata: Metadata = {
  title: 'IA Jurídica — Asistente Legal Bilingüe',
  description: 'Asistente legal bilingüe (Español / Quechua) para comunidades andinas.',
};

interface RootLayoutProps {
  children: ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="es" className="h-full dark" suppressHydrationWarning>
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
