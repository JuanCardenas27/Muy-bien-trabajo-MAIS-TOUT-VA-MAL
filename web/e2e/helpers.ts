// Helpers de las specs e2e sobre el bundle de demostración (Task WEB-13).
//
// `unlockDemo` desbloquea con la passphrase pública del demo (BND-04).
// `installFakeRecognizer` instala, vía `addInitScript`, el recognizer falso
// que `getRecognizer` acepta cuando el build se hizo con `VITE_E2E=1`
// (contrato de PRN-02) y devuelve el JSON sintético de SPK-04.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { Page } from '@playwright/test';

export const DEMO_PASSPHRASE = 'demo demo demo demo demo demo';

// Fixture sintético de SPK-04 (R-22), leído desde el repo, no desde la red.
export const BONJOUR_JSON: unknown = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL('../../tests/fixtures/azure/bonjour.json', import.meta.url),
    ),
    'utf8',
  ),
) as unknown;

// Desbloquea el demo. `path` permite aterrizar en una pantalla protegida
// (RequireUnlocked conserva el destino en `?next=`).
export async function unlockDemo(page: Page, path = '/'): Promise<void> {
  await page.goto(path);
  await page.getByLabel('Passphrase').fill(DEMO_PASSPHRASE);
  await page.getByRole('button', { name: 'Desbloquear', exact: true }).click();
}

// Aísla la spec del hardware: `createRecorder` siempre pide un stream de
// micrófono aunque el recognizer sea falso. El objeto solo necesita
// `getTracks()` (lo que usa el recorder para detener las pistas).
export async function installFakeRecognizer(page: Page): Promise<void> {
  await page.addInitScript(
    ({ json, durationMs }) => {
      const mediaDevices = navigator.mediaDevices as MediaDevices | undefined;
      const getUserMedia = async (): Promise<MediaStream> =>
        ({ getTracks: () => [] }) as unknown as MediaStream;
      if (mediaDevices !== undefined) {
        Object.defineProperty(mediaDevices, 'getUserMedia', {
          configurable: true,
          value: getUserMedia,
        });
      } else {
        Object.defineProperty(navigator, 'mediaDevices', {
          configurable: true,
          value: { getUserMedia },
        });
      }
      Object.assign(window, {
        __francesFakeRecognizer: {
          assess: async () => ({ json, durationMs }),
        },
      });
    },
    { json: BONJOUR_JSON, durationMs: 1500 },
  );
}
