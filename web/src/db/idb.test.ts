import 'fake-indexeddb/auto';
import { beforeEach } from 'vitest';
import {
  closeFrancesDbForTests,
  getSetting,
  openFrancesDb,
  setSetting,
} from './idb';

beforeEach(async () => {
  await closeFrancesDbForTests();
});

test('idb upgrade creates all stores', async () => {
  const db = await openFrancesDb();
  expect([...db.objectStoreNames].sort()).toEqual([
    'attempts',
    'keys',
    'phoneme_stats',
    'review_log',
    'settings',
    'srs',
    'usage',
  ]);
  expect([...db.transaction('attempts').store.indexNames].sort()).toEqual([
    'at',
    'card_id',
  ]);
});

test('settings default and roundtrip', async () => {
  expect(await getSetting('new_per_day')).toBe(20);
  await setSetting('new_per_day', 5);
  expect(await getSetting('new_per_day')).toBe(5);
});
