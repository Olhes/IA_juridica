import type { ConsultLegalInput, LegalGateway } from '../../domain/legal/ports';
import type { LegalConsultationEnvelope, PdfDownloadRequest } from '../../domain/legal/types';

const parseErrorMessage = (payload: unknown, fallback: string): string => {
  if (typeof payload !== 'object' || payload === null) {
    return fallback;
  }

  const maybeMessage = (payload as { error?: unknown; message?: unknown }).error;
  if (typeof maybeMessage === 'string' && maybeMessage.trim()) {
    return maybeMessage;
  }

  const secondaryMessage = (payload as { message?: unknown }).message;
  if (typeof secondaryMessage === 'string' && secondaryMessage.trim()) {
    return secondaryMessage;
  }

  return fallback;
};

export class HttpLegalGateway implements LegalGateway {
  async consult(input: ConsultLegalInput) {
    const response = await fetch('/api/legal/consult', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(input)
    });

    const payload = (await response.json()) as LegalConsultationEnvelope;

    if (!response.ok || !payload.success || !payload.data) {
      throw new Error(parseErrorMessage(payload, 'No se pudo procesar la consulta legal.'));
    }

    return payload.data;
  }

  async downloadPdf(input: PdfDownloadRequest): Promise<Blob> {
    const response = await fetch('/api/legal/pdf', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(input)
    });

    const contentType = response.headers.get('content-type') || '';
    if (response.ok && contentType.includes('application/pdf')) {
      return response.blob();
    }

    let payload: unknown = null;
    if (contentType.includes('application/json')) {
      payload = await response.json();
    } else {
      payload = { error: await response.text() };
    }

    throw new Error(parseErrorMessage(payload, 'No fue posible generar el PDF.'));
  }
}
