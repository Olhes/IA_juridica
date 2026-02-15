const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || 'http://127.0.0.1:8000';

interface LegalQueryPayload {
  query: string;
  language: string;
  context?: unknown;
}

interface PdfPayload {
  query: string;
  response: Record<string, unknown>;
}

export const backendConfig = {
  baseUrl: FASTAPI_BASE_URL
};

export async function postLegalQuery(payload: LegalQueryPayload) {
  return fetch(`${FASTAPI_BASE_URL}/legal-query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    cache: 'no-store',
    body: JSON.stringify(payload)
  });
}

export async function postLegalQueryStream(payload: LegalQueryPayload) {
  return fetch(`${FASTAPI_BASE_URL}/legal-query-stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    cache: 'no-store',
    body: JSON.stringify(payload)
  });
}

export async function postPdfReport(payload: PdfPayload) {
  return fetch(`${FASTAPI_BASE_URL}/generate-pdf-report`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    cache: 'no-store',
    body: JSON.stringify(payload)
  });
}

export async function parseUpstreamPayload(response: Response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json() as Promise<Record<string, unknown>>;
  }

  return {
    detail: await response.text()
  };
}
