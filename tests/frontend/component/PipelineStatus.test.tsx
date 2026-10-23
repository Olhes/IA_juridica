import { test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  ResponseTiming,
  StageProgress,
  StreamErrorCard,
} from '../../../frontend/src/presentation/components/chat/PipelineStatus';
import { TerminalModal } from '../../../frontend/src/presentation/components/TerminalModal';

test('etapas en vivo marcan la activa y las terminadas, en español y quechua', () => {
  const { rerender } = render(
    <StageProgress language="spanish" stage="generation" completed={['retrieval']} />,
  );
  expect(screen.getByText('Buscando en el corpus')).toBeVisible();
  expect(screen.getByText('Redactando').closest('li')).toHaveAttribute('aria-current', 'step');
  expect(screen.queryByText('Traduciendo')).toBeNull();
  rerender(<StageProgress language="quechua" stage="translate_out" completed={['retrieval', 'generation', 'validation']} />);
  expect(screen.getByText('Runasimiman tikrashan').closest('li')).toHaveAttribute('aria-current', 'step');
});

test('la traducción de entrada y salida se muestra como un único paso', () => {
  render(<StageProgress language="spanish" stage="retrieval" completed={['translate_in']} />);
  expect(screen.getAllByText('Traduciendo')).toHaveLength(1);
});

test('error muestra texto según code, sin eco del servidor, y reintenta solo si es reintentable', async () => {
  const retry = vi.fn();
  const user = userEvent.setup();
  const { rerender } = render(
    <StreamErrorCard language="spanish" error={{ code: 'TIMEOUT', retryable: true }} onRetry={retry} />,
  );
  expect(screen.getByRole('alert')).toHaveTextContent('tardó demasiado');
  await user.click(screen.getByRole('button', { name: 'Reintentar' }));
  expect(retry).toHaveBeenCalledTimes(1);
  rerender(<StreamErrorCard language="spanish" error={{ code: 'INTERNAL_ERROR', retryable: false }} onRetry={retry} />);
  expect(screen.queryByRole('button', { name: 'Reintentar' })).toBeNull();
  rerender(<StreamErrorCard language="quechua" error={{ code: 'TIMEOUT', retryable: true }} onRetry={retry} />);
  expect(screen.getByRole('button', { name: 'Yapamanta ruway' })).toBeVisible();
});

test('tiempo de respuesta muestra segundos y desglose por etapa', () => {
  const timings = { total_ms: 2350, stages: { retrieval: 800, generation: 1200 }, cache_hit: false };
  const { rerender } = render(<ResponseTiming language="spanish" timings={timings} />);
  expect(screen.getByText('Respondió en 2.4 s')).toBeVisible();
  expect(screen.getByText('Búsqueda: 0.8 s')).toBeInTheDocument();
  expect(screen.getByText('Redacción: 1.2 s')).toBeInTheDocument();
  rerender(<ResponseTiming language="spanish" timings={{ total_ms: 3, stages: {}, cache_hit: true }} />);
  expect(screen.getByText('Respuesta desde caché')).toBeVisible();
});

test('la terminal integra etapas, error con reintento y tiempos del asistente', async () => {
  const retry = vi.fn();
  const user = userEvent.setup();
  render(
    <TerminalModal
      isOpen
      onSend={vi.fn()}
      onClose={vi.fn()}
      onRetry={retry}
      messages={[
        { id: 'u', content: 'Consulta', isUser: true },
        { id: 'a1', content: '', isUser: false, isStreaming: true, stage: 'retrieval', completedStages: [] },
        { id: 'a2', content: '', isUser: false, errorInfo: { code: 'RETRIEVAL_UNAVAILABLE', retryable: true } },
        { id: 'a3', content: 'Listo', isUser: false, timings: { total_ms: 1000, stages: {}, cache_hit: false } },
      ]}
    />,
  );
  expect(screen.getByText('Buscando en el corpus')).toBeVisible();
  expect(screen.getByRole('alert')).toHaveTextContent('corpus legal');
  expect(screen.getByText('Respondió en 1.0 s')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Reintentar' }));
  expect(retry).toHaveBeenCalledWith('a2');
});
