import { test, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useChatSessions } from '../../../frontend/src/application/legal/use-cases/useChatSessions';
import { apiService } from '../../../frontend/src/application/legal/services/apiService';
import { conversation, deferred } from '../fixtures/chat';
beforeEach(() => {
  vi.spyOn(apiService, 'initializeSession').mockResolvedValue();
  vi.spyOn(apiService, 'listConversations').mockResolvedValue({ success: true, data: {
    conversations: [conversation('a', 'Existente', 2)], total_count: 1, active_count: 1,
  } });
});
async function hook() {
  const rendered = renderHook(useChatSessions);
  await waitFor(() => expect(rendered.result.current.hydrated).toBe(true)); return rendered;
}
test('montaje carga historial sin borrar ni seleccionar una sesión automáticamente', async () => {
  const { result } = await hook(); expect(result.current.sessions[0].id).toBe('a');
  expect(result.current.activeSessionId).toBeNull(); expect(result.current.loading).toBe(false);
});
test('creación reutiliza consulta vacía y respeta idioma de una nueva', async () => {
  const create = vi.spyOn(apiService, 'createConversation').mockResolvedValue({ success: true, data: conversation('new') });
  const { result } = await hook();
  await act(async () => { expect(await result.current.createSession('quechua')).toBe('new'); });
  expect(create).toHaveBeenCalledWith('quechua', 'Nueva consulta');
  await act(async () => { expect(await result.current.createSession()).toBe('new'); }); expect(create).toHaveBeenCalledTimes(1);
});
test('creación fallida no añade una sesión fantasma', async () => {
  vi.spyOn(apiService, 'createConversation').mockResolvedValue({ success: false, error: 'offline' });
  const { result } = await hook();
  await act(async () => { await expect(result.current.createSession()).rejects.toThrow(); });
  expect(result.current.sessions).toHaveLength(1); expect(result.current.activeSessionId).toBeNull();
});
test('reload fallido conserva historial y reintento recupera la lista', async () => {
  const { result } = await hook();
  vi.mocked(apiService.listConversations).mockResolvedValueOnce({ success: false, error: 'offline' });
  await act(async () => { await result.current.reloadSessions(); });
  expect(result.current.sessions).toHaveLength(1); expect(result.current.sessionsLoadError).toBe('offline');
  await act(async () => { await result.current.reloadSessions(); }); expect(result.current.sessionsLoadError).toBeNull();
});
test('bootstrap fallido muestra error y no solicita historial', async () => {
  vi.mocked(apiService.initializeSession).mockRejectedValue(new Error('offline'));
  const { result } = await hook(); expect(result.current.sessionsLoadError).toMatch(/sesión anónima/);
  expect(apiService.listConversations).not.toHaveBeenCalled();
});
test('borrado fallido conserva sesión activa y borrado exitoso la elimina', async () => {
  const remove = vi.spyOn(apiService, 'deleteConversation').mockResolvedValueOnce({ success: false, error: 'offline' })
    .mockResolvedValue({ success: true, data: { success: true, message: 'ok' } });
  const { result } = await hook(); act(() => result.current.setActiveSessionId('a'));
  await act(async () => { await expect(result.current.deleteSession('a')).rejects.toThrow('offline'); });
  expect(result.current.sessions).toHaveLength(1); expect(result.current.activeSessionId).toBe('a');
  await act(async () => { await result.current.deleteSession('a'); });
  expect(result.current.sessions).toEqual([]); expect(result.current.activeSessionId).toBeNull(); expect(remove).toHaveBeenCalledTimes(2);
});
test('metadatos locales y payload backend conservan preview conteo y título', async () => {
  const update = vi.spyOn(apiService, 'updateConversation').mockResolvedValue({ success: true, data: conversation() });
  const { result } = await hook();
  await act(async () => { await result.current.updateSessionMeta('a', { title: 'Nuevo', preview: 'á', messageCount: 4 }); });
  expect(result.current.sessions[0]).toMatchObject({ title: 'Nuevo', preview: 'á', messageCount: 4 });
  expect(update).toHaveBeenCalledWith('a', { title: 'Nuevo', metadata: { preview: 'á', messageCount: 4 } });
});
test('reload antiguo no reemplaza una respuesta nueva', async () => {
  const { result } = await hook(); const late = deferred<any>();
  vi.mocked(apiService.listConversations).mockReturnValueOnce(late.promise)
    .mockResolvedValueOnce({ success: true, data: { conversations: [conversation('b')], total_count: 1, active_count: 1 } });
  let first!: Promise<void>; act(() => { first = result.current.reloadSessions(); });
  await waitFor(() => expect(apiService.listConversations).toHaveBeenCalledTimes(2));
  await act(async () => { await result.current.reloadSessions(); });
  await act(async () => { late.resolve({ success: true, data: { conversations: [conversation('old')] } }); await first; });
  expect(result.current.sessions[0].id).toBe('b');
});
