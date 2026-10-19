// Estadística EMA por fonema (Task PRN-04).
//
// `updateStats` es pura: agrupa los fonemas de un intento por etiqueta
// canónica (`normalizePhoneme`, R-11), promedia su `accuracy` y aplica la
// media móvil exponencial. `weakPhonemes` ordena por EMA ascendente los
// fonemas con suficiente evidencia (`WEAK_MIN_N`) y por debajo del umbral
// (`WEAK_MAX_EMA`), completando con la semilla de debilidades conocidas.
// La persistencia (`loadStats`/`saveStats`) usa el store `phoneme_stats`.

import type { PronResult } from '../contracts/generated';
import { openFrancesDb } from '../db/idb';
import { normalizePhoneme } from './phonemeLabels';

export interface PhonemeStat {
  phoneme: string;
  ema: number;
  n: number;
  last_at: string;
}

export const SEED_WEAK = ['ɑ̃', 'e', 'ʁ'];
export const WEAK_MIN_N = 3;
export const WEAK_MAX_EMA = 80;
export const BASELINE = { pron: 94, date: '2026-10-14', weak: SEED_WEAK };

export function updateStats(
  stats: PhonemeStat[],
  result: PronResult,
  alpha = 0.3,
): PhonemeStat[] {
  const grouped = new Map<string, { total: number; count: number }>();
  for (const word of result.words) {
    for (const phoneme of word.phonemes) {
      const key = normalizePhoneme(phoneme.phoneme);
      const acc = grouped.get(key) ?? { total: 0, count: 0 };
      acc.total += phoneme.accuracy;
      acc.count += 1;
      grouped.set(key, acc);
    }
  }

  const next = stats.map((stat) => ({ ...stat }));
  for (const [phoneme, { total, count }] of grouped) {
    const x = total / count;
    const existing = next.find((stat) => stat.phoneme === phoneme);
    if (existing === undefined) {
      next.push({ phoneme, ema: x, n: 1, last_at: result.at });
    } else {
      existing.ema = alpha * x + (1 - alpha) * existing.ema;
      existing.n += 1;
      existing.last_at = result.at;
    }
  }
  return next;
}

export function weakPhonemes(
  stats: PhonemeStat[],
  seed: string[],
  n: number,
): string[] {
  const weak = stats
    .filter((stat) => stat.n >= WEAK_MIN_N && stat.ema < WEAK_MAX_EMA)
    .sort((a, b) => a.ema - b.ema)
    .map((stat) => stat.phoneme);
  const out = [...weak];
  for (const phoneme of seed) {
    if (out.length >= n) {
      break;
    }
    if (!out.includes(phoneme)) {
      out.push(phoneme);
    }
  }
  return out.slice(0, n);
}

export async function loadStats(): Promise<PhonemeStat[]> {
  const db = await openFrancesDb();
  return (await db.getAll('phoneme_stats')) as unknown as PhonemeStat[];
}

export async function saveStats(stats: PhonemeStat[]): Promise<void> {
  const db = await openFrancesDb();
  const tx = db.transaction('phoneme_stats', 'readwrite');
  for (const stat of stats) {
    await tx.store.put(
      stat as unknown as {
        phoneme: string;
        ema: number;
        n: number;
        last_at: string;
      },
    );
  }
  await tx.done;
}
