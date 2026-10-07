import { test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatInput } from '../../../frontend/src/presentation/components/chat/ChatInput';
const auth = vi.hoisted(() => ({ isAuthenticated: true })); const push = vi.hoisted(() => vi.fn());
vi.mock('../../../frontend/src/presentation/components/AuthProvider', () => ({ useAuth: () => auth }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

test('entrada no envía espacios y Enter recorta texto mientras Shift Enter crea línea', async () => {
  auth.isAuthenticated = true; const send = vi.fn(); const user = userEvent.setup();
  render(<ChatInput language="spanish" isLoading={false} onSend={send} />);
  const input = screen.getByRole('textbox'); await user.type(input, '   {Enter}'); expect(send).not.toHaveBeenCalled();
  await user.clear(input); await user.type(input, 'consulta{Shift>}{Enter}{/Shift}otra'); expect(input).toHaveValue('consulta\notra');
  await user.keyboard('{Enter}'); expect(send).toHaveBeenCalledWith('consulta\notra'); expect(input).toHaveValue('');
});
test('entrada limita 800 caracteres y muestra contador sin truncar silenciosamente', async () => {
  const user = userEvent.setup(); render(<ChatInput language="spanish" isLoading={false} onSend={vi.fn()} />);
  const input = screen.getByRole('textbox'); await user.click(input); await user.paste('a'.repeat(800));
  expect(input).toHaveValue('a'.repeat(800)); expect(screen.getByText('0')).toBeVisible();
  await user.type(input, 'b'); expect(input).toHaveValue('a'.repeat(800));
});
test('entrada no autenticada redirige sin enviar ni perder texto', async () => {
  auth.isAuthenticated = false; const send = vi.fn(); const user = userEvent.setup();
  render(<ChatInput language="spanish" isLoading={false} onSend={send} />);
  await user.type(screen.getByRole('textbox'), 'consulta{Enter}'); expect(push).toHaveBeenCalledWith('/login');
  expect(send).not.toHaveBeenCalled(); expect(screen.getByRole('textbox')).toHaveValue('consulta'); auth.isAuthenticated = true;
});
test('entrada quechua selecciona ejemplo y enfoca sin enviar automáticamente', async () => {
  const send = vi.fn(); const user = userEvent.setup(); render(<ChatInput language="quechua" isLoading={false} onSend={send} />);
  await user.click(screen.getByRole('button', { name: 'Llakichikuyta willay' }));
  expect(screen.getByRole('textbox')).toHaveFocus(); expect(screen.getByRole('textbox')).toHaveValue('¿Imaynatataq llakichikuyta willaqman rini?'); expect(send).not.toHaveBeenCalled();
});
test('entrada en carga bloquea cambios y permite abortar sin limpiar', async () => {
  const abort = vi.fn(); const clear = vi.fn(); const user = userEvent.setup();
  render(<ChatInput language="spanish" isLoading onSend={vi.fn()} onAbort={abort} onClearChat={clear} hasMessages />);
  expect(screen.getByRole('textbox')).toBeDisabled(); await user.click(screen.getByTitle('Detener respuesta'));
  expect(abort).toHaveBeenCalledTimes(1); expect(screen.getByRole('button', { name: 'Limpiar' })).toBeDisabled(); expect(clear).not.toHaveBeenCalled();
});
