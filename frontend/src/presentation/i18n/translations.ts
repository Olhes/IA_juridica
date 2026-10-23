export const homeTranslations = {
  spanish: {
    title: 'IA Juridica',
    tagline: 'Orientacion legal bilingue',
    footer: 'Informacion orientativa, no reemplaza asesoria profesional.',
  },
  quechua: {
    title: 'IA Juridica',
    tagline: 'Iskay simipi legal yanapay',
    footer: 'Kay willakuyqa orientacionllam, mana profesional asesoriata rantinchu.',
  },
} as const;

/**
 * Textos del chat (etapas, errores, tiempos).
 * El quechua es una primera redacción pendiente de revisión por un hablante nativo.
 */
export const chatTranslations = {
  spanish: {
    stageLabels: {
      retrieval: 'Buscando en el corpus',
      generation: 'Redactando',
      validation: 'Verificando',
      translating: 'Traduciendo',
    },
    stagesLabel: 'Progreso de la consulta',
    errorTitle: 'No se pudo completar la consulta',
    errors: {
      RETRIEVAL_UNAVAILABLE: 'No pudimos consultar el corpus legal en este momento.',
      GENERATION_UNAVAILABLE: 'No pudimos redactar la respuesta en este momento.',
      TRANSLATION_UNAVAILABLE: 'La traducción no está disponible. Intenta consultar en español.',
      TIMEOUT: 'La consulta tardó demasiado en responder.',
      INTERNAL_ERROR: 'Ocurrió un error inesperado.',
      DEFAULT: 'No se pudo completar la respuesta.',
    },
    retry: 'Reintentar',
    answeredIn: (seconds: string) => `Respondió en ${seconds} s`,
    answeredFromCache: 'Respuesta desde caché',
    timingsDetail: 'Ver desglose por etapa',
    timingStageLabels: {
      translate_in: 'Traducción de la consulta',
      retrieval: 'Búsqueda',
      generation: 'Redacción',
      validation: 'Verificación',
      translate_out: 'Traducción de la respuesta',
    },
  },
  quechua: {
    stageLabels: {
      retrieval: 'Corpuspi maskashan',
      generation: 'Qillqashan',
      validation: 'Chiqaqchashan',
      translating: 'Runasimiman tikrashan',
    },
    stagesLabel: 'Tapuypa puririynin',
    errorTitle: 'Manam tapuyta tukuchiyta atirqanchu',
    errors: {
      RETRIEVAL_UNAVAILABLE: 'Kunan manam corpus legalta maskayta atirqanchu.',
      GENERATION_UNAVAILABLE: 'Kunan manam kutichiyta qillqayta atirqanchu.',
      TRANSLATION_UNAVAILABLE: 'Manam tikrayqa kanchu. Castellanopi tapuy.',
      TIMEOUT: 'Tapuyqa nisqamanta aswan unayta kutichirqan.',
      INTERNAL_ERROR: 'Mana suyasqa pantay karqan.',
      DEFAULT: 'Manam kutichiyta tukuchiyta atirqanchu.',
    },
    retry: 'Yapamanta ruway',
    answeredIn: (seconds: string) => `${seconds} s ukhupi kutichirqan`,
    answeredFromCache: 'Waqaychasqamanta kutichiy',
    timingsDetail: 'Sapa ruwaypa tiemponta qhaway',
    timingStageLabels: {
      translate_in: 'Tapuyta tikray',
      retrieval: 'Maskay',
      generation: 'Qillqay',
      validation: 'Chiqaqchay',
      translate_out: 'Kutichiyta tikray',
    },
  },
} as const;
