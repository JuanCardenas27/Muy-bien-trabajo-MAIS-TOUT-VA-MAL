// @vitest-environment node
import 'fake-indexeddb/auto';
import { beforeEach } from 'vitest';
import { closeFrancesDbForTests } from '../db/idb';
import { clearBlobCache, configureBlobs, getBlob } from './blobs';
import { unlock } from './loader';
import { makeIndex, makeTestBundle, mockFetch } from './testing';

const PASS = 'demo demo demo demo demo demo';

beforeEach(async () => {
  await closeFrancesDbForTests();
  clearBlobCache();
  configureBlobs(null, '');
});

test('sha mismatch rejects with corrupt message', async () => {
  const payload = new TextEncoder().encode('hola');
  const { manifest, files, refs } = await makeTestBundle({
    passphrase: PASS,
    index: makeIndex(),
    files: [payload],
    iterations: 1000,
  });
  mockFetch(files);
  const key = await unlock(manifest, PASS);
  if (key === null) {
    throw new Error('unlock should succeed with the right passphrase');
  }
  configureBlobs(key, '/data/');
  const tampered = { ...refs[0], sha256: '0'.repeat(64) };
  await expect(getBlob(tampered)).rejects.toThrow(
    'Archivo dañado o incompleto: recarga la página',
  );
});

test('returns typed blob and caches it', async () => {
  const payload = new TextEncoder().encode('hola');
  const { manifest, files, refs } = await makeTestBundle({
    passphrase: PASS,
    index: makeIndex(),
    files: [payload],
    iterations: 1000,
  });
  mockFetch(files);
  const key = await unlock(manifest, PASS);
  if (key === null) {
    throw new Error('unlock should succeed with the right passphrase');
  }
  configureBlobs(key, '/data/');
  const spy = vi.spyOn(globalThis, 'fetch');
  const first = await getBlob(refs[0]);
  expect(first.type).toBe(refs[0].mime);
  const second = await getBlob(refs[0]);
  expect(await first.text()).toBe('hola');
  expect(await second.text()).toBe('hola');
  expect(spy).toHaveBeenCalledTimes(1);
  spy.mockRestore();
});
