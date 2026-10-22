import '@testing-library/jest-dom/vitest';
import 'fake-indexeddb/auto';
import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';
import type { ReactElement } from 'react';
import type { PronResult } from '../contracts/generated';
import { closeFrancesDbForTests } from '../db/idb';
import { saveAttempt } from '../pron/attempts';
import { addSeconds } from '../pron/quota';
import { saveStats } from '../pron/stats';
import Progress from './Progress';

// Datos sintéticos: stats ʁ 58/n4, ɑ̃ 71/n3, u 93/n5; 60 intentos;
// usage 2026-10 = 7200; reloj 2026-10-14.
function attempt(i: number): PronResult {
  const minute = String(i % 60).padStart(2, '0');
  const hour = String(10 + Math.floor(i / 60)).padStart(2, '0');
  return {
    id: `a${i}`,
    at: `2026-10-14T${hour}:${minute}:00.000000Z`,
    card_id: `c${i}`,
    duration_ms: 2000,
    recognized_text: 'bonjour',
    reference_text: `phrase ${i}`,
    scores: {
      pron: 60 + (i % 40),
      accuracy: 80,
      fluency: 80,
      completeness: 100,
    },
    words: [],
  };
}

beforeEach(async () => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-14T17:00:00Z'));
  await closeFrancesDbForTests();
  await saveStats([
    { phoneme: 'u', ema: 93, n: 5, last_at: '2026-10-14T12:00:00.000000Z' },
    { phoneme: 'ʁ', ema: 58, n: 4, last_at: '2026-10-14T12:00:00.000000Z' },
    { phoneme: 'ɑ̃', ema: 71, n: 3, last_at: '2026-10-14T12:00:00.000000Z' },
  ]);
  for (let i = 0; i < 60; i++) {
    await saveAttempt(attempt(i));
  }
  await addSeconds('2026-10', 7200);
  render((<Progress />) as ReactElement);
});

afterEach(() => {
  vi.useRealTimers();
});

test('phoneme table sorted by ema with bar and number', async () => {
  const table = await screen.findByRole('table', { name: 'Fonemas' });
  const rows = (await within(table).findAllByRole('row'))
    .slice(1)
    .map((r) => r.textContent);
  expect(rows).toEqual([
    expect.stringContaining('ʁ58'),
    expect.stringContaining('ɑ̃71'),
    expect.stringContaining('u93'),
  ]);
  expect(screen.getAllByRole('meter')[0]).toHaveAttribute(
    'aria-valuenow',
    '58',
  );
});

test('shows baseline 94 with weak phonemes and monthly quota usage', async () => {
  expect(
    await screen.findByText(
      'Línea base: 94 (14 oct 2026) · débiles /ɑ̃/, /e/, /ʁ/',
    ),
  ).toBeInTheDocument();
  expect(
    await screen.findByText('Uso de Azure este mes: 2 h 0 min de 5 h'),
  ).toBeInTheDocument();
});

test('trend chart has table alternative', async () => {
  expect(
    await screen.findByRole('img', { name: 'Tendencia del puntaje global' }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('table', { name: 'Tendencia del puntaje global (tabla)' }),
  ).toBeInTheDocument();
});

test('history limited to 50 attempts', async () => {
  const list = await screen.findByRole('list', { name: 'Historial' });
  const items = within(list).getAllByRole('listitem');
  expect(items).toHaveLength(50);
  expect(
    within(items[0] as HTMLElement).getByText('phrase 59'),
  ).toHaveAttribute('lang', 'fr');
});
