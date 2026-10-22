// Resumen de puntajes de un intento (Task PRN-03): región «Puntaje global»
// con el número y la banda, más exactitud, fluidez y completitud.

import type { JSX } from 'react';
import type { PronScores } from '../../contracts/generated';
import { SCORE_LABEL, formatScore, scoreBand } from './score';

export const SCORE_SUMMARY_LABELS = {
  region: 'Puntaje global',
  accuracy: 'Exactitud',
  fluency: 'Fluidez',
  completeness: 'Completitud',
} as const;

export function ScoreSummary({ scores }: { scores: PronScores }): JSX.Element {
  const band = scoreBand(scores.pron);
  return (
    <section
      aria-label={SCORE_SUMMARY_LABELS.region}
      className={`pron-score pron-band-${band}`}
    >
      <p>
        <strong className="pron-score-total">{formatScore(scores.pron)}</strong>{' '}
        <span className="pron-score-band">{SCORE_LABEL[band]}</span>
      </p>
      <ul className="pron-score-parts">
        <li>{`${SCORE_SUMMARY_LABELS.accuracy} ${formatScore(scores.accuracy)}`}</li>
        <li>{`${SCORE_SUMMARY_LABELS.fluency} ${formatScore(scores.fluency)}`}</li>
        <li>
          {`${SCORE_SUMMARY_LABELS.completeness} ${formatScore(scores.completeness)}`}
        </li>
      </ul>
    </section>
  );
}

export default ScoreSummary;
