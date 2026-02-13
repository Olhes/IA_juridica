'use client';

import { useEffect, useState } from 'react';
import { MessageSquare } from 'lucide-react';
import type { SupportedLanguage } from '../../domain/legal/types';
import { FeatureCards } from '../components/FeatureCards';
import { Header } from '../components/Header';
import { LanguageToggle } from '../components/LanguageToggle';
import { LegalConsultation } from '../components/LegalConsultation';
import { homeTranslations } from '../i18n/translations';

const LANGUAGE_STORAGE_KEY = 'preferredLanguage';

export function LegalAssistantPage() {
  const [currentLanguage, setCurrentLanguage] = useState<SupportedLanguage>('spanish');
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const savedLanguage = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (savedLanguage === 'spanish' || savedLanguage === 'quechua') {
      setCurrentLanguage(savedLanguage);
    }
  }, []);

  const handleLanguageChange = (language: SupportedLanguage) => {
    setCurrentLanguage(language);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  };

  const t = homeTranslations[currentLanguage];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-cyan-50 to-amber-50">
      <Header currentLanguage={currentLanguage} tagline={t.tagline} />

      <main className="container mx-auto px-4 py-8">
        <div className="text-center mb-12">
          <h2 className="text-4xl md:text-6xl font-bold text-gray-800 mb-4">{t.title}</h2>
          <p className="text-xl md:text-2xl text-gray-600 mb-4">{t.subtitle}</p>
          <p className="text-lg text-gray-700 max-w-3xl mx-auto mb-8">{t.description}</p>

          <LanguageToggle currentLanguage={currentLanguage} onLanguageChange={handleLanguageChange} />
        </div>

        <FeatureCards features={t.features} />

        <LegalConsultation
          currentLanguage={currentLanguage}
          isLoading={isLoading}
          setIsLoading={setIsLoading}
        />
      </main>

      <footer className="bg-gray-900 text-white py-8 mt-16">
        <div className="container mx-auto px-4 text-center">
          <div className="flex justify-center items-center mb-3">
            <MessageSquare className="w-6 h-6 mr-2" />
            <span className="text-lg font-semibold">IA Jurídica - Asistente Legal Bilingüe</span>
          </div>
          <p className="text-gray-300">{t.footer}</p>
        </div>
      </footer>
    </div>
  );
}
