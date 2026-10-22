// Store de intentos de pronunciación (Task PRN-04).
//
// Los `PronResult` se guardan localmente en el store `attempts` de
// IndexedDB. `listAttempts` devuelve los más recientes primero, recorriendo
// el índice `at` (o `card_id` cuando se filtra por tarjeta) con cursor
// descendente, y aplica `since`/`limit` en memoria.

import type { PronResult } from '../contracts/generated';
import { openFrancesDb } from '../db/idb';
import type { IDBPIndex } from 'idb';
import type { FrancesDb } from '../db/idb';

export interface ListAttemptsOptions {
  cardId?: string;
  since?: string;
  limit?: number;
}

type AttemptsIndex = IDBPIndex<
  FrancesDb,
  ['attempts'],
  'attempts',
  'at' | 'card_id'
>;

async function collect(
  index: AttemptsIndex,
  range: IDBKeyRange | undefined,
): Promise<PronResult[]> {
  const items: PronResult[] = [];
  let cursor = await index.openCursor(range, 'prev');
  while (cursor !== null) {
    items.push(cursor.value as unknown as PronResult);
    cursor = await cursor.continue();
  }
  return items;
}

export async function saveAttempt(result: PronResult): Promise<void> {
  const db = await openFrancesDb();
  await db.put(
    'attempts',
    result as unknown as { id: string; card_id: string | null; at: string },
  );
}

export async function listAttempts(
  opts: ListAttemptsOptions = {},
): Promise<PronResult[]> {
  const db = await openFrancesDb();
  const index = db
    .transaction('attempts')
    .store.index(opts.cardId !== undefined ? 'card_id' : 'at');

  const since = opts.since;
  let items: PronResult[];
  if (opts.cardId !== undefined) {
    items = await collect(index, IDBKeyRange.only(opts.cardId));
    if (since !== undefined) {
      items = items.filter((result) => result.at >= since);
    }
  } else if (since !== undefined) {
    items = await collect(index, IDBKeyRange.lowerBound(since));
  } else {
    items = await collect(index, undefined);
  }

  items.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
  if (opts.limit !== undefined) {
    return items.slice(0, opts.limit);
  }
  return items;
}
