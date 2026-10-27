import { test, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const auth = vi.hoisted(() => ({ value: { isAuthenticated: true, mounted: true, user: { roles: ['admin'] } as { roles: string[] } | null } }));
vi.mock('../../../frontend/src/presentation/components/AuthProvider', () => ({ useAuth: () => auth.value }));
vi.mock('next/link', () => ({ default: ({ href, children, ...rest }: { href: string; children: unknown }) => {
  const React = require('react'); return React.createElement('a', { href, ...rest }, children);
} }));

import { QualityAdminPage } from '../../../frontend/src/presentation/pages/QualityAdminPage';
import { QualityPage } from '../../../frontend/src/presentation/pages/QualityPage';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;
const status = (code: number) => ({ ok: false, status: code, json: async () => ({}) }) as Response;

const published = {
  schema: 1, status: 'preliminar', sha: 'abcdef1234567890', dirty: true, generated_at: '2026-10-22T10:00:00+00:00',
  notices: ['Medición preliminar: los casos del gold son candidatos.', 'Las métricas no certifican verdad jurídica.'],
  suites: {
    legal_qa: { measured: false, reason: 'Aún no se ejecutó esta evaluación.' },
    retrieval: { measured: true, n_cases: 37, note: 'Motor local sin LightRAG ni reranker de Cohere.',
      systems: { lexical: { 'evidence_recall@5': { macro: 0.629, micro: 0.6, n: 31 }, mrr: { macro: 0.491, micro: 0.49, n: 31 } } } },
    translation: { measured: true, n_scored: 3, metrics: { ter: { macro: 1.7, micro: 1.7, n: 3 } } },
  },
};

beforeEach(() => {
  auth.value = { isAuthenticated: true, mounted: true, user: { roles: ['admin'] } };
  vi.unstubAllGlobals();
});

test('la página pública muestra avisos, lo medido con sus valores y lo no medido con su razón', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ok({ published })));
  render(<QualityPage />);
  expect(screen.getByRole('status')).toHaveTextContent('Cargando métricas');
  expect(await screen.findByText('Medición preliminar', { selector: 'span' })).toBeVisible();
  expect(screen.getByText(/Versión abcdef1234 \(con cambios sin confirmar\)/)).toBeVisible();
  const notices = screen.getByRole('region', { name: 'Avisos' });
  expect(within(notices).getAllByRole('listitem')).toHaveLength(2);
  const legal = screen.getByRole('region', { name: 'Respuestas jurídicas' });
  expect(within(legal).getByText('No medido')).toBeVisible();
  expect(within(legal).getByText('Aún no se ejecutó esta evaluación.')).toBeVisible();
  const retrieval = screen.getByRole('region', { name: 'Recuperación de fuentes' });
  expect(within(retrieval).getByText('Medido')).toBeVisible();
  expect(within(retrieval).getByText(/sin LightRAG/)).toBeVisible();
  expect(within(retrieval).getByRole('row', { name: /Evidencia correcta entre las 5 primeras fuentes/ })).toHaveTextContent(`${(62.9).toLocaleString('es-PE')} %`);
  expect(within(screen.getByRole('region', { name: 'Traducción al quechua' })).getByRole('row', { name: /Tasa de edición/ })).toHaveTextContent('menor es mejor');
});

test('la página pública cambia a quechua y se recupera de un error con un reintento', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(status(503)).mockResolvedValue(ok({ published }));
  vi.stubGlobal('fetch', fetchMock);
  const user = userEvent.setup();
  render(<QualityPage />);
  expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos cargar las métricas');
  await user.click(screen.getByRole('button', { name: 'Reintentar' }));
  expect(await screen.findByText('Medición preliminar', { selector: 'span' })).toBeVisible();
  await user.selectOptions(screen.getByLabelText('Idioma'), 'quechua');
  expect(screen.getByRole('heading', { name: 'Asistentepa allin kaynin' })).toBeVisible();
  expect(screen.getByText('Ñawpaq tupuy')).toBeVisible();
  expect(screen.getByRole('region', { name: 'Derecho kutichiykuna' })).toBeVisible();
});

const overview = {
  comparison: {
    base: { ref: 'v8', sha: 'a'.repeat(40) }, head: { ref: 'HEAD', sha: 'b'.repeat(40) }, verdict: 'EMPEORÓ', blocking: true, comparable: false,
    blocks: [{ suite: 'legal_qa', kind: 'afirmación_nueva_sin_respaldo', case_id: 'pension-tope-embargo', stratum: 'positivo' }], missing: [],
    suites: [{ suite: 'legal_qa', metrics: [{ metric: 'legal_factuality', scope: 'macro', base: 0.8, head: 0.6, delta: -0.2, status: 'worse' }] }],
  },
  gold: { available: true, pending_lawyers: 37, pending_native_speakers: 319 },
  feedback: { total: 3, up: 1, down: 2, reasons: { incorrecta: 2 }, queue: { pending: 1, accepted: 0, rejected: 0 } },
  feedback_queue: [{ id: 'abc', created_at: '2026-10-22', reason: 'incorrecta', comment: 'falta el artículo', language: 'spanish', query: '¿Cuánto es la pensión?', answer: 'x', evidence_status: null, translation_quality: null }],
  stream: { n: 4, outcomes: { final: 4 }, ttfb_ms: { n: 4, p50: 12, p95: 30 }, total_ms: { n: 4, p50: 900, p95: 1500 },
    stage_ms: { retrieval: { n: 4, p50: 100, p95: 200 }, generation: { n: 4, p50: 500, p95: 900 } }, lines: {} },
};

test('el panel de administración muestra regresiones, bloqueos, colas de revisión, feedback y latencia', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ok({ overview })));
  render(<QualityAdminPage />);
  const comparison = await screen.findByRole('region', { name: 'Regresiones entre commits' });
  expect(within(comparison).getByText('Empeoró')).toHaveAttribute('data-verdict', 'EMPEORÓ');
  expect(within(comparison).getByText('Bloqueante')).toBeVisible();
  expect(within(comparison).getByText(/pension-tope-embargo/)).toBeVisible();
  expect(within(comparison).getByRole('note')).toHaveTextContent('No comparable');
  expect(within(comparison).getByRole('row', { name: /legal_factuality/ })).toHaveTextContent((-0.2).toLocaleString('es-PE', { maximumFractionDigits: 3 }));
  const queues = screen.getByRole('region', { name: 'Colas de revisión humana' });
  expect(queues).toHaveTextContent('37 casos esperan la revisión ciega de dos abogados');
  expect(queues).toHaveTextContent('319 pares esperan a hablantes nativos');
  expect(screen.getByText('1 👍 · 2 👎')).toBeVisible();
  expect(screen.getByText('¿Cuánto es la pensión?')).toBeVisible();
  const stream = screen.getByRole('region', { name: /Latencia del stream/ });
  expect(within(stream).getByRole('row', { name: /Búsqueda/ })).toHaveTextContent('100');
});

test('aceptar un candidato llama a la decisión y recarga el panel', async () => {
  const fetchMock = vi.fn(async (url: string) => (String(url).includes('/decision') ? ok({ success: true }) : ok({ overview })));
  vi.stubGlobal('fetch', fetchMock);
  const user = userEvent.setup();
  render(<QualityAdminPage />);
  await user.click(await screen.findByRole('button', { name: 'Aceptar' }));
  await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/quality/admin/overview'))).toHaveLength(2));
  const decision = fetchMock.mock.calls.find(([url]) => String(url).includes('/decision'))!;
  expect(String(decision[0])).toContain('/feedback/queue/abc/decision');
  expect(JSON.parse((decision[1] as RequestInit).body as string)).toEqual({ decision: 'accept' });
  expect(screen.getByText(/Aceptar no agrega el caso al gold/)).toBeVisible();
});

test('sin sesión o sin rol admin el panel no pide datos y explica el acceso', async () => {
  const fetchMock = vi.fn(async () => ok({ overview }));
  vi.stubGlobal('fetch', fetchMock);
  auth.value = { isAuthenticated: false, mounted: true, user: null };
  const { rerender } = render(<QualityAdminPage />);
  expect(screen.getByRole('alert')).toHaveTextContent('Inicia sesión');
  expect(screen.getByRole('link', { name: 'Ir a iniciar sesión' })).toHaveAttribute('href', '/login');
  auth.value = { isAuthenticated: true, mounted: true, user: { roles: ['user'] } };
  rerender(<QualityAdminPage />);
  expect(screen.getByRole('alert')).toHaveTextContent('solo para administradores');
  expect(fetchMock).not.toHaveBeenCalled();
});

test('si el servidor responde 403 aunque el rol local diga admin, se muestra acceso restringido', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => status(403)));
  render(<QualityAdminPage />);
  expect(await screen.findByRole('alert')).toHaveTextContent('solo para administradores');
});

test('un fallo del servidor ofrece reintentar y el panel existe en quechua', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(status(500)).mockResolvedValue(ok({ overview: { ...overview, comparison: null, feedback_queue: [] } }));
  vi.stubGlobal('fetch', fetchMock);
  const user = userEvent.setup();
  render(<QualityAdminPage />);
  expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos cargar el panel');
  await user.click(screen.getByRole('button', { name: 'Reintentar' }));
  expect(await screen.findByText(/Aún no hay comparaciones/)).toBeVisible();
  expect(screen.getByText('No hay candidatos pendientes.')).toBeVisible();
  await user.selectOptions(screen.getByLabelText('Idioma'), 'quechua');
  expect(screen.getByRole('heading', { name: 'Allin kay · kamachiq' })).toBeVisible();
});
