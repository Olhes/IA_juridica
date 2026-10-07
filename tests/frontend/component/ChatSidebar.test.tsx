import { test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatSidebar } from '../../../frontend/src/presentation/components/sidebar/ChatSidebar';
const props = () => ({ sessions: [], activeSessionId: null, language: 'spanish' as const, isOpen: false, loading: false,
  onClose: vi.fn(), onNewSession: vi.fn(), onSelectSession: vi.fn(), onDeleteSession: vi.fn(), onRetry: vi.fn() });
const sessions = [{ id: 'a', title: 'Consulta A', preview: '', language: 'spanish' as const, createdAt: '2026-10-01', updatedAt: '2026-10-01', messageCount: 2 }];
test('sidebar reintento muestra error y respeta bloqueo durante carga', async () => {
  const p = props(); const user = userEvent.setup(); const { rerender } = render(<ChatSidebar {...p} loadError="offline" />);
  await user.click(screen.getByRole('button', { name: /reintentar/i })); expect(p.onRetry).toHaveBeenCalledTimes(1);
  rerender(<ChatSidebar {...p} loadError="offline" loading />); expect(screen.getByRole('button', { name: /reintentando/i })).toBeDisabled();
});
test('sidebar ordenar sesiones no muta datos y selección cierra panel', async () => {
  const p = props(); const list = [...sessions, { ...sessions[0], id: 'b', title: 'Consulta B', updatedAt: '2026-10-02' }];
  const user = userEvent.setup(); render(<ChatSidebar {...p} sessions={list} />);
  const rows = screen.getAllByRole('button').filter(b => b.textContent?.includes('Consulta '));
  expect(rows[0]).toHaveTextContent('Consulta B'); expect(list[0].id).toBe('a'); await user.click(rows[0]);
  expect(p.onSelectSession).toHaveBeenCalledWith('b'); expect(p.onClose).toHaveBeenCalledTimes(1);
});
test('sidebar borrar exige confirmar y cancelar no elimina ni selecciona', async () => {
  const p = props(); const user = userEvent.setup(); render(<ChatSidebar {...p} sessions={sessions} />);
  await user.click(screen.getByRole('button', { name: 'Opciones de Consulta A' }));
  await user.click(screen.getByRole('button', { name: 'Eliminar' })); expect(p.onDeleteSession).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Cancelar' }));
  await user.click(screen.getByRole('button', { name: 'Eliminar' })); await user.click(screen.getByRole('button', { name: 'Eliminar' }));
  expect(p.onDeleteSession).toHaveBeenCalledExactlyOnceWith('a'); expect(p.onSelectSession).not.toHaveBeenCalled();
});
