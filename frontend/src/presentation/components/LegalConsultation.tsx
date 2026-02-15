import { type FormEvent, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle, Clock, Download, Send } from 'lucide-react';
import { createDownloadLegalPdfUseCase } from '../../application/legal/use-cases/download-legal-pdf';
import type { LegalConsultationResult, SupportedLanguage } from '../../domain/legal/types';
import { HttpLegalGateway } from '../../infrastructure/legal/http-legal-gateway';
import { consultationTranslations } from '../i18n/translations';

interface LegalConsultationProps {
  currentLanguage: SupportedLanguage;
  isLoading: boolean;
  setIsLoading: (isLoading: boolean) => void;
}

export function LegalConsultation({
  currentLanguage,
  isLoading,
  setIsLoading
}: LegalConsultationProps) {
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState<LegalConsultationResult | null>(null);
  const [streamedAnswer, setStreamedAnswer] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);

  const gateway = useMemo(() => new HttpLegalGateway(), []);
  const downloadLegalPdf = useMemo(() => createDownloadLegalPdfUseCase(gateway), [gateway]);

  const t = consultationTranslations[currentLanguage];

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    setError(null);
    setResponse(null);
    setStreamedAnswer('');

    try {
      const consultResponse = await fetch('/api/legal/consult', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          query: query.trim(),
          language: currentLanguage,
          stream: true,
          context: {
            userAgent: navigator.userAgent,
            timestamp: new Date().toISOString()
          }
        })
      });

      if (!consultResponse.ok) {
        const contentType = consultResponse.headers.get('content-type') || '';
        let message = 'No se pudo procesar la consulta legal.';

        if (contentType.includes('application/json')) {
          const payload = (await consultResponse.json()) as { error?: string; message?: string };
          message = payload.error || payload.message || message;
        } else {
          const payloadText = await consultResponse.text();
          if (payloadText.trim()) {
            message = payloadText;
          }
        }

        throw new Error(message);
      }

      if (!consultResponse.body) {
        throw new Error('El navegador no soporta streaming de respuestas en este entorno.');
      }

      const reader = consultResponse.body.getReader();
      const decoder = new TextDecoder();
      let finalText = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        finalText += chunk;
        setStreamedAnswer(finalText);
      }

      finalText += decoder.decode();

      if (!finalText.trim()) {
        throw new Error('No se recibio contenido en streaming.');
      }

      const result: LegalConsultationResult = {
        query: query.trim(),
        language: currentLanguage,
        response:
          currentLanguage === 'quechua'
            ? { spanish: '', quechua: finalText }
            : { spanish: finalText, quechua: '' },
        sources: []
      };

      setResponse(result);
    } catch (consultError) {
      const message = consultError instanceof Error ? consultError.message : 'Error desconocido';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownloadPdf = async () => {
    if (!response) return;

    setIsGeneratingPdf(true);
    setError(null);

    try {
      const pdfBlob = await downloadLegalPdf({
        query: response.query || query,
        response: response.response,
        userData: {
          language: currentLanguage,
          timestamp: new Date().toISOString()
        }
      });

      const url = window.URL.createObjectURL(pdfBlob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `informe-legal-${Date.now()}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (pdfError) {
      const message = pdfError instanceof Error ? pdfError.message : 'No se pudo generar el PDF.';
      setError(message);
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  const spanishResponse =
    response?.response.spanish || (currentLanguage === 'spanish' ? streamedAnswer : '');
  const quechuaResponse =
    response?.response.quechua || (currentLanguage === 'quechua' ? streamedAnswer : '');

  return (
    <div className="max-w-4xl mx-auto">
      <div className="bg-white rounded-lg shadow-xl p-8">
        <h2 className="text-3xl font-bold text-center mb-8 text-gray-800">{t.title}</h2>

        <form onSubmit={handleSubmit} className="mb-8">
          <div className="mb-6">
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t.placeholder}
              className="w-full p-4 border-2 border-gray-300 rounded-lg focus:border-blue-500 focus:outline-none resize-none h-32 text-gray-700"
              disabled={isLoading}
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || !query.trim()}
            className="w-full bg-blue-700 text-white py-3 px-6 rounded-lg font-semibold hover:bg-blue-800 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
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

        <div className="mb-8 p-4 bg-gray-50 rounded-lg">
          <h3 className="font-semibold text-gray-700 mb-3">{t.examplesTitle}</h3>
          <div className="space-y-2">
            {t.examples.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => setQuery(example)}
                className="block w-full text-left p-3 bg-white rounded border border-gray-200 hover:border-blue-300 hover:bg-blue-50 transition-colors text-gray-600"
                disabled={isLoading}
              >
                {example}
              </button>
            ))}
          </div>
        </div>

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

        {(isLoading || response || streamedAnswer) && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
              <div className="flex items-center">
                {isLoading && !response && !streamedAnswer ? (
                  <Clock className="w-6 h-6 text-blue-600 mr-2 animate-spin" />
                ) : (
                  <CheckCircle className="w-6 h-6 text-green-600 mr-2" />
                )}
                <h3 className="text-2xl font-semibold text-gray-800">{t.responseTitle}</h3>
              </div>
              <button
                type="button"
                onClick={handleDownloadPdf}
                disabled={isGeneratingPdf || !response}
                className="bg-emerald-700 text-white py-2 px-4 rounded-lg font-medium hover:bg-emerald-800 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center"
              >
                {isGeneratingPdf ? (
                  <>
                    <Clock className="w-4 h-4 mr-2 animate-spin" />
                    {t.generating}
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4 mr-2" />
                    {t.downloadPdf}
                  </>
                )}
              </button>
            </div>

            {spanishResponse && (
              <div className="p-6 bg-blue-50 rounded-lg border border-blue-200">
                <h4 className="font-semibold text-blue-800 mb-3">{t.spanishResponse}</h4>
                <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">{spanishResponse}</p>
              </div>
            )}

            {quechuaResponse && (
              <div className="p-6 bg-emerald-50 rounded-lg border border-emerald-200">
                <h4 className="font-semibold text-emerald-800 mb-3">{t.quechuaResponse}</h4>
                <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">{quechuaResponse}</p>
              </div>
            )}

            {isLoading && !spanishResponse && !quechuaResponse && (
              <div className="p-6 bg-slate-50 rounded-lg border border-slate-200">
                <p className="text-slate-700">{t.consulting}</p>
              </div>
            )}

            <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
              <div className="flex items-start">
                <AlertCircle className="w-5 h-5 text-amber-700 mr-2 mt-0.5 flex-shrink-0" />
                <p className="text-amber-800 text-sm">{t.disclaimer}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
