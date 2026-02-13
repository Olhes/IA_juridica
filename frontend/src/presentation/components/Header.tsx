import { Globe, MessageSquare, Shield } from 'lucide-react';
import type { SupportedLanguage } from '../../domain/legal/types';

interface HeaderProps {
  currentLanguage: SupportedLanguage;
  tagline: string;
}

export function Header({ currentLanguage, tagline }: HeaderProps) {
  return (
    <header className="bg-white shadow-md">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="bg-blue-700 p-2 rounded-lg">
              <MessageSquare className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-800">IA Jurídica</h1>
              <p className="text-sm text-gray-600">{tagline}</p>
            </div>
          </div>

          <div className="hidden md:flex items-center space-x-6">
            <div className="flex items-center space-x-2 text-gray-600">
              <Globe className="w-5 h-5" />
              <span className="text-sm font-medium">
                {currentLanguage === 'spanish' ? 'Espanol/Quechua' : 'Quechua/Espanol'}
              </span>
            </div>
            <div className="flex items-center space-x-2 text-gray-600">
              <Shield className="w-5 h-5" />
              <span className="text-sm font-medium">
                {currentLanguage === 'spanish' ? 'Derecho Familiar' : 'Familiar Derecho'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
