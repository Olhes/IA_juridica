import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

// Limitar el discovery al navegador; no cargar los tests de node:test.
export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.js',
  testIgnore: '**/*.real.spec.js',
  outputDir: '../../../temp/playwright-results',
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://localhost:3100', headless: true, reducedMotion: 'reduce', trace: 'retain-on-failure',
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
  },
  webServer: {
    cwd: fileURLToPath(new URL('../../../', import.meta.url)),
    command: 'node frontend/node_modules/next/dist/bin/next dev frontend --port 3100',
    url: 'http://localhost:3100', reuseExistingServer: false, timeout: 120000,
    env: { NEXT_PUBLIC_API_URL: 'http://localhost:8000' },
  },
});
