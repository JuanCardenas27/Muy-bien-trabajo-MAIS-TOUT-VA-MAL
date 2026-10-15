// @vitest-environment node
import 'fake-indexeddb/auto';
import { beforeEach } from 'vitest';
import { closeFrancesDbForTests } from '../db/idb';
import { deriveEncKey } from './frb1';
import { clearKey, loadKey, saveKey } from './keystore';

const KDF = {
  name: 'PBKDF2',
  hash: 'SHA-256',
  iterations: 1000,
  salt: 'AAECAwQFBgcICQoLDA0ODw',
} as const;

beforeEach(async () => {
  await closeFrancesDbForTests();
});

test('saved key stays non-extractable', async () => {
  const key = await deriveEncKey('demo demo demo demo demo demo', { ...KDF });
  expect(await loadKey()).toBeNull();
  await saveKey(key);
  const loaded = await loadKey();
  expect(loaded?.extractable).toBe(false);
  expect(loaded?.usages).toEqual(['decrypt']);
  await clearKey();
  expect(await loadKey()).toBeNull();
});
