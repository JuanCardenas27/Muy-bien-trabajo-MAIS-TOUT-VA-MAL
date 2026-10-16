// Ayudas solo para tests (Task WEB-03): índice mínimo válido, tarjetas,
// bundle FRB1 cifrado con WebCrypto igual que Python, fetch mockeado y
// proveedor de contenido sin cripto real para los tests de UI.

import { vi } from 'vitest';
import type { ReactNode } from 'react';
import type {
  BundleManifest,
  CardOut,
  ContentIndex,
  FileRef,
  KdfParams,
  VoiceOut,
} from '../contracts/generated';
import type { LockStatus } from '../ui/layout/lockStatus';
import { ContentContextProvider } from './ContentContext';
import type { ContentContextValue } from './ContentContext';
import { sha256Hex } from './loader';

const utf8 = new TextEncoder();

function toArrayBuffer(data: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(data.length);
  copy.set(data);
  return copy.buffer;
}

function b64urlEncode(data: Uint8Array): string {
  let bin = '';
  for (const byte of data) {
    bin += String.fromCharCode(byte);
  }
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function readStream(
  stream: ReadableStream<Uint8Array>,
): Promise<Uint8Array> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    if (value !== undefined) {
      chunks.push(value);
      total += value.length;
    }
  }
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

async function gzipBytes(data: Uint8Array): Promise<Uint8Array> {
  const pipe = new CompressionStream('gzip');
  const writer = pipe.writable.getWriter();
  const owned = new Uint8Array(data.length);
  owned.set(data);
  await writer.write(owned);
  await writer.close();
  return readStream(pipe.readable);
}

interface TestKeys {
  enc: CryptoKey;
  nonce: CryptoKey;
}

// Deriva (enc, nonce) igual que `frances.bundle.frb1`: PBKDF2 con la
// passphrase en NFC y HKDF con `info` "FRB1 enc" / "FRB1 nonce".
async function deriveTestKeys(
  passphrase: string,
  salt: Uint8Array<ArrayBuffer>,
  iterations: number,
): Promise<TestKeys> {
  const base = await crypto.subtle.importKey(
    'raw',
    utf8.encode(passphrase.normalize('NFC')),
    'PBKDF2',
    false,
    ['deriveBits'],
  );
  const master = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', hash: 'SHA-256', salt, iterations },
    base,
    256,
  );
  const hkdf = await crypto.subtle.importKey('raw', master, 'HKDF', false, [
    'deriveBits',
  ]);
  const encBits = await crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: new Uint8Array(0),
      info: utf8.encode('FRB1 enc'),
    },
    hkdf,
    256,
  );
  const nonceBits = await crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: new Uint8Array(0),
      info: utf8.encode('FRB1 nonce'),
    },
    hkdf,
    256,
  );
  const enc = await crypto.subtle.importKey('raw', encBits, 'AES-GCM', false, [
    'encrypt',
  ]);
  const nonce = await crypto.subtle.importKey(
    'raw',
    nonceBits,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  return { enc, nonce };
}

// Cifra con nonce determinista igual que Python:
// `FRB1 || hmac(nonce_key, sha256(pt))[:12] || AES-GCM(enc, pt, "FRB1")`.
async function encryptTest(
  plaintext: Uint8Array,
  keys: TestKeys,
): Promise<Uint8Array> {
  const pt = toArrayBuffer(plaintext);
  const digest = await crypto.subtle.digest('SHA-256', pt);
  const sig = await crypto.subtle.sign('HMAC', keys.nonce, digest);
  const nonce = new Uint8Array(sig.slice(0, 12));
  const ct = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce, additionalData: utf8.encode('FRB1') },
    keys.enc,
    pt,
  );
  const out = new Uint8Array(4 + 12 + ct.byteLength);
  out.set([0x46, 0x52, 0x42, 0x31], 0);
  out.set(nonce, 4);
  out.set(new Uint8Array(ct), 16);
  return out;
}

async function shaHex(data: Uint8Array): Promise<string> {
  return sha256Hex(toArrayBuffer(data));
}

async function fileIdTest(blob: Uint8Array): Promise<string> {
  return (await shaHex(blob)).slice(0, 32);
}

const VOICE_DENISE: VoiceOut = {
  id: 'fr-FR-DeniseNeural',
  label: 'Denise',
  age: 'adult',
  gender: 'female',
  accent: 'standard',
};

const VOICE_HENRI: VoiceOut = {
  id: 'fr-FR-HenriNeural',
  label: 'Henri',
  age: 'adult',
  gender: 'male',
  accent: 'standard',
};

const VOICE_ELOISE: VoiceOut = {
  id: 'fr-FR-EloiseNeural',
  label: 'Eloise',
  age: 'child',
  gender: 'female',
  accent: 'standard',
};

// Índice válido mínimo: 1 curso y las voces Denise/Henri/Eloise.
export function makeIndex(partial?: Partial<ContentIndex>): ContentIndex {
  return {
    attachments: [],
    cards: [],
    courses: [{ id: 'c1', name: 'Français A2', section: null }],
    drills: [],
    generated_at: '2026-10-14T10:17:00.000000Z',
    items: [],
    schema_version: 1,
    sheets: [],
    speech: null,
    topics: [],
    voices: [VOICE_DENISE, VOICE_HENRI, VOICE_ELOISE],
    ...partial,
  };
}

export function makeCard(partial?: Partial<CardOut>): CardOut {
  return {
    id: 'c1',
    kind: 'vocab',
    front_fr: 'Bonjour',
    back_es: 'Hola',
    example_fr: null,
    example_es: null,
    notes: null,
    ipa: null,
    phonemes: [],
    tags: [],
    stale: false,
    source_item_ids: [],
    audio: [],
    audio_pending: [],
    ...partial,
  };
}

export interface TestBundleOptions {
  passphrase: string;
  index: ContentIndex;
  files?: Uint8Array[];
  iterations?: number;
}

export interface TestBundle {
  manifest: BundleManifest;
  files: Map<string, Uint8Array>;
  refs: FileRef[];
}

// Cifra el índice (JSON + gzip) y cada archivo extra con WebCrypto igual
// que FRB1; `refs` describe los archivos extra y el mapa `files` sirve
// para `mockFetch` (incluye el blob del índice).
export async function makeTestBundle(
  opts: TestBundleOptions,
): Promise<TestBundle> {
  const iterations = opts.iterations ?? 1000;
  const saltBytes = Uint8Array.from({ length: 16 }, (_, i) => i);
  const kdf: KdfParams = {
    name: 'PBKDF2',
    hash: 'SHA-256',
    iterations,
    salt: b64urlEncode(saltBytes),
  };
  const keys = await deriveTestKeys(opts.passphrase, saltBytes, iterations);
  const files = new Map<string, Uint8Array>();
  const indexPlain = await gzipBytes(utf8.encode(JSON.stringify(opts.index)));
  const indexBlob = await encryptTest(indexPlain, keys);
  const indexId = await fileIdTest(indexBlob);
  files.set(indexId, indexBlob);
  const checkBlob = await encryptTest(utf8.encode('FRB1-OK'), keys);
  const manifest: BundleManifest = {
    format: 'FRB1',
    kdf,
    check: b64urlEncode(checkBlob),
    index: {
      id: indexId,
      size: indexPlain.length,
      mime: 'application/gzip',
      sha256: await shaHex(indexPlain),
    },
    created_at: '2026-10-14T10:17:00.000000Z',
  };
  const refs: FileRef[] = [];
  for (const file of opts.files ?? []) {
    const blob = await encryptTest(file, keys);
    const id = await fileIdTest(blob);
    files.set(id, blob);
    refs.push({
      id,
      size: file.length,
      mime: 'application/octet-stream',
      sha256: await shaHex(file),
    });
  }
  currentTestManifest = manifest;
  return { manifest, files, refs };
}

let currentTestManifest: BundleManifest | null = null;

function fakeResponse(init: {
  ok: boolean;
  status: number;
  json?: () => Promise<unknown>;
  arrayBuffer?: () => Promise<ArrayBuffer>;
}): Response {
  return init as unknown as Response;
}

// Mockea `fetch`: `bundle.json` responde con el manifiesto del último
// `makeTestBundle` y `d/<id>.bin` con el blob cifrado correspondiente.
export function mockFetch(files: Map<string, Uint8Array>): void {
  vi.stubGlobal('fetch', (input: string | URL | Request): Promise<Response> => {
    const url = String(input);
    if (url.endsWith('bundle.json')) {
      if (currentTestManifest === null) {
        throw new Error(
          'mockFetch: no hay manifiesto (llama a makeTestBundle primero)',
        );
      }
      const manifest = currentTestManifest;
      return Promise.resolve(
        fakeResponse({
          ok: true,
          status: 200,
          json: () => Promise.resolve(manifest),
        }),
      );
    }
    const match = url.match(/d\/([0-9a-f]{32})\.bin$/);
    if (match !== null) {
      const bytes = files.get(match[1]);
      if (bytes === undefined) {
        return Promise.resolve(fakeResponse({ ok: false, status: 404 }));
      }
      return Promise.resolve(
        fakeResponse({
          ok: true,
          status: 200,
          arrayBuffer: () => Promise.resolve(toArrayBuffer(bytes)),
        }),
      );
    }
    return Promise.resolve(fakeResponse({ ok: false, status: 404 }));
  });
}

export interface TestContentProps {
  index?: ContentIndex;
  status?: LockStatus;
  unlockWith?: (passphrase: string, remember: boolean) => Promise<boolean>;
  getBlob?: (ref: FileRef) => Promise<Blob>;
  lock?: () => Promise<void>;
  children: ReactNode;
}

// Proveedor para tests de UI: sin cripto real; en `ready` (por defecto)
// `useContent()` funciona, en otro estado lanza.
export function TestContentProvider({
  index,
  status,
  unlockWith,
  getBlob,
  lock,
  children,
}: TestContentProps): ReactNode {
  const resolvedStatus = status ?? 'ready';
  const resolvedIndex =
    index ?? (resolvedStatus === 'ready' ? makeIndex() : null);
  const value: ContentContextValue = {
    status: resolvedStatus,
    error: null,
    unlockWith: unlockWith ?? (() => Promise.resolve(true)),
    index: resolvedIndex,
    getBlob: getBlob ?? (() => Promise.resolve(new Blob([]))),
    lock: lock ?? (() => Promise.resolve()),
  };
  return (
    <ContentContextProvider value={value}>{children}</ContentContextProvider>
  );
}
