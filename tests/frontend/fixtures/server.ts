import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

export const API = 'http://localhost:8000';
export const server = setupServer(
  http.post(`${API}/session/bootstrap`, () => HttpResponse.json({ principal_id: 'synthetic' })),
  http.get(`${API}/health`, () => HttpResponse.json({ status: 'healthy' })),
);
