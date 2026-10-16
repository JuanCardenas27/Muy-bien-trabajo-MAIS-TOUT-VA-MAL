import 'fake-indexeddb/auto';
import { beforeEach } from 'vitest';
import { closeFrancesDbForTests, openFrancesDb, setSetting } from '../db/idb';
import { createSrsStore } from './store';

const NOW = new Date('2026-10-14T12:00:00Z');

beforeEach(async () => {
  await closeFrancesDbForTests();
});

test('rating persists and reschedules', async () => {
  const s = createSrsStore(['c1']);
  await s.rate('c1', 3, NOW);
  expect(await s.dueCardIds(NOW, 10)).toEqual([]);
  const rec = await (await openFrancesDb()).get('srs', 'c1');
  expect(new Date(rec!.due as string) > NOW).toBe(true);
  expect(await (await openFrancesDb()).count('review_log')).toBe(1);
});

test('new_per_day limit', async () => {
  await setSetting('new_per_day', 2);
  expect(
    await createSrsStore(['a', 'b', 'c', 'd', 'e']).dueCardIds(NOW, 10),
  ).toEqual(['a', 'b']);
});

test('overdue before new', async () => {
  const db = await openFrancesDb();
  await db.put('srs', {
    card_id: 'b',
    due: '2026-10-13T12:00:00.000Z',
    stability: 1,
    difficulty: 5,
    elapsed_days: 0,
    scheduled_days: 1,
    learning_steps: 0,
    reps: 1,
    lapses: 0,
    state: 2,
  });
  expect(await createSrsStore(['a', 'b']).dueCardIds(NOW, 10)).toEqual([
    'b',
    'a',
  ]);
});
