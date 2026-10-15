import { expect, test } from 'vitest';
import type { R2Bucket } from '@cloudflare/workers-types';
import worker from './index';

const ORIGIN = 'https://juan.github.io';
const ETAG = '"abc123etag"';
const MANIFEST_BODY = new TextEncoder().encode('{"format":"FRB1"}');
const BIN_BODY = new TextEncoder().encode('FRB1-blob-bytes');
const BIN_ID = 'a'.repeat(32);

interface FakeObject {
  body: Uint8Array;
  etag: string;
}

// Fake mínimo de R2Bucket: registra cada `get` y sirve objetos sembrados.
class FakeBucket {
  gets: string[] = [];
  objects = new Map<string, FakeObject>([
    ['site/bundle.json', { body: MANIFEST_BODY, etag: ETAG }],
    [`site/d/${BIN_ID}.bin`, { body: BIN_BODY, etag: '"binetag1"' }],
  ]);

  async get(key: string): Promise<FakeObject | null> {
    this.gets.push(key);
    return this.objects.get(key) ?? null;
  }
}

const fakeBucket = new FakeBucket();
const SITE = fakeBucket as unknown as R2Bucket;

async function call(
  method: string,
  path: string,
  headers: Record<string, string> = {},
): Promise<Response> {
  fakeBucket.gets = [];
  const request = new Request(`https://frances-data.test${path}`, { method, headers });
  return worker.fetch(request, { SITE, ALLOWED_ORIGIN: ORIGIN });
}

test('serves bundle.json uncached with CORS', async () => {
  const r = await call('GET', '/bundle.json');
  expect(r.status).toBe(200);
  expect(r.headers.get('cache-control')).toBe('no-cache');
  expect(r.headers.get('access-control-allow-origin')).toBe(ORIGIN);
});

test('serves bins immutable', async () => {
  const r = await call('GET', `/d/${BIN_ID}.bin`);
  expect(r.status).toBe(200);
  expect(r.headers.get('cache-control')).toContain('immutable');
  expect(r.headers.get('access-control-allow-origin')).toBe(ORIGIN);
});

test.each([
  '/data/state/state.sql',
  '/snapshots/state-2026-10-14.sql',
  '/locks/writer.json',
  '/d/../data/x',
  '/d/xyz.bin',
  '/',
])('404 without touching the bucket: %s', async (p) => {
  expect((await call('GET', p)).status).toBe(404);
  expect(fakeBucket.gets).toEqual([]);
});

test.each(['POST', 'PUT', 'DELETE'])('%s is 405', async (m) => {
  expect((await call(m, '/bundle.json')).status).toBe(405);
});

test('304 on matching etag', async () => {
  expect((await call('GET', '/bundle.json', { 'if-none-match': ETAG })).status).toBe(304);
});

test('HEAD returns headers without body', async () => {
  const r = await call('HEAD', '/bundle.json');
  expect(r.status).toBe(200);
  expect(r.headers.get('etag')).toBe(ETAG);
  expect(r.headers.get('access-control-allow-origin')).toBe(ORIGIN);
  expect(await r.text()).toBe('');
});

test('OPTIONS answers the CORS preflight', async () => {
  const r = await call('OPTIONS', '/bundle.json');
  expect(r.status).toBe(204);
  expect(r.headers.get('access-control-allow-origin')).toBe(ORIGIN);
});
