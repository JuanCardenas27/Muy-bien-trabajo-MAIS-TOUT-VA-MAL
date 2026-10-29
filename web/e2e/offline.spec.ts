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

  await context.setOffline(true);
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Hoy', level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByText('Sin conexión: mostrando lo último descargado'),
  ).toBeVisible();
});
