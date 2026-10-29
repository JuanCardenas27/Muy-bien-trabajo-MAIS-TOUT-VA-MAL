// Sesión de taladro por fonema débil (Task PRN-05).
//
// `deckFor` elige el mazo del fonema: curado primero, si no el automático.
// `buildSession` arma la sesión del día: tarjetas vigentes del mazo
// barajadas con Fisher–Yates sobre un PRNG determinista sembrado con el día
// (misma sesión todo el día, distinta cada día) y cortada a `DRILL_SIZE`.
// `drillSummary` compara la EMA del fonema antes y después de la sesión.

import type { CardOut, ContentIndex, DrillDeck } from '../contracts/generated';
import type { PhonemeStat } from './stats';

export const DRILL_SIZE = 10;

export function deckFor(
  phoneme: string,
  index: ContentIndex,
): DrillDeck | null {
  const forPhoneme = index.drills.filter((d) => d.phoneme === phoneme);
  return forPhoneme.find((d) => d.curated) ?? forPhoneme[0] ?? null;
}

export function buildSession(
  deck: DrillDeck,
  cards: CardOut[],
  day: string,
  size = DRILL_SIZE,
): CardOut[] {
  const byId = new Map(cards.map((card) => [card.id, card]));
  const candidates: CardOut[] = [];
  for (const id of deck.card_ids) {
    const card = byId.get(id);
    if (card !== undefined && !card.stale) {
      candidates.push(card);
    }
  }

  // Fisher–Yates con PRNG determinista sembrado por el día: FNV-1a para la
  // semilla y mulberry32 para el generador; la misma `day` produce siempre
  // la misma sesión.
  let h = 2166136261;
  for (const ch of day) {
    h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  }
  const rand = (): number => {
    h = (h + 0x6d2b79f5) | 0;
    let t = Math.imul(h ^ (h >>> 15), 1 | h);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  for (let i = candidates.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    [candidates[i], candidates[j]] = [candidates[j], candidates[i]];
  }
  return candidates.slice(0, size);
}

export function drillSummary(
  before: PhonemeStat[],
  after: PhonemeStat[],
  phoneme: string,
): { before: number | null; after: number | null } {
  return {
    before: before.find((stat) => stat.phoneme === phoneme)?.ema ?? null,
    after: after.find((stat) => stat.phoneme === phoneme)?.ema ?? null,
  };
}
