// Keystore de la clave FRB1: CryptoKey no extraíble en IndexedDB (Task WEB-02).
//
// La clave vive en el store `keys` (WEB-01) bajo el id `"enc"`. Al ser no
// extraíble, nunca sale de WebCrypto: solo se guarda y se recupera su
// referencia opaca.

import { openFrancesDb } from '../db/idb';

const ENC_KEY_ID = 'enc';

export async function saveKey(key: CryptoKey): Promise<void> {
  const db = await openFrancesDb();
  await db.put('keys', key, ENC_KEY_ID);
}

export async function loadKey(): Promise<CryptoKey | null> {
  const db = await openFrancesDb();
  return (await db.get('keys', ENC_KEY_ID)) ?? null;
}

export async function clearKey(): Promise<void> {
  const db = await openFrancesDb();
  await db.delete('keys', ENC_KEY_ID);
}
