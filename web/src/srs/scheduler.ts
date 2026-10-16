// Programador FSRS (Task WEB-08).
//
// Envuelve `ts-fsrs` con parámetros fijos (sin fuzz, retención 0.9). Dado
// el registro previo (o `undefined` si la tarjeta es nueva) y una nota,
// devuelve el `SrsRecord` actualizado y la entrada de `review_log`, ambos
// con fechas ISO para IndexedDB.

import { createEmptyCard, fsrs, generatorParameters } from 'ts-fsrs';
import type { Card, CardInput, Grade, State } from 'ts-fsrs';
import type { Rating, ReviewLogEntry, SrsRecord } from './types';

const scheduler = fsrs(
  generatorParameters({ enable_fuzz: false, request_retention: 0.9 }),
);

function toIso(date: Date): string {
  return date.toISOString();
}

function toCardInput(record: SrsRecord): CardInput {
  return {
    due: new Date(record.due),
    stability: record.stability,
    difficulty: record.difficulty,
    elapsed_days: record.elapsed_days,
    scheduled_days: record.scheduled_days,
    learning_steps: record.learning_steps,
    reps: record.reps,
    lapses: record.lapses,
    state: record.state as State,
    last_review:
      record.last_review !== undefined ? new Date(record.last_review) : null,
  };
}

function toRecord(cardId: string, card: Card): SrsRecord {
  const record: SrsRecord = {
    card_id: cardId,
    due: toIso(card.due),
    stability: card.stability,
    difficulty: card.difficulty,
    elapsed_days: card.elapsed_days,
    scheduled_days: card.scheduled_days,
    learning_steps: card.learning_steps,
    reps: card.reps,
    lapses: card.lapses,
    state: card.state,
  };
  if (card.last_review !== undefined) {
    record.last_review = toIso(card.last_review);
  }
  return record;
}

export function schedule(
  record: SrsRecord | undefined,
  rating: Rating,
  now: Date,
): { record: SrsRecord; log: ReviewLogEntry } {
  const card: CardInput | Card =
    record !== undefined ? toCardInput(record) : createEmptyCard(now);
  const grade = rating as Grade;
  const { card: next, log } = scheduler.next(card, now, grade);
  const cardId = record?.card_id ?? '';
  return {
    record: toRecord(cardId, next),
    log: {
      card_id: cardId,
      rating: log.rating as Rating,
      state: log.state,
      due: toIso(log.due),
      reviewed_at: toIso(log.review),
      elapsed_days: log.elapsed_days,
      scheduled_days: log.scheduled_days,
    },
  };
}
