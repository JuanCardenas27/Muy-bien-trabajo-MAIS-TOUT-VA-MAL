import 'fake-indexeddb/auto';
import { beforeEach } from 'vitest';
import { closeFrancesDbForTests, openFrancesDb } from '../db/idb';
import {
  ProgressImportError,
  exportProgress,
  importProgress,
  progressFileName,
} from './exportImport';

const NOW = new Date('2026-10-15T12:00:00Z');

// Datos sintéticos (sin datos reales del Classroom).
async function seedAllStores(): Promise<void> {
  const db = await openFrancesDb();
  await db.put('srs', {
    card_id: 'c1',
    due: '2026-10-16T12:00:00.000Z',
    stability: 1.5,
    difficulty: 5,
    elapsed_days: 0,
    scheduled_days: 1,
    learning_steps: 0,
    reps: 1,
    lapses: 0,
    state: 1,
  });
  await db.add('review_log', {
    card_id: 'c1',
    rating: 3,
    state: 0,
    due: '2026-10-15T12:00:00.000Z',
    reviewed_at: '2026-10-15T12:00:00.000Z',
    elapsed_days: 0,
    scheduled_days: 1,
  });
  await db.add('review_log', {
    card_id: 'c2',
    rating: 1,
    state: 0,
    due: '2026-10-15T12:00:00.000Z',
    reviewed_at: '2026-10-15T12:01:00.000Z',
    elapsed_days: 0,
    scheduled_days: 0,
  });
  await db.put('attempts', {
    id: 'a1b2c3d4',
    card_id: 'c1',
    at: '2026-10-15T12:02:00.000000Z',
    duration_ms: 1500,
    reference_text: 'Bonjour',
    recognized_text: 'Bonjour',
    scores: { pron: 88, accuracy: 90, fluency: 85, completeness: 100 },
    words: [],
  });
  await db.put('phoneme_stats', {
    phoneme: 'ʁ',
    ema: 72.5,
    n: 4,
    last_at: '2026-10-15T12:02:00.000Z',
  });
  await db.put('usage', { month: '2026-10', seconds: 42, pron_seconds: 42 });
}

beforeEach(async () => {
  await closeFrancesDbForTests();
});

test('export then import into clean db roundtrips', async () => {
  await seedAllStores();
  const data = await exportProgress(NOW);
  expect(data.format).toBe('frances-progress');
  expect(data.version).toBe(1);
  expect(data.exported_at).toBe(NOW.toISOString());
  expect(data.review_log).toHaveLength(2);
  await closeFrancesDbForTests();
  await importProgress(JSON.parse(JSON.stringify(data)));
  expect(await exportProgress(NOW)).toEqual(data);
});

test('import replaces existing progress', async () => {
  await seedAllStores();
  const db = await openFrancesDb();
  await db.put('srs', { card_id: 'viejo' });
  await importProgress({
    format: 'frances-progress',
    version: 1,
    exported_at: NOW.toISOString(),
    srs: [{ card_id: 'nuevo' }],
    review_log: [],
    attempts: [],
    phoneme_stats: [],
    usage: [],
  });
  const data = await exportProgress(NOW);
  expect(data.srs).toEqual([{ card_id: 'nuevo' }]);
  expect(data.review_log).toEqual([]);
  expect(data.usage).toEqual([]);
});

test('invalid format shows spanish error', async () => {
  await expect(importProgress({ format: 'otra', version: 1 })).rejects.toThrow(
    'El archivo no es un progreso de Frances válido',
  );
  await expect(importProgress(null)).rejects.toBeInstanceOf(
    ProgressImportError,
  );
});

test('invalid rows are rejected without touching the db', async () => {
  await seedAllStores();
  const before = await exportProgress(NOW);
  await expect(
    importProgress({ ...before, srs: [{ sin_card_id: true }] }),
  ).rejects.toBeInstanceOf(ProgressImportError);
  expect(await exportProgress(NOW)).toEqual(before);
});

test('rows missing fields the screens read are rejected', async () => {
  await seedAllStores();
  const before = await exportProgress(NOW);
  const [attempt] = before.attempts as Record<string, unknown>[];
  await expect(
    importProgress({ ...before, attempts: [{ ...attempt, scores: {} }] }),
  ).rejects.toBeInstanceOf(ProgressImportError);
  await expect(
    importProgress({ ...before, usage: [{ month: '2026-10' }] }),
  ).rejects.toBeInstanceOf(ProgressImportError);
  expect(await exportProgress(NOW)).toEqual(before);
});

test('file name uses Bogota day', () => {
  expect(progressFileName(new Date('2026-10-15T03:00:00Z'))).toBe(
    'frances-progreso-2026-10-14.json',
  );
});
