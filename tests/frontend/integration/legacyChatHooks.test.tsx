import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { useBackendChat } from '../../../frontend/src/application/legal/use-cases/useBackendChat';
import { usePersistentChat } from '../../../frontend/src/application/legal/use-cases/usePersistentChat';

const api = vi.hoisted(() => ({
  sendChatMessage: vi.fn(), createConversation: vi.fn(), getConversation: vi.fn(),
  continueConversation: vi.fn(), listConversations: vi.fn(), chatHealthCheck: vi.fn(),
}));
vi.mock('../../../frontend/src/application/legal/services/apiService', () => ({ apiService: api }));
const conversation = { id: 'c1', title: 'Sintética', language: 'spanish' };
const message = { id: 'm1', role: 'assistant', content: 'Respuesta sintética', created_at: '2026-10-06T12:00:00Z', metadata: { validation_status: 'passed' } };
beforeEach(() => {
  vi.resetAllMocks();
  api.chatHealthCheck.mockResolvedValue({ success: true, data: { status: 'healthy' } });
  api.getConversation.mockResolvedValue({ success: true, data: { conversation, messages: [message] } });
  api.createConversation.mockResolvedValue({ success: true, data: conversation });
  api.sendChatMessage.mockResolvedValue({ success: true, data: { conversation_id: 'c1', message, conversation_history: [message] } });
});

test('backend chat conserva historial fecha e identidad de conversación entre envíos', async () => {
  const { result } = renderHook(() => useBackendChat({ language: 'quechua' }));
  await waitFor(() => expect(result.current.isOnline).toBe(true));
  await act(async () => { expect(await result.current.sendMessage('  prueba  ')).toMatchObject({ conversationId: 'c1' }); });
  expect(api.sendChatMessage).toHaveBeenCalledWith('prueba', undefined, 'quechua');
  expect(result.current.messages[0]).toMatchObject({ content: message.content, timestamp: new Date(message.created_at), isStreaming: false });
  await act(async () => { await result.current.sendMessage('otra'); });
  expect(api.sendChatMessage).toHaveBeenLastCalledWith('otra', 'c1', 'quechua');
  api.sendChatMessage.mockResolvedValue({ success: true, data: { conversation_id: 'c1', message } });
  await act(async () => { await result.current.sendMessage('sin historial'); });
  expect(result.current.messages).toHaveLength(1);
  await act(async () => { await result.current.loadConversation('c1'); });
  expect(result.current.messages[0]).toMatchObject({ id: message.id, content: message.content });
  await act(async () => { await result.current.createConversation('Nuevo'); });
  expect(api.createConversation).toHaveBeenCalledWith('quechua', 'Nuevo');
  expect(result.current.messages).toEqual([]);
  act(() => result.current.resetChat());
  expect(result.current.conversationId).toBeNull();
});

test.each(['sendMessage', 'loadConversation', 'createConversation'] as const)('backend chat %s maneja fallo API y excepciones sin dejar loading', async method => {
  const { result } = renderHook(() => useBackendChat({ language: 'spanish' }));
  const service = method === 'sendMessage' ? api.sendChatMessage : method === 'loadConversation' ? api.getConversation : api.createConversation;
  for (const error of ['api', 'exception', 'unknown']) {
    if (error === 'api') service.mockResolvedValue({ success: false });
    else service.mockRejectedValue(error === 'exception' ? new Error('Fallo sintético') : 'sintético');
    await act(async () => { await result.current[method]('prueba'); });
    expect(result.current.error).toBeTruthy();
    expect(result.current.isLoading).toBe(false);
    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();
  }
});

test('backend chat rechaza entradas vacías y solapadas y limpia sondeo al desmontar', async () => {
  const clear = vi.spyOn(globalThis, 'clearInterval');
  const { result, unmount } = renderHook(() => useBackendChat({ language: 'spanish' }));
  await act(async () => { await result.current.sendMessage('  '); });
  expect(api.sendChatMessage).not.toHaveBeenCalled();
  let resolve!: (value: unknown) => void;
  api.sendChatMessage.mockImplementation(() => new Promise(done => { resolve = done; }));
  let pending!: Promise<unknown>;
  act(() => { pending = result.current.sendMessage('primera') as Promise<unknown>; });
  await act(async () => { await result.current.sendMessage('segunda'); });
  expect(api.sendChatMessage).toHaveBeenCalledTimes(1);
  await act(async () => { resolve({ success: false, error: 'busy' }); await pending; });
  unmount();
  expect(clear).toHaveBeenCalled();
});

test('backend chat listado y salud reportan fallo sin inventar datos', async () => {
  const { result } = renderHook(() => useBackendChat({ language: 'spanish' }));
  api.listConversations.mockResolvedValue({ success: true, data: [conversation] });
  await act(async () => { expect(await result.current.listConversations()).toEqual([conversation]); });
  api.listConversations.mockResolvedValue({ success: false });
  await act(async () => { expect(await result.current.listConversations()).toBeNull(); });
  vi.spyOn(console, 'error').mockImplementation(() => {});
  api.listConversations.mockRejectedValue(new Error('offline'));
  await act(async () => { expect(await result.current.listConversations()).toBeNull(); });
  api.chatHealthCheck.mockResolvedValue({ success: true, data: { status: 'unhealthy' } });
  await act(async () => { await result.current.checkHealth(); });
  expect(result.current.isOnline).toBe(false);
  api.chatHealthCheck.mockRejectedValue(new Error('offline'));
  await act(async () => { await result.current.checkHealth(); });
  expect(result.current.isOnline).toBe(false);
});

test('chat persistente carga envía continúa y crea con notificación y metadatos', async () => {
  const updated = vi.fn();
  const { result } = renderHook(() => usePersistentChat({ conversationId: 'c1', language: 'spanish', onConversationUpdated: updated }));
  await waitFor(() => expect(result.current.messages).toHaveLength(1));
  expect(updated).toHaveBeenCalledWith(conversation);
  expect(result.current.messages[0].timestamp).toEqual(new Date(message.created_at));
  await act(async () => { expect(await result.current.sendMessage(' prueba ')).toMatchObject({ success: true, conversationId: 'c1' }); });
  expect(api.sendChatMessage).toHaveBeenCalledWith('prueba', 'c1', 'spanish');
  api.continueConversation.mockResolvedValue({ success: true });
  await act(async () => { await result.current.continueConversation('seguir'); });
  expect(api.continueConversation).toHaveBeenCalledWith('c1', 'seguir');
  expect(api.getConversation).toHaveBeenCalledTimes(2);
  await act(async () => { expect(await result.current.createNewConversation('Nueva')).toEqual(conversation); });
  expect(result.current.messages).toEqual([]);
  expect(result.current.conversation).toEqual(conversation);
  act(() => result.current.resetChat());
  expect(result.current.conversation).toBeNull();
});

test.each(['sendMessage', 'loadConversation', 'createNewConversation', 'continueConversation'] as const)('chat persistente %s propaga errores controlados y recupera estado', async method => {
  const { result } = renderHook(() => usePersistentChat({ conversationId: 'c1', language: 'spanish' }));
  await waitFor(() => expect(result.current.messages).toHaveLength(1));
  const service = method === 'sendMessage' ? api.sendChatMessage : method === 'loadConversation' ? api.getConversation : method === 'createNewConversation' ? api.createConversation : api.continueConversation;
  for (const error of ['api', 'exception', 'unknown']) {
    if (error === 'api') service.mockResolvedValue({ success: false });
    else service.mockRejectedValue(error === 'exception' ? new Error('Fallo sintético') : 'sintético');
    await act(async () => { await result.current[method]('prueba'); });
    expect(result.current.error).toBeTruthy();
    expect(result.current.isLoading).toBe(false);
    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();
  }
});

test('chat persistente sin id omite continuación y tolera historial metadatos y fechas ausentes', async () => {
  const { result, unmount } = renderHook(() => usePersistentChat({ language: 'quechua' }));
  await act(async () => { await result.current.continueConversation('seguir'); await result.current.sendMessage(' '); });
  expect(api.continueConversation).not.toHaveBeenCalled();
  expect(api.sendChatMessage).not.toHaveBeenCalled();
  api.sendChatMessage.mockResolvedValue({ success: true, data: { message, conversation_history: [{ id: 'm2', role: 'user', content: 'Hola' }] } });
  await act(async () => { await result.current.sendMessage('prueba'); });
  expect(result.current.messages[0]).toMatchObject({ metadata: {}, timestamp: expect.any(Date) });
  api.sendChatMessage.mockResolvedValue({ success: true, data: { message } });
  await act(async () => { await result.current.sendMessage('otra'); });
  expect(result.current.messages).toEqual([]);
  api.chatHealthCheck.mockRejectedValue(new Error('offline'));
  await act(async () => { await result.current.checkHealth(); });
  expect(result.current.isOnline).toBe(false);
  unmount();
});
