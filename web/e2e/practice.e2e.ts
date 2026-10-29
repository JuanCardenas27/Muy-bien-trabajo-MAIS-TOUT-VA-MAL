// Práctica con el recognizer falso (Tasks WEB-13 + PRN-02/PRN-03): puntaje
// global, fonemas de la palabra y «Siguiente».

import { expect, test } from '@playwright/test';
import type { AzureJson } from '../src/pron/parse';
import { BONJOUR_JSON, installFakeRecognizer, unlockDemo } from './helpers';

// `c_fc43341b9ea63489` es la tarjeta «Bonjour» del demo (BND-04).
test('practice with fake recognizer shows scores and phonemes', async ({
  page,
}) => {
  await installFakeRecognizer(page);
  await unlockDemo(page, '/practice/c_fc43341b9ea63489');

  await expect(
    page.getByRole('heading', { level: 1, name: 'Práctica' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Grabar', exact: true }).click();

  await expect(
    page.getByRole('region', { name: 'Puntaje global' }),
  ).toContainText(/Excelente|Bien|Mejorable|A repetir/);

  await page.getByRole('button', { name: 'Bonjour', exact: true }).click();
  const words = (BONJOUR_JSON as AzureJson).NBest?.[0]?.Words ?? [];
  const phonemeCount = words[0]?.Phonemes?.length ?? 0;
  expect(phonemeCount).toBeGreaterThan(0);
  await expect(
    page
      .getByRole('list', { name: 'Fonemas de Bonjour' })
      .getByRole('listitem'),
  ).toHaveCount(phonemeCount);

  await expect(
    page.getByRole('button', { name: 'Siguiente', exact: true }),
  ).toBeVisible();
});
