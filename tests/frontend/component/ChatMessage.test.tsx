import { test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatMessage } from '../../../frontend/src/presentation/components/chat/ChatMessage';
import { payload } from '../fixtures/chat';
const message = { id: 'm', role: 'assistant', content: 'Respuesta', timestamp: new Date('2026-10-01') };
test('mensaje de error es visible y no presenta una validación exitosa', () => {
  render(<ChatMessage language="spanish" message={{ ...message, error: 'Fallo sintético' } as any} />);
  expect(screen.getByText('Fallo sintético')).toBeVisible(); expect(screen.queryByText('Validado')).toBeNull();
});
test('mensaje presenta validación advertencias y detalles sin inventar fuentes', async () => {
  const user = userEvent.setup(); render(<ChatMessage language="spanish" message={{ ...message, apiResponse: { ...payload,
    validation: { status: 'warned', confidence: 'medium', confidence_score: .5, hallucination_risk: .3, is_grounded: false },
  } } as any} />);
  expect(screen.getByText('Con advertencias')).toBeVisible();
  await user.click(screen.getByRole('button', { name: /ver pasos/i })); expect(screen.getByText('Documento sintético')).toBeVisible();
});
test('mensaje descarga solo al solicitarlo y bloquea botón durante generación', async () => {
  const download = vi.fn(); const user = userEvent.setup(); const p = { language: 'spanish' as const, message: { ...message, apiResponse: payload } as any, onDownloadPdf: download };
  const { rerender } = render(<ChatMessage {...p} />); await user.click(screen.getByRole('button', { name: /ver pasos/i }));
  await user.click(screen.getByRole('button', { name: /descargar informe/i })); expect(download).toHaveBeenCalledTimes(1);
  rerender(<ChatMessage {...p} isDownloadingPdf />); expect(screen.getByRole('button', { name: /generando pdf/i })).toBeDisabled();
});
