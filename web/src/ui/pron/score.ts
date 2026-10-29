// Bandas de puntaje y etiquetas de error de la pantalla Práctica (Task PRN-03).
//
// Cadenas propias de P06 (R-18): viven aquí, no en `es.ts` de WEB-01.

import type { ErrorType } from '../../contracts/generated';

export type ScoreBand = 'excelente' | 'bien' | 'mejorable' | 'repetir';

export function scoreBand(score: number): ScoreBand {
  if (score >= 90) {
    return 'excelente';
  }
  if (score >= 75) {
    return 'bien';
  }
  if (score >= 60) {
    return 'mejorable';
  }
  return 'repetir';
}

export const SCORE_LABEL: Record<ScoreBand, string> = {
  excelente: 'Excelente',
  bien: 'Bien',
  mejorable: 'Mejorable',
  repetir: 'A repetir',
};

export const ERROR_LABEL: Record<ErrorType, string | null> = {
  None: null,
  Omission: 'omitida',
  Insertion: 'insertada',
  Mispronunciation: 'mal pronunciada',
  UnexpectedBreak: 'pausa inesperada',
  MissingBreak: 'falta una pausa',
  Monotone: 'monótona',
};

// Puntajes de Azure (0–100, a veces con decimales) como enteros para mostrar.
export function formatScore(score: number): string {
  return String(Math.round(score));
}
