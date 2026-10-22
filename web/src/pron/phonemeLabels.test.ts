import { PHONEME_LABELS, normalizePhoneme } from './phonemeLabels';

test('table entries normalize to their canonical label', () => {
  for (const [k, v] of Object.entries(PHONEME_LABELS)) {
    expect(normalizePhoneme(k)).toBe(v);
  }
});

test('seed phonemes are fixed points', () => {
  for (const p of ['ɑ̃', 'e', 'ʁ']) {
    expect(normalizePhoneme(p)).toBe(p);
  }
});
