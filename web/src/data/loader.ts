// Carga del bundle FRB1: manifiesto, desbloqueo con passphrase e índice
// descifrado (Task WEB-03).
//
// El manifiesto (`bundle.json`) viaja en claro; el índice y los archivos
// `d/<id>.bin` viajan cifrados con FRB1 (WEB-02) y el índice además va
// comprimido con gzip.

import type { BundleManifest, ContentIndex } from '../contracts/generated';
import { checkKey, decryptBlob, deriveEncKey } from '../crypto/frb1';
import { loadKey, saveKey } from '../crypto/keystore';
import { DATA_MESSAGES, DataError } from './errors';

// URL del Worker de OPS-09 terminada en `/`; vacía en el demo y en e2e,
// donde se usa `BASE_URL + "data/"`.
export const DATA_BASE_URL: string =
  import.meta.env.VITE_DATA_URL || `${import.meta.env.BASE_URL}data/`;

// Descarga el manifiesto sin caché; cualquier fallo de red es DataError.
export async function loadManifest(baseUrl: string): Promise<BundleManifest> {
  let res: Response;
  try {
    res = await fetch(`${baseUrl}bundle.json`, { cache: 'no-cache' });
  } catch {
    throw new DataError(DATA_MESSAGES['data.network']);
  }
  if (!res.ok) {
    throw new DataError(DATA_MESSAGES['data.network']);
  }
  return (await res.json()) as BundleManifest;
}

// Descarga un `d/<id>.bin` (cacheable); cualquier fallo de red es DataError.
async function fetchBin(baseUrl: string, id: string): Promise<ArrayBuffer> {
  let res: Response;
  try {
    res = await fetch(`${baseUrl}d/${id}.bin`, { cache: 'force-cache' });
  } catch {
    throw new DataError(DATA_MESSAGES['data.network']);
  }
  if (!res.ok) {
    throw new DataError(DATA_MESSAGES['data.network']);
  }
  return res.arrayBuffer();
}

// Desbloquea el manifiesto con la passphrase. Devuelve `null` si es
// incorrecta (sin guardar nada); si es correcta guarda la clave salvo
// `opts.remember === false`.
export async function unlock(
  manifest: BundleManifest,
  passphrase: string,
  opts?: { remember?: boolean },
): Promise<CryptoKey | null> {
  const key = await deriveEncKey(passphrase, manifest.kdf);
  if (!(await checkKey(manifest, key))) {
    return null;
  }
  if (opts?.remember !== false) {
    await saveKey(key);
  }
  return key;
}

// Recupera la clave guardada si sigue siendo válida para este manifiesto.
export async function restoreKey(
  manifest: BundleManifest,
): Promise<CryptoKey | null> {
  const key = await loadKey();
  if (key === null) {
    return null;
  }
  if (!(await checkKey(manifest, key))) {
    return null;
  }
  return key;
}

export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

// Verifica el sha256 del plaintext contra el FileRef; desajuste → corrupt.
export async function checkSha256(
  data: ArrayBuffer | Uint8Array,
  expected: string,
): Promise<void> {
  const buf = data instanceof Uint8Array ? data.slice().buffer : data;
  if ((await sha256Hex(buf)) !== expected.toLowerCase()) {
    throw new DataError(DATA_MESSAGES['data.corrupt']);
  }
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

async function gunzipToText(data: Uint8Array): Promise<string> {
  const pipe = new DecompressionStream('gzip');
  const writer = pipe.writable.getWriter();
  const owned = new Uint8Array(data.length);
  owned.set(data);
  await writer.write(owned);
  await writer.close();
  return new TextDecoder().decode(await readStream(pipe.readable));
}

// Descifra el índice del manifiesto, lo descomprime (gzip) y lo valida.
// Clave incorrecta, gzip roto o JSON roto → DataError corrupt;
// `schema_version` distinto de 1 → DataError unsupported.
export async function loadIndex(
  manifest: BundleManifest,
  key: CryptoKey,
  baseUrl: string,
): Promise<ContentIndex> {
  const raw = await fetchBin(baseUrl, manifest.index.id);
  let plain: ArrayBuffer;
  try {
    plain = await decryptBlob(raw, key);
  } catch {
    throw new DataError(DATA_MESSAGES['data.corrupt']);
  }
  await checkSha256(plain, manifest.index.sha256);
  let text: string;
  try {
    text = await gunzipToText(new Uint8Array(plain));
  } catch {
    throw new DataError(DATA_MESSAGES['data.corrupt']);
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text) as unknown;
  } catch {
    throw new DataError(DATA_MESSAGES['data.corrupt']);
  }
  const index = parsed as ContentIndex;
  if (index.schema_version !== 1) {
    throw new DataError(DATA_MESSAGES['data.unsupported']);
  }
  return index;
}
