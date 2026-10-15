// @vitest-environment node
import { readFileSync } from 'node:fs';
import { FrbError, b64urlToBytes, checkKey, decryptBlob, deriveEncKey } from './frb1';
import type { BundleManifest, KdfParams } from './frb1';

interface FrbVector {
  passphrase: string;
  salt_b64url: string;
  iterations: number;
  plaintext_b64: string;
  enc_key_hex: string;
  blob_b64: string;
  file_id: string;
}

const vectors = JSON.parse(
  readFileSync(
    new URL('../../../tests/fixtures/frb1_vectors.json', import.meta.url),
    'utf8',
  ),
) as FrbVector[];

const kdf = (v: FrbVector): KdfParams => ({
  name: 'PBKDF2',
  hash: 'SHA-256',
  iterations: v.iterations,
  salt: v.salt_b64url,
});

function toArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.length);
  copy.set(bytes);
  return copy.buffer as ArrayBuffer;
}

function manifestFor(v: FrbVector): BundleManifest {
  return {
    format: 'FRB1',
    kdf: kdf(v),
    check: v.blob_b64,
    index: {
      id: '0'.repeat(32),
      size: 0,
      mime: 'application/gzip',
      sha256: '0'.repeat(64),
    },
    created_at: '2026-10-14T10:17:00.000000Z',
  };
}

test.each(vectors)('decrypts python vector %#', async (v) => {
  const key = await deriveEncKey(v.passphrase, kdf(v));
  const out = await decryptBlob(toArrayBuffer(b64urlToBytes(v.blob_b64)), key);
  expect(Buffer.from(out).toString('base64')).toBe(v.plaintext_b64);
});

test('NFD passphrase derives the same key', async () => {
  expect(vectors[2].passphrase).not.toBe(vectors[3].passphrase);
  const key = await deriveEncKey(vectors[3].passphrase, kdf(vectors[3]));
  const out = await decryptBlob(
    toArrayBuffer(b64urlToBytes(vectors[2].blob_b64)),
    key,
  );
  expect(Buffer.from(out).toString('base64')).toBe(vectors[2].plaintext_b64);
});

test('tampered blob throws auth_failed', async () => {
  const key = await deriveEncKey(vectors[0].passphrase, kdf(vectors[0]));
  const bytes = b64urlToBytes(vectors[0].blob_b64);
  bytes[bytes.length - 1] ^= 1;
  await expect(decryptBlob(toArrayBuffer(bytes), key)).rejects.toMatchObject({
    code: 'auth_failed',
  });
});

test('bad magic throws bad_magic', async () => {
  const key = await deriveEncKey(vectors[0].passphrase, kdf(vectors[0]));
  const bytes = b64urlToBytes(vectors[0].blob_b64);
  bytes[0] = 0x58;
  await expect(decryptBlob(toArrayBuffer(bytes), key)).rejects.toMatchObject({
    code: 'bad_magic',
  });
});

test('derived key is not extractable', async () => {
  const key = await deriveEncKey(vectors[0].passphrase, kdf(vectors[0]));
  expect(key.extractable).toBe(false);
  expect(key.usages).toEqual(['decrypt']);
  expect(key.algorithm).toMatchObject({ name: 'AES-GCM' });
});

test('checkKey true with right key and false with wrong one', async () => {
  const good = await deriveEncKey(vectors[0].passphrase, kdf(vectors[0]));
  const bad = await deriveEncKey(vectors[1].passphrase, kdf(vectors[1]));
  await expect(checkKey(manifestFor(vectors[0]), good)).resolves.toBe(true);
  await expect(checkKey(manifestFor(vectors[0]), bad)).resolves.toBe(false);
});

test('FrbError carries its code', () => {
  expect(new FrbError('auth_failed').code).toBe('auth_failed');
});
