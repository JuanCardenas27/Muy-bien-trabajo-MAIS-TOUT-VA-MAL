import 'fake-indexeddb/auto';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach } from 'vitest';
import { loadKey } from '../crypto/keystore';
import { closeFrancesDbForTests } from '../db/idb';
import { ContentProvider, useContent, useContentState } from './ContentContext';
import { unlock } from './loader';
import { makeIndex, makeTestBundle, mockFetch } from './testing';

const PASS = 'demo demo demo demo demo demo';

beforeEach(async () => {
  await closeFrancesDbForTests();
});

function harness() {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ContentProvider baseUrl="/data/">{children}</ContentProvider>
  );
  return renderHook(
    () => {
      const state = useContentState();
      let lock: (() => Promise<void>) | null = null;
      try {
        lock = useContent().lock;
      } catch {
        lock = null;
      }
      return { state, lock };
    },
    { wrapper },
  );
}

test('restoreKey with stored key goes ready without passphrase', async () => {
  const { manifest, files } = await makeTestBundle({
    passphrase: PASS,
    index: makeIndex(),
    iterations: 1000,
  });
  mockFetch(files);
  const stored = await unlock(manifest, PASS);
  if (stored === null) {
    throw new Error('setup: unlock should succeed');
  }
  const { result } = harness();
  expect(result.current.state.status).toBe('loading');
  await waitFor(() => expect(result.current.state.status).toBe('ready'));
});

test('remember=false keeps key out of IndexedDB', async () => {
  const { manifest, files } = await makeTestBundle({
    passphrase: PASS,
    index: makeIndex(),
    iterations: 1000,
  });
  mockFetch(files);
  const { result } = harness();
  await waitFor(() => expect(result.current.state.status).toBe('locked'));
  let ok = false;
  await act(async () => {
    ok = await result.current.state.unlockWith(PASS, false);
  });
  expect(ok).toBe(true);
  expect(await loadKey()).toBeNull();
  expect(result.current.state.status).toBe('ready');
});

test('lock clears key and returns to locked', async () => {
  const { manifest, files } = await makeTestBundle({
    passphrase: PASS,
    index: makeIndex(),
    iterations: 1000,
  });
  mockFetch(files);
  const { result } = harness();
  await waitFor(() => expect(result.current.state.status).toBe('locked'));
  await act(async () => {
    await result.current.state.unlockWith(PASS, true);
  });
  await waitFor(() => expect(result.current.state.status).toBe('ready'));
  expect(await loadKey()).not.toBeNull();
  const lock = result.current.lock;
  if (lock === null) {
    throw new Error('useContent should provide lock when ready');
  }
  await act(async () => {
    await lock();
  });
  expect(result.current.state.status).toBe('locked');
  expect(await loadKey()).toBeNull();
});
