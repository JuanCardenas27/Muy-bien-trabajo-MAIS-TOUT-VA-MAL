// Store SRS sobre IndexedDB (Task WEB-08).
//
// `activeCardIds` fija el universo de tarjetas (ya sin las obsoletas, que
// excluye el llamante). `dueCardIds` devuelve primero las tarjetas vencidas
// por `due` ascendente y luego tarjetas nuevas (sin registro) en el orden
// de `activeCardIds`, hasta el cupo de `new_per_day` menos las introducidas
// hoy, recortado a `limit`. `rate` persiste el registro y el log.

import { bogotaDay } from '../i18n/dates';
import { getSetting, openFrancesDb } from '../db/idb';
import { schedule } from './scheduler';
import type { Rating, ReviewLogEntry, SrsRecord } from './types';

export type { Rating, ReviewLogEntry, SrsRecord } from './types';

export interface SrsStore {
  dueCardIds(now: Date, limit: number): Promise<string[]>;
  rate(cardId: string, rating: Rating, now: Date): Promise<void>;
  countDue(now: Date): Promise<number>;
}

export function createSrsStore(activeCardIds: string[]): SrsStore {
  async function loadRecords(): Promise<Map<string, SrsRecord>> {
    const db = await openFrancesDb();
    const all = (await db.getAll('srs')) as unknown as SrsRecord[];
    const map = new Map<string, SrsRecord>();
    for (const record of all) {
      map.set(record.card_id, record);
    }
    return map;
  }

  async function newTodayCount(now: Date): Promise<number> {
    const db = await openFrancesDb();
    const logs = (await db.getAll('review_log')) as unknown as ReviewLogEntry[];
    const today = bogotaDay(now);
    let count = 0;
    for (const log of logs) {
      if (log.state === 0 && bogotaDay(new Date(log.reviewed_at)) === today) {
        count += 1;
      }
    }
    return count;
  }

  async function dueCardIds(now: Date, limit: number): Promise<string[]> {
    const records = await loadRecords();
    const active = new Set(activeCardIds);

    const overdue: { id: string; due: number }[] = [];
    for (const [id, record] of records) {
      if (!active.has(id)) {
        continue;
      }
      const due = new Date(record.due).getTime();
      if (due <= now.getTime()) {
        overdue.push({ id, due });
      }
    }
    overdue.sort((a, b) => a.due - b.due);

    const perDay = await getSetting('new_per_day');
    const introducedToday = await newTodayCount(now);
    const newQuota = Math.max(0, perDay - introducedToday);
    const fresh: string[] = [];
    for (const id of activeCardIds) {
      if (fresh.length >= newQuota) {
        break;
      }
      if (!records.has(id)) {
        fresh.push(id);
      }
    }

    return [...overdue.map((entry) => entry.id), ...fresh].slice(0, limit);
  }

  async function countDue(now: Date): Promise<number> {
    return (await dueCardIds(now, Number.MAX_SAFE_INTEGER)).length;
  }

  async function rate(
    cardId: string,
    rating: Rating,
    now: Date,
  ): Promise<void> {
    const db = await openFrancesDb();
    const existing = (await db.get('srs', cardId)) as unknown as
      SrsRecord | undefined;
    const { record, log } = schedule(existing, rating, now);
    const stored: SrsRecord = { ...record, card_id: cardId };
    await db.put('srs', stored as unknown as { card_id: string });
    await db.add('review_log', log as unknown as { card_id: string });
  }

  return { dueCardIds, rate, countDue };
}
