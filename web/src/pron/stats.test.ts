import type { PronResult } from '../contracts/generated';
import { SEED_WEAK, updateStats, weakPhonemes } from './stats';
import type { PhonemeStat } from './stats';

function result(at: string, phonemes: [string, number][]): PronResult {
  return {
    id: at,
    at,
    card_id: null,
    duration_ms: 0,
    recognized_text: '',
    reference_text: '',
    scores: { pron: 0, accuracy: 0, fluency: 0, completeness: 0 },
    words: [
      {
        word: 'w',
        accuracy: 0,
        error_type: 'None',
        phonemes: phonemes.map(([phoneme, accuracy]) => ({
          phoneme,
          accuracy,
        })),
      },
    ],
  };
}

test('ema first observation then alpha 0.3', () => {
  let s = updateStats([], result('2026-10-14T21:00:00.000000Z', [['ʁ', 60]]));
  expect(s).toEqual([
    { phoneme: 'ʁ', ema: 60, n: 1, last_at: '2026-10-14T21:00:00.000000Z' },
  ]);
  s = updateStats(s, result('2026-10-14T21:01:00.000000Z', [['ʁ', 80]]));
  expect(s[0].ema).toBeCloseTo(66, 10);
  expect(s[0].n).toBe(2);
  expect(updateStats(s, result('x', [['ʁ', 80]]), 0.5)[0].ema).toBeCloseTo(
    73,
    10,
  );
});

test('phoneme repeated in one attempt is averaged before ema', () => {
  expect(
    updateStats(
      [],
      result('t', [
        ['e', 50],
        ['e', 70],
      ]),
    )[0],
  ).toMatchObject({ phoneme: 'e', ema: 60, n: 1 });
});

test('weak requires n >= 3 and ema < 80 sorted ascending', () => {
  const st = (phoneme: string, ema: number, n: number): PhonemeStat => ({
    phoneme,
    ema,
    n,
    last_at: '',
  });
  expect(
    weakPhonemes(
      [st('ɔ̃', 70, 3), st('y', 50, 2), st('ɛ̃', 65, 4), st('u', 80, 9)],
      [],
      5,
    ),
  ).toEqual(['ɛ̃', 'ɔ̃']);
});

test('weak fills with seed in order without repeats', () => {
  expect(
    weakPhonemes([{ phoneme: 'ʁ', ema: 55, n: 3, last_at: '' }], SEED_WEAK, 3),
  ).toEqual(['ʁ', 'ɑ̃', 'e']);
  expect(weakPhonemes([], SEED_WEAK, 2)).toEqual(['ɑ̃', 'e']);
});
