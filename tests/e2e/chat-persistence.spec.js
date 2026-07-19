const { test, expect } = require('@playwright/test');

const targetUrl = process.env.PLAYWRIGHT_TARGET_URL;

test('recovers conversation history after a temporary backend outage', async ({ page }) => {
  test.skip(!targetUrl, 'PLAYWRIGHT_TARGET_URL is required');
  const consoleErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });

  await page.route('**/chat/conversations?**', (route) => route.abort('connectionrefused'), { times: 1 });
  await page.goto(targetUrl);

  const loadAlert = page.getByRole('alert').filter({ hasText: /no pudimos cargar tus consultas/i });
  await expect(loadAlert).toContainText(/no pudimos cargar tus consultas/i);
  await loadAlert.getByRole('button', { name: /reintentar/i }).click();
  await expect(loadAlert).toBeHidden();
  expect(consoleErrors.filter((message) => /failed to fetch|api error/i.test(message))).toEqual([]);
});

test('persists assistant messages across refresh and keeps the home route on landing', async ({ page }) => {
  test.skip(!targetUrl, 'PLAYWRIGHT_TARGET_URL is required');
  test.setTimeout(180000);

  await page.goto(targetUrl);
  await expect(page.getByRole('heading', { name: /orientacion legal clara para actuar hoy/i })).toBeVisible();

  const createConversation = page.waitForResponse(
    (response) => response.url().includes('/chat/conversations') && response.request().method() === 'POST'
  );
  await page.locator('#new-session-btn').click();
  const conversation = await (await createConversation).json();
  const sessionRow = page.locator(`#session-menu-${conversation.id}`).locator('xpath=../..').first();
  await expect(sessionRow).toHaveClass(/bg-indigo-600/);
  const query = `Persistence check ${Date.now()}`;
  const streamResponse = page.waitForResponse(
    (response) => response.url().includes('/legal-query-stream') && response.request().method() === 'POST'
  );
  await page.locator('#chat-input').fill(query);
  await page.locator('#chat-send-btn').click();
  await (await streamResponse).finished();

  const messageArea = page.locator('main');
  await expect(messageArea).toContainText(query);
  await expect(page.locator('.markdown-content')).toContainText(/\S/, { timeout: 120000 });

  const assistantText = await page.locator('.markdown-content').innerText();
  expect(assistantText.length).toBeGreaterThan(0);

  await page.reload();
  await expect(page.getByRole('heading', { name: /orientacion legal clara para actuar hoy/i })).toBeVisible();
  await expect(messageArea).not.toContainText(query);

  await sessionRow.click();
  await expect(messageArea).toContainText(query);
  await expect(page.locator('.markdown-content')).toContainText(assistantText);
});
