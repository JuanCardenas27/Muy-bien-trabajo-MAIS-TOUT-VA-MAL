// Audio pregrabado de una tarjeta (Task WEB-13): el blob descifrado se
// reproduce desde una object URL.

import { expect, test } from '@playwright/test';
import { unlockDemo } from './helpers';

// `c_fc43341b9ea63489` es la tarjeta «Bonjour» del demo (BND-04).
test('plays audio', async ({ page }) => {
  await unlockDemo(page);
  await page.goto('/cards?card=c_fc43341b9ea63489');

  await page
    .getByRole('button', { name: 'Reproducir', exact: true })
    .first()
    .click();
  await expect(
    page.getByRole('button', { name: 'Detener', exact: true }).first(),
  ).toBeVisible();

  const audio = page.locator('audio').first();
  await expect(audio).toHaveAttribute('src', /^blob:/);
});
