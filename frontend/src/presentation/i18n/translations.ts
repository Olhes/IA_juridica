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
    insufficient: {
      title: 'No hay evidencia suficiente en el corpus',
      body: 'No encontramos fuentes que respalden una respuesta a esta consulta y preferimos no inventarla. Consulta con una persona profesional o con estos servicios gratuitos.',
      resourcesLabel: 'Dónde pedir ayuda',
      // Datos de contacto: confirmar con el equipo antes de publicar.
      resources: [
        { name: 'Línea 100', detail: 'Orientación gratuita sobre violencia familiar y sexual, las 24 horas.', contact: '100' },
        { name: 'Centros Emergencia Mujer (CEM)', detail: 'Atención legal, psicológica y social gratuita; se solicita a través de la Línea 100.', contact: '100' },
        { name: 'Defensoría del Pueblo', detail: 'Orientación gratuita sobre tus derechos.', contact: '0800-15170' },
      ],
    },
    trust: {
      summary: '¿Por qué confiar en esta respuesta?',
      evidence: (n: number) => (n === 1 ? 'Se apoya en 1 fuente recuperada del corpus.' : `Se apoya en ${n} fuentes recuperadas del corpus.`),
      noEvidence: 'No se recuperaron fuentes del corpus.',
      grounded: 'El validador encontró respaldo en las fuentes.',
      notGrounded: 'El validador no encontró respaldo suficiente en las fuentes.',
      reliable: 'El sistema la considera fiable.',
      notReliable: 'El sistema no la considera fiable: contrástala con una persona profesional.',
      risk: (percent: string) => `Riesgo estimado de alucinación: ${percent} %.`,
      citations: (verified: number, total: number) => `${verified} de ${total} citas legales verificadas en las fuentes.`,
      noCitations: 'La respuesta no cita normas concretas.',
      disclaimer: 'Es orientación informativa: no certifica verdad jurídica ni reemplaza asesoría profesional.',
    },
    citations: {
      label: 'Citas legales',
      verified: 'Verificada en las fuentes',
      unverified: 'No se encontró en las fuentes recuperadas',
      excerptFrom: (source: string) => `Extracto de ${source}`,
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
    insufficient: {
      title: 'Corpuspi mana haypachu willakuy',
      body: 'Manam tarirqanchu kay tapuyta takyachiq willakuykunata, chaymi mana llullakuyta munani. Huk yachaq runawan icha kay mana qullqiyuq yanapaykunawan rimay.',
      resourcesLabel: 'Maymanta yanapayta maskana',
      resources: [
        { name: 'Línea 100', detail: 'Mana qullqiwan yanapay, 24 ura.', contact: '100' },
        { name: 'Centros Emergencia Mujer (CEM)', detail: 'Mana qullqiwan yanapay; Línea 100 nisqawan mañakuy.', contact: '100' },
        { name: 'Defensoría del Pueblo', detail: 'Mana qullqiwan derechoykikunamanta yanapay.', contact: '0800-15170' },
      ],
    },
    trust: {
      summary: '¿Imanaqtin kay kutichiyta iñina?',
      evidence: (n: number) => `${n} corpusmanta willakuywan sayasqa.`,
      noEvidence: 'Manam corpusmanta willakuy tarisqachu.',
      grounded: 'Chiqaqchaqmi willakuykunapi sayasqa tarirqan.',
      notGrounded: 'Chiqaqchaqqa mana hayk’aq willakuykunapi sayasqa tarirqanchu.',
      reliable: 'Sistemam iñiypaq nin.',
      notReliable: 'Sistemaqa mana iñiypaqchu nin: huk yachaq runawan chiqaqchay.',
      risk: (percent: string) => `Llullakuy ima hina kanman: ${percent} %.`,
      citations: (verified: number, total: number) => `${total} norma sutichasqamanta ${verified} chiqaqchasqa.`,
      noCitations: 'Kutichiyqa manam normakunata sutinchanchu.',
      disclaimer: 'Willakuy yanapaylla: mana derecho chiqaqta takyachinchu nitaq yachaq runata rantinchu.',
    },
    citations: {
      label: 'Normakuna sutichasqa',
      verified: 'Willakuykunapi chiqaqchasqa',
      unverified: 'Taripasqa willakuykunapi mana tarisqachu',
      excerptFrom: (source: string) => `${source} nisqamanta pisi simi`,
    },
  },
} as const;
