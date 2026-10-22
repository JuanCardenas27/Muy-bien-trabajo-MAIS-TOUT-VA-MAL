// Sesión de taladro por fonema débil (Task PRN-05).
//
// `deckFor` elige el mazo del fonema (el curado primero, si no el
// automático). `buildSession` toma hasta `DRILL_SIZE` tarjetas vigentes del
// mazo, barajadas con un PRNG sembrado por el día de Bogotá: la misma
// sesión durante todo el día. `drillSummary` compara la EMA del fonema
// antes y después de la sesión.

import type { CardOut, ContentIndex, DrillDeck } from '../contracts/generated';
import { normalizePhoneme } from './phonemeLabels';
import type { PhonemeStat } from './stats';

export const DRILL_SIZE = 10;

export function deckFor(
  phoneme: string,
  index: ContentIndex,
): DrillDeck | null {
  const key = normalizePhoneme(phoneme);
  const decks = index.drills.filter((d) => normalizePhoneme(d.phoneme) === key);
  return decks.find((d) => d.curated) ?? decks[0] ?? null;
}

// FNV-1a sobre el día como semilla de mulberry32.
function seededRandom(day: string): () => number {
  let h = 2166136261;
  for (const ch of day) {
    h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  }
  return () => {
    h = (h + 0x6d2b79f5) | 0;
    let t = Math.imul(h ^ (h >>> 15), 1 | h);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function buildSession(
  deck: DrillDeck,
  cards: CardOut[],
  day: string,
  size = DRILL_SIZE,
): CardOut[] {
  const byId = new Map(cards.map((c) => [c.id, c]));
  const pool: CardOut[] = [];
  for (const id of deck.card_ids) {
    const card = byId.get(id);
    if (card !== undefined && !card.stale) {
      pool.push(card);
    }
  }
  const rand = seededRandom(day);
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    const tmp = pool[i] as CardOut;
    pool[i] = pool[j] as CardOut;
    pool[j] = tmp;
  }
  return pool.slice(0, size);
}

export function drillSummary(
  before: PhonemeStat[],
  after: PhonemeStat[],
  phoneme: string,
): { before: number | null; after: number | null } {
  const key = normalizePhoneme(phoneme);
  const emaOf = (stats: PhonemeStat[]): number | null =>
    stats.find((s) => s.phoneme === key)?.ema ?? null;
  return { before: emaOf(before), after: emaOf(after) };
}
