import { test, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { ChatPage } from '../../../frontend/src/presentation/pages/ChatPage';
import { server, API } from '../fixtures/server';
import { conversation, payload } from '../fixtures/chat';
vi.mock('../../../frontend/src/presentation/components/SandAnimation', () => ({ SandAnimation: ({ onComplete }: any) => {
  const React = require('react'); React.useEffect(() => onComplete(), []); return null;
} }));
vi.mock('../../../frontend/src/presentation/components/FloatingRadialHub', () => ({ FloatingRadialHub: () => null }));
vi.mock('../../../frontend/src/presentation/components/AuthProvider', () => ({ useAuth: () => ({ isAuthenticated: false }) }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'dark', setTheme: vi.fn() }) }));
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  server.use(http.get(`${API}/chat/conversations`, () => HttpResponse.json({ conversations: [], total_count: 0, active_count: 0 })),
    http.post(`${API}/chat/conversations`, () => HttpResponse.json(conversation())),
    http.get(`${API}/chat/conversations/a`, () => HttpResponse.json({ conversation: conversation(), messages: [], total_messages: 0 })),
    http.put(`${API}/chat/conversations/a`, () => HttpResponse.json(conversation())),
    http.post(`${API}/legal-query-stream`, () => new HttpResponse(JSON.stringify({ type: 'final', data: payload }) + '\n')));
});
test('pantalla principal crea sesión antes de enviar y muestra respuesta final', async () => {
  const user = userEvent.setup(); render(<ChatPage />);
  await user.click(await screen.findByRole('button', { name: 'Comenzar consulta' }));
  await user.type(screen.getByRole('textbox', { name: 'Consulta legal' }), 'sintético{Enter}');
  expect(await within(screen.getByRole('dialog')).findByText(payload.response.respuesta_espanol)).toBeVisible();
  expect(within(screen.getByRole('dialog')).getByText('sintético')).toBeVisible();
});
test('nueva sesión no conserva mensajes del terminal anterior', async () => {
  const user = userEvent.setup(); render(<ChatPage />);
  await user.click(await screen.findByRole('button', { name: 'Comenzar consulta' }));
  await user.type(screen.getByRole('textbox'), 'sintético{Enter}');
  await within(screen.getByRole('dialog')).findByText(payload.response.respuesta_espanol);
  await user.click(screen.getByRole('button', { name: 'Cerrar' }));
  server.use(http.post(`${API}/chat/conversations`, () => HttpResponse.json(conversation('b'))),
    http.get(`${API}/chat/conversations/b`, () => HttpResponse.json({ conversation: conversation('b'), messages: [] })));
  await user.click(screen.getByRole('button', { name: 'Nueva consulta' }));
  await waitFor(() => expect(within(screen.getByRole('dialog')).queryByText('sintético')).toBeNull());
});
test('pantalla recupera historial tras fallo con reintento sin borrar datos', async () => {
  server.use(http.get(`${API}/chat/conversations`, () => new HttpResponse(null, { status: 503 }), { once: true }));
  const user = userEvent.setup(); render(<ChatPage />);
  await user.click(await screen.findByRole('button', { name: 'Reintentar' }));
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
});
