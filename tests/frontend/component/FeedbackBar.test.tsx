import { test, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FeedbackBar } from '../../../frontend/src/presentation/components/chat/FeedbackBar';
import { TerminalModal } from '../../../frontend/src/presentation/components/TerminalModal';
import { payload } from '../fixtures/chat';

const REQUEST_ID = '0123456789abcdef0123456789abcdef';
const setup = (language: 'spanish' | 'quechua' = 'spanish', result = { ok: true, queued: false }) => {
  const onSubmit = vi.fn(async () => result);
  render(<FeedbackBar language={language} requestId={REQUEST_ID} context={{ evidence_status: 'retrieved', translation_quality: 'media' }} onSubmit={onSubmit} />);
  return { onSubmit, user: userEvent.setup() };
};

test('un pulgar arriba se envía de inmediato con el contexto numérico y sin motivo', async () => {
  const { onSubmit, user } = setup();
  await user.click(screen.getByRole('button', { name: 'Útil' }));
  expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ rating: 'up', evidence_status: 'retrieved', translation_quality: 'media' });
  expect(await screen.findByRole('status')).toHaveTextContent('Gracias por tu opinión.');
});

test('un pulgar abajo exige un motivo y por defecto no comparte el texto de la consulta', async () => {
  const { onSubmit, user } = setup();
  await user.click(screen.getByRole('button', { name: 'No útil' }));
  const send = screen.getByRole('button', { name: 'Enviar' });
  expect(send).toBeDisabled();
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  await user.click(screen.getByLabelText('No cita fuentes'));
  await user.type(screen.getByLabelText(/Cuéntanos más/), '  falta el artículo  ');
  await user.click(send);
  expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
    rating: 'down', reason: 'sin_fuentes', comment: 'falta el artículo', share_text: false,
    evidence_status: 'retrieved', translation_quality: 'media',
  });
});

test('compartir el texto es una casilla explícita y la cola de revisión se avisa', async () => {
  const { onSubmit, user } = setup('spanish', { ok: true, queued: true });
  await user.click(screen.getByRole('button', { name: 'No útil' }));
  await user.click(screen.getByLabelText('Es incorrecta'));
  await user.click(screen.getByRole('checkbox', { name: /Permito que el equipo revise/ }));
  await user.click(screen.getByRole('button', { name: 'Enviar' }));
  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ share_text: true, reason: 'incorrecta' }));
  expect(await screen.findByRole('status')).toHaveTextContent('cola de revisión');
});

test('si el envío falla se explica y se puede reintentar sin perder lo escrito', async () => {
  const { onSubmit, user } = setup('spanish', { ok: false, queued: false });
  await user.click(screen.getByRole('button', { name: 'No útil' }));
  await user.click(screen.getByLabelText('Es confusa'));
  await user.type(screen.getByLabelText(/Cuéntanos más/), 'no entiendo');
  await user.click(screen.getByRole('button', { name: 'Enviar' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos enviar tu opinión');
  expect(screen.getByLabelText(/Cuéntanos más/)).toHaveValue('no entiendo');
  await user.click(screen.getByRole('button', { name: 'Enviar' }));
  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
});

test('cancelar cierra el formulario y la barra existe en quechua', async () => {
  const { user } = setup('quechua');
  await user.click(screen.getByRole('button', { name: 'Mana yanapaq' }));
  expect(screen.getByText('¿Imataq pantarqan?')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Ama' }));
  expect(screen.queryByText('¿Imataq pantarqan?')).toBeNull();
  expect(screen.getByRole('button', { name: 'Yanapaq' })).toBeVisible();
});

test('la terminal muestra la opinión solo con respuesta final, request_id y manejador', () => {
  const messages = [
    { id: 'a', content: 'Respuesta', isUser: false, apiResponse: payload as never, requestId: REQUEST_ID },
    { id: 'b', content: 'Sin id', isUser: false, apiResponse: payload as never },
    { id: 'c', content: 'En curso', isUser: false, isStreaming: true, apiResponse: payload as never, requestId: REQUEST_ID },
  ];
  const onFeedback = vi.fn(async () => ({ ok: true, queued: false }));
  const { rerender } = render(<TerminalModal isOpen onSend={() => {}} onClose={() => {}} messages={messages} onFeedback={onFeedback} />);
  expect(screen.getAllByRole('button', { name: 'Útil' })).toHaveLength(1);
  rerender(<TerminalModal isOpen onSend={() => {}} onClose={() => {}} messages={messages} />);
  expect(screen.queryByRole('button', { name: 'Útil' })).toBeNull();
});
