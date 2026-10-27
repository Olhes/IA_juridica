import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
export default defineConfig({
  root,
  resolve: {
    dedupe: ['react', 'react-dom'],
    // One React instance, including tests located outside the Next workspace.
    alias: {
      react: fileURLToPath(new URL('../../node_modules/react', import.meta.url)),
      'react-dom': fileURLToPath(new URL('../../node_modules/react-dom', import.meta.url)),
      'lucide-react': fileURLToPath(new URL('../../frontend/node_modules/lucide-react/dist/esm/lucide-react.mjs', import.meta.url)),
      'next/link': fileURLToPath(new URL('../../frontend/node_modules/next/link.js', import.meta.url)),
      'next/navigation': fileURLToPath(new URL('../../frontend/node_modules/next/navigation.js', import.meta.url)),
      'next/font/google': fileURLToPath(new URL('../../frontend/node_modules/next/font/google/index.js', import.meta.url)),
    },
  },
  oxc: { jsx: { runtime: 'automatic' } },
  test: {
    environment: 'jsdom',
    include: ['tests/frontend/{unit,component,integration}/**/*.test.{ts,tsx,mts}'],
    setupFiles: ['tests/frontend/fixtures/setup.ts'],
    clearMocks: true,
    server: { deps: { inline: ['lucide-react', 'next-themes'] } },
    restoreMocks: true,
    maxWorkers: 2,
    env: { NEXT_PUBLIC_API_URL: 'http://localhost:8000' },
    coverage: {
      provider: 'v8',
      include: ['frontend/src/**/*.{ts,tsx}', 'frontend/app/**/*.{ts,tsx}'],
      exclude: ['**/*.d.ts'],
      reportsDirectory: 'temp/sonar-reports/frontend-coverage',
      reporter: ['text', 'lcov', 'json-summary'],
    },
  },
});
