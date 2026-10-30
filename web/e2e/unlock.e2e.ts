// Desbloqueo del bundle de demostración (Task WEB-13, Review Focus 5).

import { expect, test } from '@playwright/test';
import { unlockDemo } from './helpers';

test('wrong passphrase shows error and keeps input', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Passphrase').fill('no es la del demo para nada');
  await page.getByRole('button', { name: 'Desbloquear' }).click();
  await expect(page.getByRole('alert')).toHaveText('Passphrase incorrecta');
  await expect(page.getByLabel('Passphrase')).toHaveValue(
    'no es la del demo para nada',
  );
});

test('unlock demo lands on Hoy', async ({ page }) => {
  await unlockDemo(page);
  await expect(
    page.getByRole('heading', { name: 'Hoy', level: 1 }),
  ).toBeVisible();
});
