const { test, expect } = require('@playwright/test');

const published = {
  schema: 1, status: 'preliminar', sha: 'abcdef1234567890', dirty: false, generated_at: '2026-10-22T10:00:00+00:00',
  notices: ['Medición preliminar: los casos del gold son candidatos.'],
  suites: {
    legal_qa: { measured: false, reason: 'Aún no se ejecutó esta evaluación.' },
    retrieval: { measured: true, n_cases: 37, systems: { lexical: { 'evidence_recall@5': { macro: 0.629, micro: 0.6, n: 31 } } } },
  },
};
const overview = {
  comparison: { base: { ref: 'v8', sha: 'a'.repeat(40) }, head: { ref: 'HEAD', sha: 'b'.repeat(40) }, verdict: 'EMPEORÓ', blocking: true, comparable: true,
    blocks: [{ suite: 'legal_qa', kind: 'afirmación_nueva_sin_respaldo', case_id: 'pension-tope-embargo', stratum: 'positivo' }], missing: [], suites: [] },
  gold: { available: true, pending_lawyers: 37, pending_native_speakers: 319 },
  feedback: { total: 0, up: 0, down: 0, reasons: {}, queue: { pending: 0, accepted: 0, rejected: 0 } }, feedback_queue: [],
  stream: { n: 0, outcomes: {}, ttfb_ms: { n: 0, p50: null, p95: null }, total_ms: { n: 0, p50: null, p95: null }, stage_ms: {}, lines: {} },
};

test('la página pública /calidad muestra avisos, lo medido y lo no medido, y cambia de idioma', async ({ page }) => {
  const { mockApi } = await import('../fixtures/browser.mjs'); await mockApi(page, { published });
  await page.goto('/calidad');
  await expect(page.getByRole('heading', { name: 'Calidad del asistente' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Avisos' })).toContainText('Medición preliminar');
  await expect(page.getByRole('region', { name: 'Respuestas jurídicas' })).toContainText('No medido');
  await expect(page.getByRole('region', { name: 'Recuperación de fuentes' })).toContainText('Medido');
  await page.getByLabel('Idioma').selectOption('quechua');
  await expect(page.getByRole('heading', { name: 'Asistentepa allin kaynin' })).toBeVisible();
});

test('/calidad/admin muestra regresiones y colas a un administrador', async ({ page }) => {
  const { mockApi } = await import('../fixtures/browser.mjs'); await mockApi(page, { roles: ['admin'], overview });
  await page.goto('/calidad/admin');
  const comparison = page.getByRole('region', { name: 'Regresiones entre commits' });
  await expect(comparison).toContainText('Empeoró'); await expect(comparison).toContainText('Bloqueante');
  await expect(comparison).toContainText('pension-tope-embargo');
  await expect(page.getByRole('region', { name: 'Colas de revisión humana' })).toContainText('319 pares esperan a hablantes nativos');
});

test('/calidad/admin niega el acceso a quien no es administrador', async ({ page }) => {
  const { mockApi } = await import('../fixtures/browser.mjs'); await mockApi(page, { roles: ['user'] });
  await page.goto('/calidad/admin');
  await expect(page.getByRole('alert').filter({ hasText: 'solo para administradores' })).toBeVisible();
});

test('el 👎 con motivo viaja a /feedback sin el texto de la consulta salvo que se autorice', async ({ page }) => {
  const { mockApi } = await import('../fixtures/browser.mjs'); const api = await mockApi(page);
  await page.goto('/'); await page.getByRole('button', { name: 'Comenzar consulta' }).click();
  await page.getByRole('textbox', { name: 'Consulta legal' }).fill('Consulta privada [stream:valid]'); await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText('Respuesta final validada ñ 🦙', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'No útil' }).click();
  await dialog.getByLabel('No cita fuentes').check();
  await dialog.getByRole('button', { name: 'Enviar', exact: true }).click();
  await expect(dialog.getByRole('status').filter({ hasText: 'Gracias' })).toBeVisible();
  expect(api.feedback).toHaveLength(1);
  expect(api.feedback[0]).toMatchObject({ request_id: '0123456789abcdef0123456789abcdef', rating: 'down', reason: 'sin_fuentes', share_text: false, language: 'spanish' });
  expect(JSON.stringify(api.feedback[0])).not.toContain('privada');
});
