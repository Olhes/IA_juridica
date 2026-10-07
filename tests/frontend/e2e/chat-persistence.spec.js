const { test, expect } = require('@playwright/test');
const { default: AxeBuilder } = require('@axe-core/playwright');
test.beforeEach(async ({ page }) => { const { mockApi } = await import('../fixtures/browser.mjs'); await mockApi(page); });
test('interfaz actual envía consulta y conserva respuesta al recargar', async ({ page }) => {
  await page.goto('/'); await page.getByRole('button', { name: 'Comenzar consulta' }).click();
  await page.getByRole('textbox', { name: 'Consulta legal' }).fill('Consulta sintética'); await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog').getByText('Respuesta sintética á 🦙', { exact: true })).toBeVisible();
  await page.reload(); await expect(page.getByRole('heading', { name: /orientación legal clara/i })).toBeVisible();
  await page.getByRole('button').filter({ hasText: 'Consulta sintética' }).first().click();
  await expect(page.getByRole('dialog').getByText('Respuesta sintética á 🦙', { exact: true })).toBeVisible();
});
test('interfaz recupera listado después de caída temporal simulada', async ({ page }) => {
  await page.route('**/chat/conversations?**', route => route.abort(), { times: 1 });
  await page.goto('/'); const alert = page.getByRole('alert').filter({ hasText: 'No pudimos cargar tus consultas.' }); await expect(alert).toBeVisible();
  await alert.getByRole('button', { name: 'Reintentar' }).click(); await expect(alert).toBeHidden();
});
test('nueva consulta móvil no muestra mensajes de sesión anterior', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto('/');
  await page.getByRole('button', { name: 'Comenzar consulta' }).click();
  await page.getByRole('textbox').fill('Consulta anterior'); await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog').getByText('Respuesta sintética á 🦙', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Cerrar', exact: true }).click();
  await page.getByRole('button', { name: 'Abrir panel de consultas' }).click();
  await page.getByRole('button', { name: 'Nueva consulta' }).last().click();
  await expect(page.getByRole('dialog').getByText('Consulta anterior', { exact: true })).toBeHidden(); await expect(page.getByRole('textbox')).toBeVisible();
});
test('terminal accesible permite teclado Escape y devuelve foco', async ({ page }) => {
  await page.goto('/'); await page.getByRole('button', { name: 'Comenzar consulta' }).click();
  await expect(page.getByRole('textbox')).toBeFocused(); await page.getByRole('textbox').fill('Consulta de teclado');
  await page.keyboard.press('Tab'); await expect(page.getByRole('button', { name: 'Enviar consulta' })).toBeFocused();
  await page.keyboard.press('Tab'); await expect(page.getByRole('button', { name: 'Cerrar', exact: true })).toBeFocused();
  await page.keyboard.press('Shift+Tab'); await expect(page.getByRole('button', { name: 'Enviar consulta' })).toBeFocused();
  await expect(page.getByRole('dialog')).toBeVisible(); await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Abrir terminal', exact: true })).toBeFocused();
});
test('pantalla y terminal no tienen violaciones axe serias o críticas', async ({ page }) => {
  await page.goto('/'); await expect(page.getByRole('button', { name: 'Comenzar consulta' })).toBeVisible();
  let results = await new AxeBuilder({ page }).analyze(); expect(results.violations.filter(v => ['serious', 'critical'].includes(v.impact))).toEqual([]);
  await page.getByRole('button', { name: 'Comenzar consulta' }).click();
  results = await new AxeBuilder({ page }).include('[role="dialog"]').analyze(); expect(results.violations.filter(v => ['serious', 'critical'].includes(v.impact))).toEqual([]);
});
