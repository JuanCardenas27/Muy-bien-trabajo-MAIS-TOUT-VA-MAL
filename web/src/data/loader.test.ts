// @vitest-environment node
import 'fake-indexeddb/auto';
import { beforeEach } from 'vitest';
import type { ContentIndex } from '../contracts/generated';
import { loadKey } from '../crypto/keystore';
import { closeFrancesDbForTests } from '../db/idb';
import { loadIndex, restoreKey, unlock } from './loader';
import { makeIndex, makeTestBundle, mockFetch } from './testing';

const PASS = 'demo demo demo demo demo demo';

beforeEach(async () => {
  await closeFrancesDbForTests();
});

test('unlock + loadIndex decrypts and validates the index', async () => {
  const index = makeIndex();
  const { manifest, files } = await makeTestBundle({
    passphrase: PASS,
    index,
    iterations: 1000,
  });
  mockFetch(files);
  const key = await unlock(manifest, PASS);
  if (key === null) {
    throw new Error('unlock should succeed with the right passphrase');
  }
  const loaded = await loadIndex(manifest, key, '/data/');
  expect(loaded.schema_version).toBe(1);
  expect(loaded.courses).toEqual(index.courses);
});

test('wrong passphrase returns null and stores nothing', async () => {
  const { manifest, files } = await makeTestBundle({
    passphrase: PASS,
    index: makeIndex(),
    iterations: 1000,
  });
  mockFetch(files);
  await expect(
    unlock(manifest, 'una passphrase equivocada ok'),
  ).resolves.toBeNull();
  await expect(loadKey()).resolves.toBeNull();
});

test('remember false returns key without storing it', async () => {
  const { manifest, files } = await makeTestBundle({
    passphrase: PASS,
    index: makeIndex(),
    iterations: 1000,
  });
  mockFetch(files);
  const key = await unlock(manifest, PASS, { remember: false });
  if (key === null) {
    throw new Error('unlock should succeed with the right passphrase');
  }
  expect(await loadKey()).toBeNull();
});

test('unsupported schema_version throws DataError', async () => {
  const raw = makeIndex() as unknown as { schema_version: number };
  raw.schema_version = 2;
  const { manifest, files } = await makeTestBundle({
    passphrase: PASS,
    index: raw as unknown as ContentIndex,
    iterations: 1000,
  });
  mockFetch(files);
  const key = await unlock(manifest, PASS);
  if (key === null) {
    throw new Error('unlock should succeed with the right passphrase');
  }
  await expect(loadIndex(manifest, key, '/data/')).rejects.toThrow(
    'Versión de datos no soportada: recarga la página',
  );
});

test('restoreKey returns stored key valid for manifest', async () => {
  const { manifest, files } = await makeTestBundle({
    passphrase: PASS,
    index: makeIndex(),
    iterations: 1000,
  });
  mockFetch(files);
  await expect(restoreKey(manifest)).resolves.toBeNull();
  const key = await unlock(manifest, PASS);
  if (key === null) {
    throw new Error('unlock should succeed with the right passphrase');
  }
  const restored = await restoreKey(manifest);
  if (restored === null) {
    throw new Error('restoreKey should return the stored key');
  }
  const loaded = await loadIndex(manifest, restored, '/data/');
  expect(loaded.schema_version).toBe(1);
});
