// Taladro por fonema débil (Tasks WEB-13 + PRN-05): /ɑ̃/ codificado en la URL.

import { expect, test } from '@playwright/test';
import { installFakeRecognizer, unlockDemo } from './helpers';

test('drill for nasal a', async ({ page }) => {
  await installFakeRecognizer(page);
  await unlockDemo(page, '/drill/%C9%91%CC%83');

  await expect(
    page.getByRole('heading', { level: 1, name: 'Taladro /ɑ̃/' }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Grabar', exact: true }),
  ).toBeVisible();
});
