const { test, expect } = require('@playwright/test');
const api = process.env.PLAYWRIGHT_API_URL;
test('servicios reales recuperan historial después de caída temporal', async ({ page }) => {
  await page.route('**/chat/conversations?**', route => route.abort(), { times: 1 });
  await page.goto('/'); const alert = page.getByRole('alert').filter({ hasText: 'No pudimos cargar tus consultas.' }); await expect(alert).toBeVisible();
  await alert.getByRole('button', { name: 'Reintentar' }).click(); await expect(alert).toBeHidden();
});
test('consulta real sintética persiste al recargar y se limpia al terminar', async ({ page }) => {
  let id;
  try {
    await page.goto('/'); const created = page.waitForResponse(r => r.url().includes('/chat/conversations') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Comenzar consulta' }).click(); id = (await (await created).json()).id;
    const query = `Prueba sintética ${Date.now()}: ¿qué pasos generales orientan una consulta sobre pensión de alimentos sin datos personales?`;
    const finished = page.waitForResponse(r => r.url().includes('/legal-query-stream') && r.request().method() === 'POST');
    await page.getByRole('textbox').fill(query); await page.keyboard.press('Enter');
    const response = await finished; expect(response.ok()).toBe(true); await response.finished();
    const final = (await response.text()).trim().split('\n').map(line => JSON.parse(line)).find(e => e.type === 'final');
    const text = final?.data?.response?.respuesta_espanol; expect(text?.trim().length).toBeGreaterThan(0);
    await expect(page.getByRole('dialog').getByText(text, { exact: true })).toBeVisible(); await page.reload();
    await page.locator(`#session-menu-${id}`).locator('..').locator('..').click(); await expect(page.getByRole('dialog').getByText(text, { exact: true })).toBeVisible();
  } finally { if (id) await page.request.delete(`${api}/chat/conversations/${id}`); }
});
test('servicios reales aíslan principales anónimos en dos contextos', async ({ browser }) => {
  const a = await browser.newContext(); const b = await browser.newContext(); let id;
  try {
    const left = await a.request.post(`${api}/session/bootstrap`); const right = await b.request.post(`${api}/session/bootstrap`);
    expect((await left.json()).principal_id).not.toBe((await right.json()).principal_id);
    expect((await a.cookies(api)).find(c => c.name === 'ia_juridica_session')?.httpOnly).toBe(true);
    id = (await (await a.request.post(`${api}/chat/conversations`, { data: { language: 'spanish', title: 'Test sintético aislado' } })).json()).id;
    expect((await b.request.get(`${api}/chat/conversations/${id}`)).status()).toBe(404);
    expect((await a.request.get(`${api}/chat/conversations/${id}`)).ok()).toBe(true);
  } finally { if (id) await a.request.delete(`${api}/chat/conversations/${id}`); await a.close(); await b.close(); }
});
