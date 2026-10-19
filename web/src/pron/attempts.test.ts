import 'fake-indexeddb/auto';
import { beforeEach } from 'vitest';
import type { PronResult } from '../contracts/generated';
import { closeFrancesDbForTests } from '../db/idb';
import { listAttempts, saveAttempt } from './attempts';
import { loadStats, saveStats } from './stats';

function attempt(id: string, cardId: string | null, at: string): PronResult {
  return {
    id,
    at,
    card_id: cardId,
    duration_ms: 0,
    recognized_text: '',
    reference_text: '',
    scores: { pron: 0, accuracy: 0, fluency: 0, completeness: 0 },
    words: [],
  };
}

const r1 = attempt('a1', 'c_a', '2026-10-14T20:00:00.000000Z');
const r2 = attempt('a2', 'c_b', '2026-10-14T21:00:00.000000Z');

beforeEach(async () => {
  await closeFrancesDbForTests();
});

test('save and list attempts newest first with filters', async () => {
  await saveAttempt(r1);
  await saveAttempt(r2);
  expect((await listAttempts()).map((r) => r.id)).toEqual([r2.id, r1.id]);
  expect((await listAttempts({ cardId: 'c_a' })).map((r) => r.id)).toEqual([
    r1.id,
  ]);
  expect(
    await listAttempts({ since: '2026-10-14T20:30:00.000000Z' }),
  ).toHaveLength(1);
  expect(await listAttempts({ limit: 1 })).toHaveLength(1);
});

test('stats roundtrip through phoneme_stats', async () => {
  const s = [
    { phoneme: 'ɑ̃', ema: 71.5, n: 3, last_at: '2026-10-14T21:00:00.000000Z' },
  ];
  await saveStats(s);
  expect(await loadStats()).toEqual(s);
});
