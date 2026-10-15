import { deleteDB, openDB } from 'idb';
import type { DBSchema, IDBPDatabase } from 'idb';

export const DB_NAME = 'frances';
export const DB_VERSION = 1;

export interface FrancesDb extends DBSchema {
  keys: {
    key: string;
    value: CryptoKey;
  };
  srs: {
    key: string;
    value: { card_id: string } & Record<string, unknown>;
  };
  review_log: {
    key: number;
    value: { card_id: string } & Record<string, unknown>;
    indexes: { card_id: string };
  };
  attempts: {
    key: string;
    value: {
      id: string;
      card_id: string | null;
      at: string;
    } & Record<string, unknown>;
    indexes: { card_id: string; at: string };
  };
  phoneme_stats: {
    key: string;
    value: {
      phoneme: string;
      ema: number;
      n: number;
      last_at: string;
    } & Record<string, unknown>;
  };
  usage: {
    key: string;
    value: { month: string; seconds: number } & Record<string, unknown>;
  };
  settings: {
    key: string;
    value: unknown;
  };
}

let dbPromise: Promise<IDBPDatabase<FrancesDb>> | null = null;

export function openFrancesDb(): Promise<IDBPDatabase<FrancesDb>> {
  if (dbPromise === null) {
    dbPromise = openDB<FrancesDb>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('keys')) {
          db.createObjectStore('keys');
        }
        if (!db.objectStoreNames.contains('srs')) {
          db.createObjectStore('srs', { keyPath: 'card_id' });
        }
        if (!db.objectStoreNames.contains('review_log')) {
          const reviewLog = db.createObjectStore('review_log', {
            autoIncrement: true,
          });
          reviewLog.createIndex('card_id', 'card_id');
        }
        if (!db.objectStoreNames.contains('attempts')) {
          const attempts = db.createObjectStore('attempts', {
            keyPath: 'id',
          });
          attempts.createIndex('card_id', 'card_id');
          attempts.createIndex('at', 'at');
        }
        if (!db.objectStoreNames.contains('phoneme_stats')) {
          db.createObjectStore('phoneme_stats', { keyPath: 'phoneme' });
        }
        if (!db.objectStoreNames.contains('usage')) {
          db.createObjectStore('usage', { keyPath: 'month' });
        }
        if (!db.objectStoreNames.contains('settings')) {
          db.createObjectStore('settings');
        }
      },
    });
  }
  return dbPromise;
}

export async function closeFrancesDbForTests(): Promise<void> {
  if (dbPromise !== null) {
    const db = await dbPromise;
    db.close();
    dbPromise = null;
  }
  await deleteDB(DB_NAME);
}

export interface SettingsMap {
  remember_key: boolean;
  preferred_voices: string[];
  new_per_day: number;
  last_visit_at: string | null;
}

export const SETTINGS_DEFAULTS: SettingsMap = {
  remember_key: true,
  preferred_voices: [],
  new_per_day: 20,
  last_visit_at: null,
};

export async function getSetting<K extends keyof SettingsMap>(
  key: K,
): Promise<SettingsMap[K]> {
  const db = await openFrancesDb();
  const stored = (await db.get('settings', key)) as SettingsMap[K] | undefined;
  return stored ?? SETTINGS_DEFAULTS[key];
}

export async function setSetting<K extends keyof SettingsMap>(
  key: K,
  value: SettingsMap[K],
): Promise<void> {
  const db = await openFrancesDb();
  await db.put('settings', value, key);
}
