import type { LegalGateway } from '../../../domain/legal/ports';
import type { PdfDownloadRequest } from '../../../domain/legal/types';

export const createDownloadLegalPdfUseCase = (gateway: LegalGateway) => {
  return async (input: PdfDownloadRequest) => gateway.downloadPdf(input);
};
