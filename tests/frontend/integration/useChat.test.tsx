import { test, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useChat } from '../../../frontend/src/application/legal/use-cases/useChat';
import { apiService } from '../../../frontend/src/application/legal/services/apiService';
import { conversation, deferred, payload, streamResponse } from '../fixtures/chat';

beforeEach(() => vi.spyOn(apiService, 'getConversation').mockImplementation(async id => ({
  success: true, data: { conversation: conversation(id), messages: [], total_messages: 0 },
})));
async function hook(language: 'spanish' | 'quechua' = 'spanish') {
  const updated = vi.fn();
  const rendered = renderHook(({ id }) => useChat({ sessionId: id, language, onSessionUpdated: updated }), { initialProps: { id: 'a' as string | null } });
  await act(async () => {});
  return { ...rendered, updated };
}
test('NDJSON fragmentado por byte conserva Unicode y usa respuesta final española', async () => {
  const { result, updated } = await hook();
  vi.stubGlobal('fetch', vi.fn(async () => streamResponse(
    JSON.stringify({ type: 'chunk', delta: 'ñ 🦙 parcial' }) + '\n' + JSON.stringify({ type: 'final', data: payload }))));
  await act(async () => { await result.current.sendQuery('  consulta  '); });
  expect(result.current.messages.map(m => m.content)).toEqual(['consulta', payload.response.respuesta_espanol]);
  expect(result.current.messages[1].apiResponse).toEqual(payload);
  expect(result.current.isLoading).toBe(false);
  expect(updated).toHaveBeenCalledWith({ title: 'consulta' });
  expect(updated).toHaveBeenCalledWith({ messageCount: 2 });
});
test('final quechua selecciona idioma y transmite conversation_id con cookies', async () => {
  const { result } = await hook('quechua');
  const fetch = vi.fn(async () => streamResponse(JSON.stringify({ type: 'final', data: payload }) + '\n', 9999));
  vi.stubGlobal('fetch', fetch);
  await act(async () => { await result.current.sendQuery('tapukuy'); });
  expect(result.current.messages[1].content).toBe(payload.response.respuesta_quechua);
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ query: 'tapukuy', language: 'quechua', conversation_id: 'a' });
  expect(fetch.mock.calls[0][1].credentials).toBe('include');
});
test('stream sin final vacíos y varios eventos conserva texto parcial', async () => {
  const { result } = await hook();
  vi.stubGlobal('fetch', vi.fn(async () => streamResponse('\n{"type":"chunk","delta":"á"}\n{"type":"chunk","delta":""}\n{"type":"chunk","delta":"🦙"}', 9999)));
  await act(async () => { await result.current.sendQuery('q'); });
  expect(result.current.messages[1].content).toBe('á🦙');
  expect(result.current.messages[1].isStreaming).toBe(false);
});
test('evento de error y JSON malformado terminan carga sin éxito falso', async () => {
  for (const text of ['{"type":"error","error":"Fallo sintético"}\n', '{broken}\n']) {
    const { result, unmount } = await hook();
    vi.stubGlobal('fetch', vi.fn(async () => streamResponse(text)));
    await act(async () => { await result.current.sendQuery('q'); });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.messages[1].apiResponse).toBeUndefined();
    expect(result.current.messages[1].content).toMatch(/no se pudo/i);
    unmount();
  }
});
test('HTTP no exitoso y cuerpo ausente terminan con error recuperable', async () => {
  for (const response of [new Response(null, { status: 503 }), new Response(null)]) {
    const { result, unmount } = await hook();
    vi.stubGlobal('fetch', vi.fn(async () => response));
    await act(async () => { await result.current.sendQuery('q'); });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.messages[1].content).toMatch(/no se pudo/i);
    unmount();
  }
});
test('envíos vacíos sin sesión y simultáneos no duplican solicitudes', async () => {
  const { result, rerender } = await hook();
  const fetch = vi.fn(async () => streamResponse('{"type":"chunk","delta":"ok"}\n'));
  vi.stubGlobal('fetch', fetch);
  await act(async () => { await result.current.sendQuery('   '); });
  rerender({ id: null }); await act(async () => { await result.current.sendQuery('q'); });
  expect(fetch).not.toHaveBeenCalled();
  rerender({ id: 'a' }); await act(async () => {});
  await act(async () => { await Promise.all([result.current.sendQuery('q'), result.current.sendQuery('q')]); });
  expect(fetch).toHaveBeenCalledTimes(1);
});
test('abort conserva respuesta parcial y libera bloqueo de envío', async () => {
  const { result } = await hook();
  let stream!: ReadableStreamDefaultController;
  vi.stubGlobal('fetch', vi.fn(async (_url, options) => new Response(new ReadableStream({
    start(controller) {
      stream = controller;
      controller.enqueue(new TextEncoder().encode('{"type":"chunk","delta":"parcial"}\n'));
      options.signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')));
    },
  }))));
  let pending!: Promise<void>;
  act(() => { pending = result.current.sendQuery('q'); });
  await waitFor(() => expect(result.current.messages[1].streamingContent).toBe('parcial'));
  await act(async () => { result.current.abort(); await pending; });
  expect(result.current.messages[1].content).toBe('parcial'); expect(result.current.isLoading).toBe(false);
});
test('carga antigua no reemplaza mensajes de la sesión nueva', async () => {
  const late = deferred<any>();
  vi.spyOn(apiService, 'getConversation').mockImplementation(id => id === 'a' ? late.promise : Promise.resolve({
    success: true, data: { conversation: conversation(id), messages: [{ id: 'b-msg', role: 'user', content: 'solo B', created_at: '2026-10-01' }], total_messages: 1 },
  } as any));
  const rendered = await hook(); rendered.rerender({ id: 'b' });
  await waitFor(() => expect(rendered.result.current.messages[0]?.content).toBe('solo B'));
  await act(async () => late.resolve({ success: true, data: { messages: [{ id: 'a-msg', content: 'solo A' }] } }));
  expect(rendered.result.current.messages[0]?.content).toBe('solo B');
});
test('cambio de sesión cancela stream y no actualiza metadatos antiguos', async () => {
  const { result, rerender, updated } = await hook();
  const late = deferred<Response>(); let signal!: AbortSignal;
  vi.stubGlobal('fetch', vi.fn((_url, options) => { signal = options.signal; return late.promise; }));
  let pending!: Promise<void>; act(() => { pending = result.current.sendQuery('q'); });
  rerender({ id: 'b' }); await act(async () => {});
  expect(signal.aborted).toBe(true); updated.mockClear();
  await act(async () => { late.resolve(streamResponse(JSON.stringify({ type: 'final', data: payload }))); await pending; });
  expect(result.current.messages).toEqual([]); expect(updated).not.toHaveBeenCalled();
});
test('desmontaje cancela stream sin notificar metadatos tardíos', async () => {
  const { result, unmount, updated } = await hook(); const late = deferred<Response>(); let signal!: AbortSignal;
  vi.stubGlobal('fetch', vi.fn((_url, options) => { signal = options.signal; return late.promise; }));
  let pending!: Promise<void>; act(() => { pending = result.current.sendQuery('q'); });
  unmount(); expect(signal.aborted).toBe(true); updated.mockClear();
  late.resolve(streamResponse(JSON.stringify({ type: 'final', data: payload }))); await pending;
  expect(updated).not.toHaveBeenCalled();
});
test('limpiar aborta y una carga tardía no repuebla la conversación', async () => {
  const late = deferred<any>(); vi.spyOn(apiService, 'getConversation').mockReturnValue(late.promise);
  const { result } = await hook();
  act(() => result.current.clearChat());
  await act(async () => late.resolve({ success: true, data: { messages: [{ id: 'late', content: 'antiguo' }] } }));
  expect(result.current.messages).toEqual([]);
});
test('health distingue saludable degradado y fallo de red', async () => {
  const { result } = await hook();
  for (const [status, expected] of [['healthy', true], ['degraded', false]] as const) {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ status })));
    await act(async () => { await result.current.checkHealth(); }); expect(result.current.isOnline).toBe(expected);
  }
  vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline'); }));
  await act(async () => { await result.current.checkHealth(); }); expect(result.current.isOnline).toBe(false);
});
test('PDF válido descarga blob y revoca URL incluso si click falla', async () => {
  const { result } = await hook(); const create = vi.fn(() => 'blob:synthetic'); const revoke = vi.fn();
  URL.createObjectURL = create; URL.revokeObjectURL = revoke;
  vi.stubGlobal('fetch', vi.fn(async () => new Response('pdf', { headers: { 'content-type': 'application/pdf' } })));
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => { throw new Error('no download'); });
  await act(async () => { await result.current.downloadPdf({ id: 'm', apiResponse: payload } as any); });
  expect(create).toHaveBeenCalledTimes(1); expect(revoke).toHaveBeenCalledWith('blob:synthetic');
  expect(result.current.downloadingPdfId).toBeNull();
});
test('PDF ausente MIME inválido y fallo de red no descargan ni dejan carga', async () => {
  const { result } = await hook(); URL.createObjectURL = vi.fn();
  const fetch = vi.fn(async () => Response.json({ error: true })); vi.stubGlobal('fetch', fetch);
  await act(async () => { await result.current.downloadPdf({ id: 'm' } as any); }); expect(fetch).not.toHaveBeenCalled();
  await act(async () => { await result.current.downloadPdf({ id: 'm', apiResponse: payload } as any); });
  expect(URL.createObjectURL).not.toHaveBeenCalled(); expect(result.current.downloadingPdfId).toBeNull();
  fetch.mockRejectedValueOnce(new Error('offline'));
  await act(async () => { await result.current.downloadPdf({ id: 'm', apiResponse: payload } as any); });
  expect(URL.createObjectURL).not.toHaveBeenCalled(); expect(result.current.downloadingPdfId).toBeNull();
});
test('contrato v1: etapas en vivo, texto validado y tiempos en el payload final', async () => {
  const { result } = await hook();
  const v1 = (seq: number, event: object) => JSON.stringify({ v: 1, seq, request_id: 'r', ...event }) + '\n';
  const gate = deferred<void>();
  vi.stubGlobal('fetch', vi.fn(async () => new Response(new ReadableStream({
    async start(controller) {
      const send = (text: string) => controller.enqueue(new TextEncoder().encode(text));
      send(v1(0, { type: 'meta', data: {} }) + v1(1, { type: 'stage', stage: 'retrieval', status: 'start' }));
      await gate.promise;
      send(v1(2, { type: 'stage', stage: 'retrieval', status: 'end', elapsed_ms: 5 })
        + v1(3, { type: 'final', data: { ...payload, metadata: { timings: { total_ms: 5, stages: { retrieval: 5 }, cache_hit: false } } } })
        + v1(4, { type: 'done' }));
      controller.close();
    },
  }))));
  let pending!: Promise<void>;
  act(() => { pending = result.current.sendQuery('q'); });
  await waitFor(() => expect(result.current.messages[1].stage).toBe('retrieval'));
  gate.resolve();
  await act(async () => { await pending; });
  expect(result.current.messages[1].stage).toBeUndefined();
  expect(result.current.messages[1].content).toBe(payload.response.respuesta_espanol);
  expect(result.current.messages[1].apiResponse?.metadata.timings?.stages.retrieval).toBe(5);
});
test('contrato v1: error con code se conserva y reintentar reenvía la misma consulta', async () => {
  const { result } = await hook();
  const error = JSON.stringify({ v: 1, seq: 1, request_id: 'r', type: 'error', code: 'TIMEOUT', message: 'x', retryable: true }) + '\n'
    + JSON.stringify({ v: 1, seq: 2, request_id: 'r', type: 'done' }) + '\n';
  const fetch = vi.fn(async () => streamResponse(error));
  vi.stubGlobal('fetch', fetch);
  await act(async () => { await result.current.sendQuery('consulta'); });
  expect(result.current.messages[1].errorInfo).toEqual({ code: 'TIMEOUT', retryable: true });
  expect(result.current.messages[1].isStreaming).toBe(false);
  vi.stubGlobal('fetch', vi.fn(async () => streamResponse(JSON.stringify({ type: 'final', data: payload }) + '\n')));
  await act(async () => { result.current.retry(result.current.messages[1].id); });
  await waitFor(() => expect(result.current.messages.map(m => m.content)).toEqual(['consulta', payload.response.respuesta_espanol]));
  expect(result.current.messages[1].errorInfo).toBeUndefined();
});
