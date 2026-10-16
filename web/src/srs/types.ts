// Tipos del SRS (Task WEB-08).
//
// `Rating` replica los grados de ts-fsrs (1=Otra vez … 4=Fácil; 0=Manual
// no se usa). `SrsRecord` es una `Card` de ts-fsrs con las fechas en ISO
// (apta para IndexedDB) más `card_id`. `ReviewLogEntry` es la fila que se
// guarda en el store `review_log`.

export type Rating = 1 | 2 | 3 | 4;

export interface SrsRecord {
  card_id: string;
  due: string;
  stability: number;
  difficulty: number;
  elapsed_days: number;
  scheduled_days: number;
  learning_steps: number;
  reps: number;
  lapses: number;
  state: number;
  last_review?: string;
}

export interface ReviewLogEntry {
  id?: number;
  card_id: string;
  rating: Rating;
  state: number;
  due: string;
  reviewed_at: string;
  elapsed_days: number;
  scheduled_days: number;
}
