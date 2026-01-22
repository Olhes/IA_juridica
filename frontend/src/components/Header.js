import React from 'react';
import { MessageSquare, Shield, Globe } from 'lucide-react';

const Header = ({ currentLanguage }) => {
  const translations = {
    spanish: {
      tagline: 'Acceso a la justicia para comunidades andinas'
    },
    quechua: {
      tagline: 'Andinas comunidades para justicia acceso'
    }
  };

  const t = translations[currentLanguage];

  return (
    <header className="bg-white shadow-md">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="bg-blue-600 p-2 rounded-lg">
              <MessageSquare className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-800">IA Jurídica</h1>
              <p className="text-sm text-gray-600">{t.tagline}</p>
            </div>
          </div>
          
          <div className="flex items-center space-x-6">
            <div className="flex items-center space-x-2 text-gray-600">
              <Globe className="w-5 h-5" />
              <span className="text-sm font-medium">
                {currentLanguage === 'spanish' ? 'Español/Quechua' : 'Quechua/Español'}
              </span>
            </div>
            <div className="flex items-center space-x-2 text-gray-600">
              <Shield className="w-5 h-5" />
              <span className="text-sm font-medium">
                {currentLanguage === 'spanish' ? 'Derecho Digital' : 'Digital Derecho'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
