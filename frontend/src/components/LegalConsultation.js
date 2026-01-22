import React, { useState } from 'react';
import { Send, Download, AlertCircle, CheckCircle, Clock } from 'lucide-react';
import axios from 'axios';

const LegalConsultation = ({ currentLanguage, isLoading, setIsLoading }) => {
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [isGeneratingPDF, setIsGeneratingPDF] = useState(false);

  const translations = {
    spanish: {
      title: 'Consulta Legal',
      placeholder: 'Escribe tu consulta sobre derecho digital, protección de datos, ciberseguridad...',
      consultButton: 'Consultar',
      consulting: 'Consultando...',
      downloadPDF: 'Descargar Informe PDF',
      responseTitle: 'Respuesta Legal',
      spanishResponse: 'Respuesta en Español',
      quechuaResponse: 'Respuesta en Quechua',
      errorTitle: 'Error en la Consulta',
      retryButton: 'Intentar de Nuevo',
      examples: {
        title: 'Ejemplos de Consultas:',
        items: [
          '¿Qué hago si robaron mi contraseña?',
          '¿Cómo protejo mis datos en redes sociales?',
          '¿Es seguro usar WiFi público para banca?'
        ]
      },
      disclaimer: 'Esta es orientación básica y no reemplaza el consejo de un abogado profesional.'
    },
    quechua: {
      title: 'Legal Consulta',
      placeholder: 'Digital derecho, datos proteccion, ciberseguridad acerca consulta escribi...',
      consultButton: 'Consultar',
      consulting: 'Consultando...',
      downloadPDF: 'PDF Informe Descargar',
      responseTitle: 'Legal Respuesta',
      spanishResponse: 'Kastilla Simipi Respuesta',
      quechuaResponse: 'Quechua Simipi Respuesta',
      errorTitle: 'Consultapi Error',
      retryButton: 'Nuevo Intentar',
      examples: {
        title: 'Consulta Ejemplos:',
        items: [
          '¿Contraseña robashqañam, ima ruwani?',
          '¿Redes socialespi datos proteccion ima ruwani?',
          '¿WiFi público banca segura ruwani?'
        ]
      },
      disclaimer: 'Kani basic orientacion, abogado profesional consejo reemplaza chu.'
    }
  };

  const t = translations[currentLanguage];

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    setError(null);
    setResponse(null);

    try {
      const response = await axios.post('/api/legal/consult', {
        query: query.trim(),
        language: currentLanguage,
        context: {
          userAgent: navigator.userAgent,
          timestamp: new Date().toISOString()
        }
      });

      if (response.data.success) {
        setResponse(response.data.data);
      } else {
        setError(response.data.error || 'Error desconocido');
      }
    } catch (err) {
      console.error('Error en consulta:', err);
      setError(
        err.response?.data?.error || 
        err.message || 
        'Error de conexión. Intenta nuevamente.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownloadPDF = async () => {
    if (!response) return;

    setIsGeneratingPDF(true);
    try {
      const pdfResponse = await axios.post('/api/legal/pdf', {
        legalResponse: response,
        userData: {
          language: currentLanguage,
          timestamp: new Date().toISOString()
        }
      }, {
        responseType: 'blob'
      });

      // Crear URL y descargar el PDF
      const url = window.URL.createObjectURL(new Blob([pdfResponse.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `informe-legal-${Date.now()}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

    } catch (err) {
      console.error('Error generando PDF:', err);
      setError('Error al generar el PDF. Intenta nuevamente.');
    } finally {
      setIsGeneratingPDF(false);
    }
  };

  const handleExampleClick = (example) => {
    setQuery(example);
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="bg-white rounded-lg shadow-xl p-8">
        <h2 className="text-3xl font-bold text-center mb-8 text-gray-800">
          {t.title}
        </h2>

        <form onSubmit={handleSubmit} className="mb-8">
          <div className="mb-6">
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t.placeholder}
              className="w-full p-4 border-2 border-gray-300 rounded-lg focus:border-blue-500 focus:outline-none resize-none h-32 text-gray-700"
              disabled={isLoading}
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || !query.trim()}
            className="w-full bg-blue-600 text-white py-3 px-6 rounded-lg font-semibold hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
          >
            {isLoading ? (
              <>
                <Clock className="w-5 h-5 mr-2 animate-spin" />
                {t.consulting}
              </>
            ) : (
              <>
                <Send className="w-5 h-5 mr-2" />
                {t.consultButton}
              </>
            )}
          </button>
        </form>

        {/* Ejemplos de consultas */}
        <div className="mb-8 p-4 bg-gray-50 rounded-lg">
          <h3 className="font-semibold text-gray-700 mb-3">{t.examples.title}</h3>
          <div className="space-y-2">
            {t.examples.items.map((example, index) => (
              <button
                key={index}
                onClick={() => handleExampleClick(example)}
                className="block w-full text-left p-3 bg-white rounded border border-gray-200 hover:border-blue-300 hover:bg-blue-50 transition-colors text-gray-600"
                disabled={isLoading}
              >
                {example}
              </button>
            ))}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <div className="flex items-start">
              <AlertCircle className="w-5 h-5 text-red-600 mr-3 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="font-semibold text-red-800 mb-1">{t.errorTitle}</h3>
                <p className="text-red-700">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Respuesta */}
        {response && (
          <div className="space-y-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center">
                <CheckCircle className="w-6 h-6 text-green-600 mr-2" />
                <h3 className="text-2xl font-semibold text-gray-800">{t.responseTitle}</h3>
              </div>
              <button
                onClick={handleDownloadPDF}
                disabled={isGeneratingPDF}
                className="bg-green-600 text-white py-2 px-4 rounded-lg font-medium hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center"
              >
                {isGeneratingPDF ? (
                  <>
                    <Clock className="w-4 h-4 mr-2 animate-spin" />
                    Generando...
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4 mr-2" />
                    {t.downloadPDF}
                  </>
                )}
              </button>
            </div>

            {/* Respuesta en español */}
            {response.response.spanish && (
              <div className="p-6 bg-blue-50 rounded-lg border border-blue-200">
                <h4 className="font-semibold text-blue-800 mb-3">{t.spanishResponse}</h4>
                <div className="text-gray-700 whitespace-pre-wrap leading-relaxed">
                  {response.response.spanish}
                </div>
              </div>
            )}

            {/* Respuesta en quechua */}
            {response.response.quechua && (
              <div className="p-6 bg-green-50 rounded-lg border border-green-200">
                <h4 className="font-semibold text-green-800 mb-3">{t.quechuaResponse}</h4>
                <div className="text-gray-700 whitespace-pre-wrap leading-relaxed">
                  {response.response.quechua}
                </div>
              </div>
            )}

            {/* Descargo de responsabilidad */}
            <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
              <div className="flex items-start">
                <AlertCircle className="w-5 h-5 text-yellow-600 mr-2 mt-0.5 flex-shrink-0" />
                <p className="text-yellow-800 text-sm">{t.disclaimer}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default LegalConsultation;
