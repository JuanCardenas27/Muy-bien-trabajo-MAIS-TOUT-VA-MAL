import { expect, test } from 'vitest';
import { ERROR_LABEL, SCORE_LABEL, scoreBand } from './score';

test('score bands and labels', () => {
  expect([90, 89.5, 75, 74.9, 60, 59.9].map(scoreBand)).toEqual([
    'excelente',
    'bien',
    'bien',
    'mejorable',
    'mejorable',
    'repetir',
  ]);
  expect(SCORE_LABEL).toEqual({
    excelente: 'Excelente',
    bien: 'Bien',
    mejorable: 'Mejorable',
    repetir: 'A repetir',
  });
  expect([
    ERROR_LABEL.Omission,
    ERROR_LABEL.Mispronunciation,
    ERROR_LABEL.Insertion,
    ERROR_LABEL.None,
  ]).toEqual(['omitida', 'mal pronunciada', 'insertada', null]);
  expect([
    ERROR_LABEL.UnexpectedBreak,
    ERROR_LABEL.MissingBreak,
    ERROR_LABEL.Monotone,
  ]).toEqual(['pausa inesperada', 'falta una pausa', 'monótona']);
});
