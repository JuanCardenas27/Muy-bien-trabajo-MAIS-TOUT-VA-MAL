// E2E de la app real sobre el bundle de demostración (Task WEB-13, R-21).
//
// Toda la preparación vive en `webServer.command`: build con `VITE_E2E=1`,
// `frances demo-bundle` en `dist/data` y `vite preview` en el 4173. No hay
// script `e2e:prepare`; OPS-01 solo ejecuta `playwright test`.

import { defineConfig, devices } from '@playwright/test';

const PORT = 4173;
const BASE_URL = `http://localhost:${PORT}/`;

export default defineConfig({
  testDir: './e2e',
  // Vitest también recoge `**/*.spec.ts`; los e2e usan `.e2e.ts` para no
  // ejecutarse con `npm run test` (la exclusión vive en vite.config.ts, de
  // WEB-12, así que aquí se resuelve sin tocar fuera de `owns`).
  testMatch: /.*\.e2e\.ts$/,
  outputDir: '../.cache/playwright-results',
  // Cada desbloqueo deriva la clave con PBKDF2 (600 000 iteraciones) y
  // `frances demo-bundle` tarda lo suyo; los timeouts por defecto se quedan
  // cortos en runners de 2 vCPU. Un solo worker evita que las derivaciones
  // compitan por CPU.
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: true,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: BASE_URL },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: {
    command:
      'VITE_E2E=1 npm run build -- --mode e2e && uv run --project .. frances demo-bundle --out dist/data && npm run preview -- --port 4173 --strictPort',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
