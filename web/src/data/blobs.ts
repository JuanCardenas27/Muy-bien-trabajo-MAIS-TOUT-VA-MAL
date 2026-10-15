// Blobs descifrados con caché LRU en memoria (Task WEB-03).
//
// `configureBlobs` fija la clave FRB1 y la URL base que usa `getBlob`;
// cada blob se descifra, se verifica su sha256 y se guarda como `Blob`
// tipado. La caché expulsa los menos usados al superar 50 MB.

import type { FileRef } from '../contracts/generated';
import { decryptBlob } from '../crypto/frb1';
import { DATA_MESSAGES, DataError } from './errors';
import { checkSha256 } from './loader';

export const BLOB_CACHE_MAX_BYTES = 50 * 1024 * 1024;

let currentKey: CryptoKey | null = null;
let currentBaseUrl = '';

const cache = new Map<string, { blob: Blob; bytes: number }>();
let cachedBytes = 0;

export function configureBlobs(key: CryptoKey | null, baseUrl: string): void {
  currentKey = key;
  currentBaseUrl = baseUrl;
}

export function clearBlobCache(): void {
  cache.clear();
  cachedBytes = 0;
}

// Descifra el blob de `ref`, verifica su sha256 y lo devuelve tipado.
// Sin clave configurada, red corrupta, descifrado inválido o sha distinto
// → DataError con el mensaje que corresponde.
export async function getBlob(ref: FileRef): Promise<Blob> {
  const hit = cache.get(ref.id);
  if (hit !== undefined) {
    cache.delete(ref.id);
    cache.set(ref.id, hit);
    return hit.blob;
  }
  if (currentKey === null) {
    throw new DataError(DATA_MESSAGES['data.corrupt']);
  }
  let res: Response;
  try {
    res = await fetch(`${currentBaseUrl}d/${ref.id}.bin`, {
      cache: 'force-cache',
    });
  } catch {
    throw new DataError(DATA_MESSAGES['data.network']);
  }
  if (!res.ok) {
    throw new DataError(DATA_MESSAGES['data.network']);
  }
  const raw = await res.arrayBuffer();
  let plain: ArrayBuffer;
  try {
    plain = await decryptBlob(raw, currentKey);
  } catch {
    throw new DataError(DATA_MESSAGES['data.corrupt']);
  }
  await checkSha256(plain, ref.sha256);
  const blob = new Blob([plain], { type: ref.mime });
  const entry = { blob, bytes: plain.byteLength };
  cache.set(ref.id, entry);
  cachedBytes += entry.bytes;
  while (cachedBytes > BLOB_CACHE_MAX_BYTES && cache.size > 1) {
    const oldest = cache.keys().next();
    if (oldest.done || oldest.value === ref.id) {
      break;
    }
    const evicted = cache.get(oldest.value);
    cache.delete(oldest.value);
    if (evicted !== undefined) {
      cachedBytes -= evicted.bytes;
    }
  }
  return blob;
}
