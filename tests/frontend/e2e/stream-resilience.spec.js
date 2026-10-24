const { test, expect } = require('@playwright/test');

const FINAL = 'Respuesta final validada ñ 🦙';
let api;
test.beforeEach(async ({ page }) => { const { mockApi } = await import('../fixtures/browser.mjs'); api = await mockApi(page); });

async function ask(page, query) {
  await page.goto('/'); await page.getByRole('button', { name: 'Comenzar consulta' }).click();
  await page.getByRole('textbox', { name: 'Consulta legal' }).fill(query); await page.keyboard.press('Enter');
}
const dialog = page => page.getByRole('dialog');

test('stream con BOM y CRLF se muestra completo con el tiempo de respuesta', async ({ page }) => {
  await ask(page, 'Consulta [stream:bom_crlf]');
  await expect(dialog(page).getByText(FINAL, { exact: true })).toBeVisible();
  await expect(dialog(page).getByText(/Respondió en/)).toBeVisible();
  await expect(dialog(page).getByText('Respuesta parcial')).toBeHidden();
});

test('una línea corrupta, un prefijo data: y eventos pegados no tiran la respuesta', async ({ page }) => {
  for (const name of ['invalid_line', 'repairable_prefix', 'concatenated_objects']) {
    await ask(page, `Consulta [stream:${name}]`);
    await expect(dialog(page).getByText(FINAL, { exact: true }).first()).toBeVisible();
  }
});

test('eventos duplicados o desordenados muestran la respuesta una sola vez', async ({ page }) => {
  for (const name of ['duplicate_events', 'out_of_order']) {
    await ask(page, `Consulta [stream:${name}]`);
    await expect(dialog(page).getByText(FINAL, { exact: true })).toHaveCount(1);
  }
});

test('sin evento final se muestra el texto recibido con aviso de respuesta parcial', async ({ page }) => {
  await ask(page, 'Consulta [stream:missing_final]');
  await expect(dialog(page).getByText(FINAL, { exact: true })).toBeVisible();
  await expect(dialog(page).getByText('Respuesta parcial')).toBeVisible();
  await ask(page, 'Consulta [stream:truncated_final]');
  await expect(dialog(page).getByText('Respuesta parcial')).toBeVisible();
});

test('un error con código se explica en español y permite reintentar', async ({ page }) => {
  await ask(page, 'Consulta [stream:error_event]');
  await expect(dialog(page).getByRole('alert')).toContainText('tardó demasiado');
  const before = api.calls.filter(call => call.stream === 'error_event').length;
  await dialog(page).getByRole('button', { name: 'Reintentar' }).click();
  await expect.poll(() => api.calls.filter(call => call.stream === 'error_event').length).toBe(before + 1);
});

test('un stream vacío o de otra versión termina con un mensaje recuperable', async ({ page }) => {
  for (const name of ['empty', 'unsupported_version']) {
    await ask(page, `Consulta [stream:${name}]`);
    await expect(dialog(page).getByText(/No se pudo completar la respuesta/)).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Consulta legal' })).toBeEnabled();
  }
});

test('la telemetría del stream viaja sin texto de la consulta ni de la respuesta', async ({ page }) => {
  await ask(page, 'Consulta privada [stream:valid]');
  await expect(dialog(page).getByText(FINAL, { exact: true })).toBeVisible();
  await expect.poll(() => api.beacons.length).toBeGreaterThan(0);
  const body = api.beacons[0];
  expect(JSON.parse(body)).toMatchObject({ request_id: '0123456789abcdef0123456789abcdef', outcome: 'final' });
  expect(body).not.toContain('privada');
  expect(body).not.toContain('Respuesta final');
});
