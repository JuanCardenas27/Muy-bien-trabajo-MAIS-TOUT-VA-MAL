// Descifrado FRB1 en el navegador (Task WEB-02).
//
// Espejo TypeScript de `src/frances/bundle/frb1.py` (BND-01):
// blob = b"FRB1" || nonce(12) || AES-GCM(enc_key).encrypt(nonce, plaintext, aad=b"FRB1").
//
// Los tipos `KdfParams`, `FileRef` y `BundleManifest` copian campo por campo
// el plan maestro (§Modelos Python) e idénticos a los que generará FND-02 en
// `web/src/contracts/generated.ts`. Cuando FND-02 se fusione, estas
// interfaces se sustituyen por `import type { ... } from
// '../contracts/generated.js'` sin cambiar las firmas.

export type FrbErrorCode = 'bad_magic' | 'auth_failed';

export class FrbError extends Error {
  readonly code: FrbErrorCode;

  constructor(code: FrbErrorCode, message?: string) {
    super(
      message ??
        (code === 'bad_magic'
          ? 'FRB1: magic inválido'
          : 'FRB1: autenticación fallida'),
    );
    this.name = 'FrbError';
    this.code = code;
  }
}

// Espejo mínimo del contrato FND-02 (plan maestro §Modelos Python).
export interface KdfParams {
  name: 'PBKDF2';
  hash: 'SHA-256';
  iterations: number;
  salt: string;
}

// Espejo mínimo del contrato FND-02 (plan maestro §Modelos Python).
export interface FileRef {
  id: string;
  size: number;
  mime: string;
  sha256: string;
}

// Espejo mínimo del contrato FND-02 (plan maestro §Modelos Python).
export interface BundleManifest {
  format: 'FRB1';
  kdf: KdfParams;
  check: string;
  index: FileRef;
  created_at: string;
}

const MAGIC = new Uint8Array([0x46, 0x52, 0x42, 0x31]); // b"FRB1"
const CHECK_PLAINTEXT = 'FRB1-OK';

const utf8 = new TextEncoder();

// Base64 URL-safe sin padding (acepta entrada sin `=`), como `b64url_decode`.
export function b64urlToBytes(s: string): Uint8Array<ArrayBuffer> {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/');
  const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
  const bin = atob(padded);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) {
    out[i] = bin.charCodeAt(i);
  }
  return out;
}

// Deriva la clave AES-256-GCM no extraíble (usos: ["decrypt"]).
export async function deriveEncKey(
  passphrase: string,
  kdf: KdfParams,
): Promise<CryptoKey> {
  const baseKey = await crypto.subtle.importKey(
    'raw',
    utf8.encode(passphrase.normalize('NFC')),
    'PBKDF2',
    false,
    ['deriveBits'],
  );
  const master = await crypto.subtle.deriveBits(
    {
      name: 'PBKDF2',
      hash: kdf.hash,
      salt: b64urlToBytes(kdf.salt),
      iterations: kdf.iterations,
    },
    baseKey,
    256,
  );
  const hkdfKey = await crypto.subtle.importKey('raw', master, 'HKDF', false, [
    'deriveKey',
  ]);
  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: new Uint8Array(0),
      info: utf8.encode('FRB1 enc'),
    },
    hkdfKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['decrypt'],
  );
}

// Descifra un blob FRB1; lanza FrbError("bad_magic" | "auth_failed").
export async function decryptBlob(
  blob: ArrayBuffer,
  key: CryptoKey,
): Promise<ArrayBuffer> {
  const bytes = new Uint8Array(blob);
  if (
    bytes.length < MAGIC.length ||
    bytes[0] !== MAGIC[0] ||
    bytes[1] !== MAGIC[1] ||
    bytes[2] !== MAGIC[2] ||
    bytes[3] !== MAGIC[3]
  ) {
    throw new FrbError('bad_magic');
  }
  const iv = bytes.slice(MAGIC.length, MAGIC.length + 12);
  const data = bytes.slice(MAGIC.length + 12);
  try {
    return await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv, additionalData: utf8.encode('FRB1') },
      key,
      data,
    );
  } catch (err) {
    if (err instanceof DOMException) {
      throw new FrbError('auth_failed');
    }
    throw err;
  }
}

// Comprueba `manifest.check` con la clave; `false` si la passphrase era otra.
export async function checkKey(
  manifest: BundleManifest,
  key: CryptoKey,
): Promise<boolean> {
  try {
    const raw = b64urlToBytes(manifest.check);
    const out = await decryptBlob(raw.buffer, key);
    return new TextDecoder().decode(out) === CHECK_PLAINTEXT;
  } catch (err) {
    if (err instanceof FrbError) {
      return false;
    }
    throw err;
  }
}
