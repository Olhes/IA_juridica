import type { SupportedLanguage } from '../../domain/legal/types';

interface HomeTranslation {
  title: string;
  subtitle: string;
  description: string;
  tagline: string;
  consultTitle: string;
  footer: string;
  features: {
    accessibility: string;
    accessibilityDescription: string;
    democratization: string;
    democratizationDescription: string;
    practical: string;
    practicalDescription: string;
  };
}

interface ConsultationTranslation {
  title: string;
  placeholder: string;
  consultButton: string;
  consulting: string;
  downloadPdf: string;
  spanishResponse: string;
  quechuaResponse: string;
  responseTitle: string;
  errorTitle: string;
  generating: string;
  examplesTitle: string;
  examples: string[];
  disclaimer: string;
}

export const homeTranslations: Record<SupportedLanguage, HomeTranslation> = {
  spanish: {
    title: 'IA Juridica',
    subtitle: 'Asistente Legal Bilingue',
    description: 'Orientacion legal basica en derecho digital para comunidades andinas.',
    tagline: 'Acceso a la justicia para comunidades andinas',
    consultTitle: 'Consulta Legal',
    footer: 'Derecho Digital - Proteccion de Datos - Acceso a la Justicia',
    features: {
      accessibility: 'Accesibilidad Linguistica',
      accessibilityDescription:
        'Responde en quechua y espanol con enfoque cultural y practico.',
      democratization: 'Democratizacion del Conocimiento',
      democratizationDescription:
        'Entrega explicaciones claras sobre derechos y rutas legales.',
      practical: 'Orientacion Practica',
      practicalDescription:
        'Sugiere pasos accionables y permite descargar reportes para seguimiento.'
    }
  },
  quechua: {
    title: 'IA Juridica',
    subtitle: 'Iskay Simi Yachachiq Legal',
    description: 'Derecho digitalmanta yachachiy, runasimipi kastillasimipipas.',
    tagline: 'Andinas comunidades para justicia acceso',
    consultTitle: 'Legal Consulta',
    footer: 'Digital Derecho - Datos Proteccion - Justicia Acceso',
    features: {
      accessibility: 'Simi Accesibilidad',
      accessibilityDescription: 'Quechua simipi kastilla simipipas kutichiyta qun.',
      democratization: 'Yachay Rurasqa',
      democratizationDescription: 'Derechokunaqa sutita willakun, ima ruwaykunatapas.',
      practical: 'Practico Orientacion',
      practicalDescription: 'Ruranapaq pasos qun, chaymanta PDF informe uraykachiy atikun.'
    }
  }
};

export const consultationTranslations: Record<SupportedLanguage, ConsultationTranslation> = {
  spanish: {
    title: 'Consulta Legal',
    placeholder: 'Escribe tu consulta sobre violencia familiar, pension, denuncias o procesos.',
    consultButton: 'Consultar',
    consulting: 'Consultando...',
    downloadPdf: 'Descargar Informe PDF',
    spanishResponse: 'Respuesta en Espanol',
    quechuaResponse: 'Respuesta en Quechua',
    responseTitle: 'Respuesta Legal',
    errorTitle: 'Error en la Consulta',
    generating: 'Generando...',
    examplesTitle: 'Ejemplos de Consultas',
    examples: [
      'Que hago si mi pareja me golpea?',
      'Como solicito pension de alimentos para mis hijos?',
      'Que medidas de proteccion puedo pedir hoy?'
    ],
    disclaimer:
      'Esta orientacion no reemplaza la asesoria profesional de una abogada o abogado.'
  },
  quechua: {
    title: 'Legal Consulta',
    placeholder: 'Violencia, pension, denuncias utaq proceso legalmanta tapukuy qillqay.',
    consultButton: 'Consultar',
    consulting: 'Consultando...',
    downloadPdf: 'PDF Informe Descargar',
    spanishResponse: 'Kastilla Simipi Respuesta',
    quechuaResponse: 'Quechua Simipi Respuesta',
    responseTitle: 'Legal Respuesta',
    errorTitle: 'Consultapi Error',
    generating: 'Generando...',
    examplesTitle: 'Consulta Ejemplos',
    examples: [
      'Wasiypi maqanakuy kaptin, imataq ruwani?',
      'Wawakunapaq pensionta imaynataq mañani?',
      'Kunan pacha ima proteccionta mañakuy atini?'
    ],
    disclaimer: 'Kay orientacionqa mana reemplazanchu abogadopa profesional yanapayninta.'
  }
};
