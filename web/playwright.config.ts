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
  // PBKDF2 del bundle (600 000 iteraciones) y pdf.js pueden tardar más que
  // los 5 s por defecto de un `expect` en webkit.
  expect: { timeout: 15_000 },
  // El demo es el mismo para cada spec; los contextos son independientes.
  fullyParallel: true,
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
