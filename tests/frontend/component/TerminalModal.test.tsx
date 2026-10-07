import { test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TerminalModal } from '../../../frontend/src/presentation/components/TerminalModal';

test('terminal cerrado no renderiza y abierto enfoca la entrada', () => {
  const props = { onSend: vi.fn(), onClose: vi.fn(), messages: [] };
  const { rerender } = render(<TerminalModal {...props} isOpen={false} />);
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  rerender(<TerminalModal {...props} isOpen />); expect(screen.getByRole('textbox')).toHaveFocus();
});
test('terminal envía texto recortado por Enter y no envía espacios', async () => {
  const onSend = vi.fn(); const user = userEvent.setup();
  render(<TerminalModal isOpen onSend={onSend} onClose={vi.fn()} messages={[]} />);
  await user.type(screen.getByRole('textbox'), '   {Enter}'); expect(onSend).not.toHaveBeenCalled();
  await user.clear(screen.getByRole('textbox')); await user.type(screen.getByRole('textbox'), ' consulta {Enter}');
  expect(onSend).toHaveBeenCalledExactlyOnceWith('consulta'); expect(screen.getByRole('textbox')).toHaveValue('');
});
test('terminal cargando bloquea envío y representa mensajes y estado', () => {
  render(<TerminalModal isOpen isLoading onSend={vi.fn()} onClose={vi.fn()} messages={[{ id: 'a', content: 'Texto seguro <script>', isUser: true }]} />);
  expect(screen.getByRole('textbox')).toBeDisabled(); expect(screen.getByText('Texto seguro <script>')).toBeVisible();
  expect(screen.getByText(/procesando respuesta/i)).toBeVisible(); expect(document.querySelector('script')).toBeNull();
});
test('terminal Escape y cerrar notifican cierre y devuelven foco', async () => {
  const close = vi.fn(); const user = userEvent.setup();
  const { rerender } = render(<><button autoFocus>Abrir</button><TerminalModal isOpen onSend={vi.fn()} onClose={close} messages={[]} /></>);
  await user.keyboard('{Escape}'); expect(close).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole('button', { name: 'Cerrar' })); expect(close).toHaveBeenCalledTimes(2);
  rerender(<><button>Abrir</button><TerminalModal isOpen={false} onSend={vi.fn()} onClose={close} messages={[]} /></>);
  expect(screen.getByRole('button', { name: 'Abrir' })).toHaveFocus();
});
