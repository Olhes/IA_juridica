export type SupportedLanguage = 'spanish' | 'quechua';

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
