import { expect, test } from 'vitest';
import type { CardOut, ContentIndex, DrillDeck } from '../contracts/generated';
import { makeCard, makeIndex } from '../data/testing';
import { buildSession, deckFor, drillSummary } from './drill';

// Datos sintéticos: mazos y tarjetas inventados para el test.
function indexWith(
  decks: { id: string; phoneme: string; curated: boolean }[],
): ContentIndex {
  return makeIndex({
    drills: decks.map((d) => ({
      ...d,
      card_ids: [],
      title_es: `Taladro ${d.phoneme}`,
    })),
  });
}

function deckOf(
  n: number,
  stale: number,
): { deck: DrillDeck; cards: CardOut[] } {
  const cards = Array.from({ length: n }, (_, i) =>
    makeCard({
      id: `c_drill${String(i).padStart(2, '0')}`,
      kind: 'drill',
      front_fr: `Phrase ${i}`,
      phonemes: ['ɑ̃'],
      stale: i < stale,
    }),
  );
  const deck: DrillDeck = {
    id: 'd_an',
    phoneme: 'ɑ̃',
    curated: true,
    title_es: 'Nasal ɑ̃',
    card_ids: cards.map((c) => c.id),
  };
  return { deck, cards };
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
