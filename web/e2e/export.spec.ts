// Exportar el progreso desde Ajustes (Tasks WEB-13 + WEB-11): descarga un
// JSON con el formato del plan maestro.

import { expect, test } from '@playwright/test';
import { unlockDemo } from './helpers';

test('exports progress', async ({ page }) => {
  await unlockDemo(page);
  await page.getByRole('link', { name: 'Ajustes', exact: true }).click();

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Exportar progreso' }).click();
  const download = await downloadPromise;

  expect(download.suggestedFilename()).toMatch(
    /^frances-progreso-\d{4}-\d{2}-\d{2}\.json$/,
  );

  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) {
    chunks.push(chunk as Buffer);
  }
  const data = JSON.parse(Buffer.concat(chunks).toString('utf8')) as {
    format?: string;
  };
  expect(data.format).toBe('frances-progress');
});
