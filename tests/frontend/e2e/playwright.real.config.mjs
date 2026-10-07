import { defineConfig } from '@playwright/test';
if (process.env.RUN_MODEL_EVALS !== '1') throw new Error('Usa pnpm test:e2e:real --run-model-evals para confirmar red/coste.');
for (const key of ['PLAYWRIGHT_TARGET_URL', 'PLAYWRIGHT_API_URL']) {
  if (!process.env[key]) throw new Error(`Configura ${key} con la URL de tu instalación local de prueba.`);
  const url = new URL(process.env[key]);
  if (!['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || !['http:', 'https:'].includes(url.protocol)) {
    throw new Error(`${key} debe apuntar a una instalación local de prueba, no producción.`);
  }
}
export default defineConfig({
  testDir: '.', testMatch: '**/*.real.spec.js', workers: 1, retries: 0, timeout: 180000,
  outputDir: '../../../temp/playwright-real-results', reporter: 'list',
  use: { baseURL: process.env.PLAYWRIGHT_TARGET_URL, headless: true, reducedMotion: 'reduce', trace: 'off', screenshot: 'off', video: 'off',
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
  },
});
