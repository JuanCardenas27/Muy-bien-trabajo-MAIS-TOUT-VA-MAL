// PWA offline (Tasks WEB-13 + WEB-12): tras la primera carga, el shell y el
// bundle quedan en caché y la app abre sin red.

import { expect, test } from '@playwright/test';
import { unlockDemo } from './helpers';

test('works offline after first load', async ({ page, context }) => {
  await unlockDemo(page);
  await expect(
    page.getByRole('heading', { name: 'Hoy', level: 1 }),
  ).toBeVisible();

  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Hoy', level: 1 }),
  ).toBeVisible();

  // Workbox guarda el manifiesto y el índice en segundo plano: sin esperar
  // a que existan, la recarga offline puede adelantarse.
  await expect
    .poll(
      async () =>
        page.evaluate(async () => {
          if (navigator.serviceWorker.controller === null) {
            return false;
          }
          const names = await caches.keys();
          if (
            !names.includes('frances-manifest') ||
            !names.includes('frances-bins')
          ) {
            return false;
          }
          const manifest = await (await caches.open('frances-manifest')).keys();
          const bins = await (await caches.open('frances-bins')).keys();
          return (
            manifest.some((request) => request.url.endsWith('/bundle.json')) &&
            bins.some((request) =>
              /\/d\/[0-9a-f]{32}\.bin$/.test(new URL(request.url).pathname),
            )
          );
        }),
      { timeout: 30_000 },
    )
    .toBe(true);

  await context.setOffline(true);
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Hoy', level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByText('Sin conexión: mostrando lo último descargado'),
  ).toBeVisible();
});
