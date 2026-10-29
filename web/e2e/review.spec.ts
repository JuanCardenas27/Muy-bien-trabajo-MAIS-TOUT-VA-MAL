// Repaso FSRS con las tarjetas del demo (Task WEB-13).

import { expect, test } from '@playwright/test';
import { unlockDemo } from './helpers';

test('review three cards', async ({ page }) => {
  await unlockDemo(page);
  await page.getByRole('link', { name: 'Repasar ahora' }).click();

  const left = page.getByText(/^Quedan \d+$/);
  await expect(left).toBeVisible();
  const initial = Number((await left.textContent())?.match(/\d+/)?.[0]);
  expect(initial).toBeGreaterThanOrEqual(3);

  for (let i = 1; i <= 3; i += 1) {
    await page.keyboard.press('Space');
    await expect(page.getByRole('button', { name: 'Bien (3)' })).toBeVisible();
    await page.keyboard.press('3');
    await expect(
      page.getByText(`Quedan ${initial - i}`, { exact: true }),
    ).toBeVisible();
  }
});
