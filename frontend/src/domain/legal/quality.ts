/** Tipos de las vistas de calidad (`GET /quality/published`, `GET /quality/admin/overview`, `POST /feedback`). */

export type FeedbackRating = 'up' | 'down';
export type FeedbackReason = 'incorrecta' | 'incompleta' | 'sin_fuentes' | 'mala_traduccion' | 'confusa' | 'otro';

export interface FeedbackPayload {
  request_id: string;
  rating: FeedbackRating;
  reason?: FeedbackReason;
  comment?: string;
  conversation_id?: string;
  language: 'spanish' | 'quechua';
  evidence_status?: 'retrieved' | 'insufficient_evidence';
  translation_quality?: 'alta' | 'media' | 'baja';
  share_text?: boolean;
}

export interface PublishedMetric {
  macro: number | null;
  micro: number | null;
  n: number;
}

export interface PublishedSuite {
  measured: boolean;
  reason?: string;
  answer_source?: string;
  created_at?: string | null;
  note?: string | null;
  n_cases?: number;
  n_scored?: number;
  n_streams?: number;
  metrics?: Record<string, PublishedMetric>;
  systems?: Record<string, Record<string, PublishedMetric>>;
  gold?: { adjudicated?: number; status?: Record<string, number> };
}

export interface PublishedQuality {
  schema: number;
  status: 'preliminar' | 'sin_publicar';
  generated_at?: string;
  sha?: string;
  dirty?: boolean;
  notices: string[];
  suites: Record<string, PublishedSuite>;
}

export interface ComparisonMetric {
  metric: string;
  scope: string;
  base: number | null;
  head: number | null;
  delta: number | null;
  status: string;
}

export interface ComparisonSummary {
  base: { ref: string; sha: string };
  head: { ref: string; sha: string };
  verdict: 'MEJORÓ' | 'IGUAL' | 'EMPEORÓ';
  blocking: boolean;
  comparable: boolean;
  blocks: Array<{ suite: string; kind: string; case_id: string | null; stratum: string | null }>;
  missing: string[];
  suites: Array<{ suite: string; metrics: ComparisonMetric[] }>;
}

export interface FeedbackQueueItem {
  id: string;
  created_at: string;
  reason: FeedbackReason | null;
  comment: string | null;
  language: string;
  query: string;
  answer: string;
  evidence_status: string | null;
  translation_quality: string | null;
}

export interface QualityOverview {
  comparison: ComparisonSummary | null;
  gold: {
    available: boolean;
    pending_lawyers?: number;
    pending_native_speakers?: number;
    legal_qa?: Record<string, number>;
    translation?: Record<string, number>;
  };
  feedback: {
    total: number;
    up: number;
    down: number;
    reasons: Record<string, number>;
    queue: { pending: number; accepted: number; rejected: number };
  };
  feedback_queue: FeedbackQueueItem[];
  stream: {
    n: number;
    outcomes: Record<string, number>;
    ttfb_ms: { n: number; p50: number | null; p95: number | null };
    total_ms: { n: number; p50: number | null; p95: number | null };
    stage_ms: Record<string, { n: number; p50: number | null; p95: number | null }>;
    lines: Record<string, number>;
  };
}
