export type SupportedLanguage = 'spanish' | 'quechua';

export type LegalTopic =
  | 'violencia_familiar'
  | 'pension_alimentos'
  | 'medidas_proteccion'
  | 'regimen_visitas'
  | 'denuncias_procesos';

export type ValidationStatus = 'passed' | 'warned' | 'corrected' | 'failed';
export type ConfidenceLevel = 'high' | 'medium' | 'low';
export type UrgencyLevel = 'bajo' | 'medio' | 'alto' | 'critico';

// ---- API Response Shapes ----

export interface LegalStep {
  paso: number;
  descripcion: string;
  documentos_requeridos: string[];
  plazo: string | null;
  lugar: string | null;
}

export interface LegalResource {
  nombre: string;
  tipo: string;
  contacto: string | null;
  horario: string | null;
  descripcion: string;
}

export interface LegalWarning {
  tipo: string;
  mensaje: string;
  urgencia: UrgencyLevel;
}

export interface LegalSource {
  nombre: string;
  tipo: string;
  numero: string | null;
  enlace: string | null;
}

export interface GeneralLegalResponse {
  tema: LegalTopic;
  respuesta_espanol: string;
  respuesta_quechua: string;
  pasos_recomendados: LegalStep[];
  recursos: LegalResource[];
  advertencias: LegalWarning[];
  fuentes: LegalSource[];
  confianza: number;
  fecha_respuesta: string;
}

export interface CrossCheckSummary {
  is_grounded: boolean;
  overlap_score: number;
  ungrounded_claims: string[];
  supporting_chunks: string[];
}

export interface ValidationReport {
  status: ValidationStatus;
  confidence: ConfidenceLevel;
  confidence_score: number;
  hallucination_risk: number;
  is_grounded: boolean;
  corrections_applied: number;
  flags: unknown[];
  cross_check: CrossCheckSummary | null;
  cultural_issues: string[];
  warnings: string[];
  processing_time_ms: number;
  validated_at: string;
}

export interface LegalQueryApiResponse {
  success: boolean;
  query: string;
  language: string;
  cached: boolean;
  response: GeneralLegalResponse;
  sources: string[];
  validation: ValidationReport;
  metadata: {
    rerank_scores: number[];
    retrieval_method: string;
    total_candidates: number;
    enriched_context: Record<string, unknown>;
    optimizer_stats: Record<string, unknown>;
  };
}

// ---- Chat UI Types ----

export type MessageRole = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  /** Streaming text (progressively updated) */
  streamingContent?: string;
  /** Final structured API response (available after /legal-query completes) */
  apiResponse?: LegalQueryApiResponse;
  isStreaming?: boolean;
  isLoadingFull?: boolean;
  timestamp: Date;
  error?: string;
}

// ---- Legacy types kept for backward compat ----

export interface LegalQueryContext {
  userAgent: string;
  timestamp: string;
}

export interface LegalStructuredResponse {
  spanish: string;
  quechua: string;
  [key: string]: unknown;
}

export interface LegalConsultationResult {
  query: string;
  language: string;
  response: LegalStructuredResponse;
  sources: unknown[];
  [key: string]: unknown;
}

export interface LegalConsultationEnvelope {
  success: boolean;
  data?: LegalConsultationResult;
  error?: string;
  message?: string;
}

export interface PdfDownloadRequest {
  query: string;
  response: Record<string, unknown>;
  userData: {
    language: SupportedLanguage;
    timestamp: string;
  };
}
