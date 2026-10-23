import type { ErrorEvent, StageEvent } from './streamEvents.generated';

export type SupportedLanguage = 'spanish' | 'quechua';

/** Etapas del pipeline (contrato NDJSON v1). */
export type PipelineStage = StageEvent['stage'];
/** Códigos de error del stream (contrato NDJSON v1). */
export type StreamErrorCode = ErrorEvent['code'];

export interface StreamErrorInfo {
  code: StreamErrorCode;
  retryable: boolean;
}

/** Tiempos por etapa que entrega el backend en `metadata.timings`. Solo números. */
export interface ResponseTimings {
  total_ms: number;
  stages: Partial<Record<PipelineStage, number>>;
  cache_hit: boolean;
}

export type LegalTopic =
  | 'violencia_familiar'
  | 'pension_alimentos'
  | 'medidas_proteccion'
  | 'regimen_visitas'
  | 'denuncias_procesos';

export type ValidationStatus = 'passed' | 'warned' | 'corrected' | 'failed';
export type ConfidenceLevel = 'high' | 'medium' | 'low';
export type UrgencyLevel = 'bajo' | 'medio' | 'alto' | 'critico';

// ---- Estructuras de respuesta de la API ----

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

/** Cita legal verificada contra las fuentes recuperadas (`metadata.citations`). */
export interface CitationCheck {
  key: string;
  /** Texto tal como lo citó la respuesta. */
  text: string;
  status: 'verified' | 'unverified';
  source: string | null;
  /** Extracto del corpus donde aparece la cita; nunca texto del modelo. */
  excerpt: string | null;
}

/** Fuente recuperada con su relevancia y un extracto del corpus (`metadata.evidence`). */
export interface EvidenceItem {
  source: string;
  relevance: number | null;
  excerpt: string;
  /** Camino de recuperación: grafo de conocimiento (LightRAG) o búsqueda léxica local. */
  origin?: 'lightrag' | 'lexical';
  /** Casaciones citadas en el fragmento; vacío si no es jurisprudencia. */
  jurisprudence?: string[];
}

export type EvidenceStatus = 'retrieved' | 'insufficient_evidence';

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
  /** El pipeline lo considera fiable: hubo evidencia y el validador la aprobó. No certifica verdad jurídica. */
  is_reliable?: boolean;
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
    timings?: ResponseTimings;
    evidence_status?: EvidenceStatus;
    citations?: CitationCheck[];
    evidence?: EvidenceItem[];
    rerank_scores: number[];
    retrieval_method: string;
    total_candidates: number;
    enriched_context: Record<string, unknown>;
    optimizer_stats: Record<string, unknown>;
  };
}

// ---- Tipos de la interfaz de chat ----

export type MessageRole = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  /** Texto en streaming (actualizado progresivamente). */
  streamingContent?: string;
  /** Respuesta estructurada final de la API (disponible al terminar el flujo). */
  apiResponse?: LegalQueryApiResponse;
  isStreaming?: boolean;
  isLoadingFull?: boolean;
  /** Etapa del pipeline en curso mientras llega la respuesta. */
  stage?: PipelineStage;
  /** Etapas ya terminadas, en orden de llegada. */
  completedStages?: PipelineStage[];
  /** Error del stream con código; la UI lo traduce y ofrece reintentar. */
  errorInfo?: StreamErrorInfo;
  timestamp: Date;
  error?: string;
  language?: SupportedLanguage;
  tokens?: number;
  metadata?: Record<string, any>;
}

// ---- Sesión de chat (varios hilos) ----

export interface ChatSessionMeta {
  id: string;
  /** Primer mensaje del usuario (truncado) — usado como título */
  title: string;
  /** Primer fragmento de la respuesta del asistente (truncado) */
  preview: string;
  language: SupportedLanguage;
  createdAt: string;   // ISO string
  updatedAt: string;   // ISO string
  messageCount: number;
}
