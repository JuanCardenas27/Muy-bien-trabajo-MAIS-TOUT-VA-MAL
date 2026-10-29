// Detalle de una publicación con PDF (Task WEB-13): Classroom → ficha del
// demo → visor pdf.js en la página 1.

import { expect, test } from '@playwright/test';
import { unlockDemo } from './helpers';

test('open item with pdf shows page 1', async ({ page }) => {
  await unlockDemo(page);
  await page.getByRole('link', { name: 'Classroom', exact: true }).click();
  await page
    .getByRole('link', { name: 'Leçon 1 — Les salutations' })
    .click();
  await expect(
    page.getByRole('img', { name: /^Página 1 de \d+$/ }),
  ).toBeVisible();
});
