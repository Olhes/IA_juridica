import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { MessageSquare, FileText, Globe, Shield } from 'lucide-react';
import Header from './components/Header';
import LegalConsultation from './components/LegalConsultation';
import LanguageToggle from './components/LanguageToggle';
import './App.css';

function App() {
  const [currentLanguage, setCurrentLanguage] = useState('spanish');
  const [isLoading, setIsLoading] = useState(false);

  const translations = {
    spanish: {
      title: 'IA Jurídica',
      subtitle: 'Asistente Legal Bilingüe',
      description: 'Orientación legal básica en derecho digital, disponible en quechua y español',
      features: {
        accessibility: 'Accesibilidad Lingüística',
        democratization: 'Democratización del Conocimiento',
        practical: 'Orientación Práctica'
      }
    },
    quechua: {
      title: 'IA Jurídica',
      subtitle: 'Iskay Simi Yachachiq Legal',
      description: 'Digital derechopi basic orientacion, quechua simipi kastilla simipipis',
      features: {
        accessibility: 'Simi Accesibilidad',
        democratization: 'Yachay Rurasqa',
        practical: 'Practico Orientacion'
      }
    }
  };

  const t = translations[currentLanguage];

  const handleLanguageChange = (language) => {
    setCurrentLanguage(language);
    localStorage.setItem('preferredLanguage', language);
  };

  useEffect(() => {
    const savedLanguage = localStorage.getItem('preferredLanguage');
    if (savedLanguage && ['spanish', 'quechua'].includes(savedLanguage)) {
      setCurrentLanguage(savedLanguage);
    }
  }, []);

  return (
    <Router>
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
        <Header currentLanguage={currentLanguage} />
        
        <main className="container mx-auto px-4 py-8">
          <div className="text-center mb-12">
            <h1 className="text-4xl md:text-6xl font-bold text-gray-800 mb-4">
              {t.title}
            </h1>
            <h2 className="text-xl md:text-2xl text-gray-600 mb-6">
              {t.subtitle}
            </h2>
            <p className="text-lg text-gray-700 max-w-3xl mx-auto mb-8">
              {t.description}
            </p>
            
            <LanguageToggle 
              currentLanguage={currentLanguage}
              onLanguageChange={handleLanguageChange}
            />
          </div>

          <div className="grid md:grid-cols-3 gap-8 mb-12">
            <div className="bg-white rounded-lg shadow-lg p-6 transform hover:scale-105 transition-transform">
              <div className="flex justify-center mb-4">
                <Globe className="w-12 h-12 text-blue-600" />
              </div>
              <h3 className="text-xl font-semibold text-center mb-3">
                {t.features.accessibility}
              </h3>
              <p className="text-gray-600 text-center">
                {currentLanguage === 'spanish' 
                  ? 'Responde tanto en quechua como en español, respetando la cosmovisión andina.'
                  : 'Quechua simipim kastilla simipim respuestas, cosmovicion andina respetando.'
                }
              </p>
            </div>

            <div className="bg-white rounded-lg shadow-lg p-6 transform hover:scale-105 transition-transform">
              <div className="flex justify-center mb-4">
                <Shield className="w-12 h-12 text-green-600" />
              </div>
              <h3 className="text-xl font-semibold text-center mb-3">
                {t.features.democratization}
              </h3>
              <p className="text-gray-600 text-center">
                {currentLanguage === 'spanish'
                  ? 'Explicación clara de derechos digitales y protección de datos.'
                  : 'Digital derechos y datos proteccion clara explicacion.'
                }
              </p>
            </div>

            <div className="bg-white rounded-lg shadow-lg p-6 transform hover:scale-105 transition-transform">
              <div className="flex justify-center mb-4">
                <FileText className="w-12 h-12 text-purple-600" />
              </div>
              <h3 className="text-xl font-semibold text-center mb-3">
                {t.features.practical}
              </h3>
              <p className="text-gray-600 text-center">
                {currentLanguage === 'spanish'
                  ? 'Genera informes PDF personalizados para consultar después.'
                  : 'Personalizado PDF informes generan, despues consulta para.'
                }
              </p>
            </div>
          </div>

          <Routes>
            <Route 
              path="/" 
              element={
                <LegalConsultation 
                  currentLanguage={currentLanguage}
                  isLoading={isLoading}
                  setIsLoading={setIsLoading}
                />
              } 
            />
          </Routes>
        </main>

        <footer className="bg-gray-800 text-white py-8 mt-16">
          <div className="container mx-auto px-4 text-center">
            <div className="flex justify-center items-center mb-4">
              <MessageSquare className="w-6 h-6 mr-2" />
              <span className="text-lg font-semibold">
                IA Jurídica - Asistente Legal Bilingüe
              </span>
            </div>
            <p className="text-gray-400">
              {currentLanguage === 'spanish'
                ? 'Derecho Digital • Protección de Datos • Acceso a la Justicia'
                : 'Digital Derecho • Datos Proteccion • Justicia Acceso'
              }
            </p>
            <p className="text-gray-500 text-sm mt-2">
              © 2024 IA Jurídica. Para comunidades andinas y rurales de América Latina.
            </p>
          </div>
        </footer>
      </div>
    </Router>
  );
}

export default App;
