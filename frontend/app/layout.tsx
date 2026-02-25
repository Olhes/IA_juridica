import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { ThemeProvider } from '../src/presentation/components/ThemeProvider';
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
    <html lang="es" className="h-full" suppressHydrationWarning>
      <body className="h-full bg-slate-50 dark:bg-gray-950 transition-colors duration-300">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
