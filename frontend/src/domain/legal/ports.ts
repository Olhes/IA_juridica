import type {
  LegalConsultationResult,
  LegalQueryContext,
  PdfDownloadRequest,
  SupportedLanguage
} from './types';

export interface ConsultLegalInput {
  query: string;
  language: SupportedLanguage;
  context: LegalQueryContext;
}

export interface LegalGateway {
  consult(input: ConsultLegalInput): Promise<LegalConsultationResult>;
  downloadPdf(input: PdfDownloadRequest): Promise<Blob>;
}
