import { test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HistoryPanel } from '../../../frontend/src/presentation/components/HistoryPanel';
const sessions = [{ id: 'a', title: 'Consulta A', preview: 'Sintético', timestamp: new Date('2026-10-01') }];
test('historial cerrado no aparece y lista vacía tiene mensaje', () => {
  const props = { sessions: [], onClose: vi.fn(), onSelectSession: vi.fn(), onDeleteSession: vi.fn() };
  const { rerender } = render(<HistoryPanel {...props} isOpen={false} />); expect(screen.queryByText('Historial')).toBeNull();
  rerender(<HistoryPanel {...props} isOpen />); expect(screen.getByText('No hay sesiones recientes')).toBeVisible();
});
test('historial selecciona por teclado y borrar no selecciona accidentalmente', async () => {
  const select = vi.fn(); const remove = vi.fn(); const user = userEvent.setup();
  render(<HistoryPanel isOpen sessions={sessions} onClose={vi.fn()} onSelectSession={select} onDeleteSession={remove} />);
  screen.getByRole('button', { name: /seleccionar consulta a/i }).focus(); await user.keyboard('{Enter}');
  expect(select).toHaveBeenCalledExactlyOnceWith('a'); select.mockClear();
  await user.click(screen.getByRole('button', { name: /eliminar consulta a/i })); expect(remove).toHaveBeenCalledWith('a'); expect(select).not.toHaveBeenCalled();
});
test('historial permite cerrar con botón y Escape', async () => {
  const close = vi.fn(); const user = userEvent.setup();
  render(<HistoryPanel isOpen sessions={sessions} onClose={close} onSelectSession={vi.fn()} onDeleteSession={vi.fn()} />);
  await user.keyboard('{Escape}'); await user.click(screen.getByRole('button', { name: 'Cerrar historial' })); expect(close).toHaveBeenCalledTimes(2);
});
