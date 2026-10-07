import { test, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { ApiService } from '../../../frontend/src/application/legal/services/apiService';
import { server, API } from '../fixtures/server';
import { deferred } from '../fixtures/chat';

test('bootstrap concurrente comparte una solicitud y todas incluyen cookies', async () => {
  let starts = 0;
  const gate = deferred<void>();
  server.use(http.post(`${API}/session/bootstrap`, async ({ request }) => {
    expect(request.credentials).toBe('include'); starts++; await gate.promise;
    return HttpResponse.json({});
  }), http.get(`${API}/chat/conversations`, ({ request }) => {
    expect(request.credentials).toBe('include'); return HttpResponse.json({ conversations: [] });
  }));
  const api = new ApiService();
  const requests = [api.listConversations(), api.listConversations()];
  await new Promise(resolve => setTimeout(resolve, 20));
  gate.resolve();
  expect((await Promise.all(requests)).every(r => r.success)).toBe(true);
  expect(starts).toBe(1);
});
test('bootstrap fallido se puede reintentar sin llamar al endpoint protegido', async () => {
  let starts = 0; let reads = 0;
  server.use(http.post(`${API}/session/bootstrap`, () => ++starts === 1 ?
    new HttpResponse(null, { status: 503 }) : HttpResponse.json({})),
  http.get(`${API}/chat/conversations`, () => { reads++; return HttpResponse.json({ conversations: [] }); }));
  const api = new ApiService();
  expect((await api.listConversations()).success).toBe(false);
  expect(reads).toBe(0);
  expect((await api.listConversations()).success).toBe(true);
  expect(starts).toBe(2);
});
test('API conserva detalle HTTP y tolera respuestas de error no JSON', async () => {
  server.use(http.get(`${API}/chat/conversations`, () => HttpResponse.json({ detail: 'No disponible' }, { status: 503 })));
  const api = new ApiService();
  expect(await api.listConversations()).toEqual({ success: false, error: 'No disponible' });
  server.use(http.get(`${API}/chat/conversations`, () => new HttpResponse('invalid', { status: 401 })));
  expect((await api.listConversations()).error).toBe('HTTP 401');
});
test('API JSON inválido y desconexión no producen un éxito falso', async () => {
  const api = new ApiService();
  server.use(http.get(`${API}/chat/conversations`, () => new HttpResponse('{')));
  expect((await api.listConversations()).success).toBe(false);
  server.use(http.get(`${API}/chat/conversations`, () => HttpResponse.error()));
  expect((await api.listConversations()).success).toBe(false);
});
test('API serializa idioma título y metadatos y codifica búsquedas', async () => {
  const api = new ApiService();
  server.use(http.post(`${API}/chat/conversations`, async ({ request }) => {
    expect(await request.json()).toEqual({ language: 'quechua', title: 'Título' }); return HttpResponse.json({ id: 'a' });
  }), http.put(`${API}/chat/conversations/a`, async ({ request }) => {
    expect(await request.json()).toEqual({ metadata: { preview: 'á' } }); return HttpResponse.json({ id: 'a' });
  }), http.get(`${API}/chat/search`, ({ request }) => {
    expect(new URL(request.url).searchParams.get('q')).toBe('a & ñ'); return HttpResponse.json({ results: [] });
  }));
  expect((await api.createConversation('quechua', 'Título')).success).toBe(true);
  expect((await api.updateConversation('a', { metadata: { preview: 'á' } })).success).toBe(true);
  expect((await api.searchConversations('a & ñ')).success).toBe(true);
});
