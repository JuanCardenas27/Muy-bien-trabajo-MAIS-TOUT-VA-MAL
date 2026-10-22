// Exportar/importar el progreso local (Task WEB-11).
//
// El formato maestro reúne los 5 stores de progreso de IndexedDB:
// `{ format: "frances-progress", version: 1, exported_at, srs, review_log,
// attempts, phoneme_stats, usage }`. Importar valida todo antes de tocar la
// base y luego reemplaza los 5 stores en una sola transacción.

import { openFrancesDb } from '../db/idb';
import { bogotaDay } from '../i18n/dates';
import { t } from '../i18n/es';

export interface ProgressExport {
  format: 'frances-progress';
  version: 1;
  exported_at: string;
  srs: unknown[];
  review_log: unknown[];
  attempts: unknown[];
  phoneme_stats: unknown[];
  usage: unknown[];
}

export class ProgressImportError extends Error {
  constructor() {
    super(t('settings.importInvalid'));
    this.name = 'ProgressImportError';
  }
}

const STORES = [
  'srs',
  'review_log',
  'attempts',
  'phoneme_stats',
  'usage',
] as const;

type ProgressStore = (typeof STORES)[number];

// Campo de clave (o índice) que cada fila debe traer como string.
const REQUIRED_KEY: Record<ProgressStore, string> = {
  srs: 'card_id',
  review_log: 'card_id',
  attempts: 'id',
  phoneme_stats: 'phoneme',
  usage: 'month',
};

type Row = Record<string, unknown>;

function isRow(value: unknown): value is Row {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function validate(data: unknown): Record<ProgressStore, Row[]> {
  if (
    !isRow(data) ||
    data['format'] !== 'frances-progress' ||
    data['version'] !== 1 ||
    typeof data['exported_at'] !== 'string'
  ) {
    throw new ProgressImportError();
  }
  const out = {} as Record<ProgressStore, Row[]>;
  for (const store of STORES) {
    const rows = data[store];
    if (!Array.isArray(rows)) {
      throw new ProgressImportError();
    }
    const field = REQUIRED_KEY[store];
    for (const row of rows) {
      if (!isRow(row) || typeof row[field] !== 'string') {
        throw new ProgressImportError();
      }
    }
    out[store] = rows as Row[];
  }
  return out;
}

export async function exportProgress(
  now: Date = new Date(),
): Promise<ProgressExport> {
  const db = await openFrancesDb();
  const tx = db.transaction([...STORES], 'readonly');
  const [srs, reviewLog, attempts, phonemeStats, usage] = await Promise.all([
    tx.objectStore('srs').getAll(),
    tx.objectStore('review_log').getAll(),
    tx.objectStore('attempts').getAll(),
    tx.objectStore('phoneme_stats').getAll(),
    tx.objectStore('usage').getAll(),
  ]);
  await tx.done;
  return {
    format: 'frances-progress',
    version: 1,
    exported_at: now.toISOString(),
    srs,
    review_log: reviewLog,
    attempts,
    phoneme_stats: phonemeStats,
    usage,
  };
}

export async function importProgress(data: unknown): Promise<void> {
  const rows = validate(data);
  const db = await openFrancesDb();
  const tx = db.transaction([...STORES], 'readwrite');
  const srs = tx.objectStore('srs');
  const reviewLog = tx.objectStore('review_log');
  const attempts = tx.objectStore('attempts');
  const phonemeStats = tx.objectStore('phoneme_stats');
  const usage = tx.objectStore('usage');
  const writes: Promise<unknown>[] = [
    srs.clear(),
    reviewLog.clear(),
    attempts.clear(),
    phonemeStats.clear(),
    usage.clear(),
  ];
  for (const row of rows.srs) {
    writes.push(srs.put(row as { card_id: string }));
  }
  for (const row of rows.review_log) {
    writes.push(reviewLog.add(row as { card_id: string }));
  }
  for (const row of rows.attempts) {
    writes.push(
      attempts.put(row as { id: string; card_id: string | null; at: string }),
    );
  }
  for (const row of rows.phoneme_stats) {
    writes.push(
      phonemeStats.put(
        row as { phoneme: string; ema: number; n: number; last_at: string },
      ),
    );
  }
  for (const row of rows.usage) {
    writes.push(usage.put(row as { month: string; seconds: number }));
  }
  await Promise.all([...writes, tx.done]);
}

export function progressFileName(now: Date): string {
  return `frances-progreso-${bogotaDay(now)}.json`;
}
