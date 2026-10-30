// Exportar el progreso desde Ajustes (Tasks WEB-13 + WEB-11): descarga un
// JSON con el formato del plan maestro.
//
// En el Chromium de este entorno las descargas se cancelan al 100 %
// (incluidas las de un blob mínimo), así que además del evento `download` se
// captura el blob que la app entrega al navegador. El nombre y el contenido
// se comprueban igual en los dos navegadores.

import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { unlockDemo } from './helpers';

const FILE_NAME = /^frances-progreso-\d{4}-\d{2}-\d{2}\.json$/;

interface CapturedExport {
  name: string;
  text: string;
}

async function captureDownloads(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    const state: { name: string; blob: Blob | null } = {
      name: '',
      blob: null,
    };
    Object.assign(window, { __francesExport: state });
    const createObjectURL = URL.createObjectURL.bind(URL);
    URL.createObjectURL = (object: Blob | MediaSource): string => {
      if (object instanceof Blob) {
        state.blob = object;
      }
      return createObjectURL(object);
    };
    const click = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function (this: HTMLAnchorElement) {
      if (this.download !== '') {
        state.name = this.download;
      }
      return click.call(this);
    };
  });
}

async function readCaptured(page: import('@playwright/test').Page) {
  return page.evaluate(async () => {
    const state = (
      window as unknown as {
        __francesExport?: { name: string; blob: Blob | null };
      }
    ).__francesExport;
    if (state?.blob === null || state?.blob === undefined) {
      return null;
    }
    return { name: state.name, text: await state.blob.text() };
  }) as Promise<CapturedExport | null>;
}

test('exports progress', async ({ page }, testInfo) => {
  await captureDownloads(page);
  await unlockDemo(page);
  await page.getByRole('link', { name: 'Ajustes', exact: true }).click();

  const downloadPromise = page.waitForEvent('download').catch(() => null);
  await page.getByRole('button', { name: 'Exportar progreso' }).click();
  const download = await downloadPromise;

  let data: { format?: string } | null = null;
  if (download !== null) {
    expect(download.suggestedFilename()).toMatch(FILE_NAME);
    if ((await download.failure()) === null) {
      const saved = testInfo.outputPath('frances-progress.json');
      await download.saveAs(saved);
      data = JSON.parse(readFileSync(saved, 'utf8')) as { format?: string };
    }
  }

  if (data === null) {
    const captured = await readCaptured(page);
    expect(captured).not.toBeNull();
    expect(captured?.name).toMatch(FILE_NAME);
    data = JSON.parse(captured?.text ?? '{}') as { format?: string };
  }
  expect(data.format).toBe('frances-progress');
});
