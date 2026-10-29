// Tests de la sesión de taladro (Task PRN-05): `deckFor` prefiere el mazo
// curado; `buildSession` excluye `stale`, corta a lo sumo en `DRILL_SIZE` y
// es estable dentro del día; `drillSummary` compara la EMA antes/después.

import { expect, test } from 'vitest';
import type { CardOut, ContentIndex, DrillDeck } from '../contracts/generated';
import { makeCard, makeIndex } from '../data/testing';
import { buildSession, deckFor, drillSummary } from './drill';

type DeckSeed = Pick<DrillDeck, 'id' | 'phoneme' | 'curated'> &
  Partial<Pick<DrillDeck, 'card_ids' | 'title_es'>>;

// indexWith(decks) y deckOf(n, stale) construyen datos sintéticos.
function indexWith(decks: DeckSeed[]): ContentIndex {
  return makeIndex({
    drills: decks.map((d) => ({
      id: d.id,
      phoneme: d.phoneme,
      curated: d.curated,
      title_es: d.title_es ?? '',
      card_ids: d.card_ids ?? [],
    })),
  });
}

function deckOf(
  n: number,
  stale: number,
): { deck: DrillDeck; cards: CardOut[] } {
  const cards = Array.from({ length: n }, (_, i) =>
    makeCard({
      id: `c_${String(i).padStart(3, '0')}`,
      front_fr: `Mot ${i}`,
      stale: i >= n - stale,
    }),
  );
  return {
    deck: {
      id: 'd_test',
      phoneme: 'ɑ̃',
      title_es: 'Taladro ɑ̃',
      curated: false,
      card_ids: cards.map((c) => c.id),
    },
    cards,
  };
}

test('deckFor prefers curated deck', () => {
  const idx = indexWith([
    { id: 'd_auto', phoneme: 'ɑ̃', curated: false },
    { id: 'd_cur', phoneme: 'ɑ̃', curated: true },
  ]);
  expect(deckFor('ɑ̃', idx)?.id).toBe('d_cur');
  expect(deckFor('y', idx)).toBeNull();
  expect(
    deckFor('ʁ', indexWith([{ id: 'd_r', phoneme: 'ʁ', curated: false }]))?.id,
  ).toBe('d_r');
});

test('session is at most 10, excludes stale and is stable per day', () => {
  const { deck, cards } = deckOf(14, 2);
  const a = buildSession(deck, cards, '2026-10-14');
  expect(a).toHaveLength(10);
  expect(a.some((c) => c.stale)).toBe(false);
  expect(buildSession(deck, cards, '2026-10-14').map((c) => c.id)).toEqual(
    a.map((c) => c.id),
  );
  const small = deckOf(4, 0);
  expect(buildSession(small.deck, small.cards, '2026-10-14')).toHaveLength(4);
});

test('summary before and after ema', () => {
  expect(
    drillSummary(
      [{ phoneme: 'ɑ̃', ema: 70, n: 3, last_at: '' }],
      [{ phoneme: 'ɑ̃', ema: 73, n: 4, last_at: '' }],
      'ɑ̃',
    ),
  ).toEqual({ before: 70, after: 73 });
  expect(
    drillSummary([], [{ phoneme: 'ʁ', ema: 60, n: 1, last_at: '' }], 'ʁ'),
  ).toEqual({ before: null, after: 60 });
});
