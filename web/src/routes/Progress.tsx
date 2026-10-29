// Pantalla Progreso (Task PRN-07).
//
// Muestra el mapa de fonemas (EMA ascendente, con barra `<meter>` y número),
// la línea base con los fonemas débiles conocidos, el uso mensual de Azure,
// la tendencia del puntaje global de los últimos 50 intentos (SVG con tabla
// alternativa visualmente oculta) y el historial de esos intentos.
// Las cadenas viven aquí como constantes exportadas (R-18).

import { useEffect, useState } from 'react';
import type { CSSProperties, JSX } from 'react';
import type { PronResult } from '../contracts/generated';
import { TZ } from '../i18n/dates';
import { listAttempts } from '../pron/attempts';
import { getUsage, monthOf, QUOTA_SECONDS } from '../pron/quota';
import { BASELINE, loadStats } from '../pron/stats';
import type { PhonemeStat } from '../pron/stats';

export const HISTORY_LIMIT = 50;

export const PROGRESS_TEXT = {
  title: 'Progreso',
  loading: 'Cargando…',
  phonemes: 'Fonemas',
  phoneme: 'Fonema',
  score: 'Puntaje',
  noStats: 'Aún no hay puntajes por fonema',
  trend: 'Tendencia del puntaje global',
  trendTable: 'Tendencia del puntaje global (tabla)',
  date: 'Fecha',
  history: 'Historial',
  noHistory: 'Aún no hay intentos',
} as const;

const MONTHS = [
  'ene',
  'feb',
  'mar',
  'abr',
  'may',
  'jun',
  'jul',
  'ago',
  'sep',
  'oct',
  'nov',
  'dic',
] as const;

const VISUALLY_HIDDEN: CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  border: 0,
};

function dateParts(d: Date, timeZone: string): Record<string, string> {
  const found: Record<string, string> = {};
  for (const p of new Intl.DateTimeFormat('es-CO', {
    timeZone,
    day: 'numeric',
    month: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    hourCycle: 'h23',
  }).formatToParts(d)) {
    if (p.type !== 'literal') {
      found[p.type] = p.value;
    }
  }
  return found;
}

function monthName(month: string | undefined): string {
  return MONTHS[Number(month) - 1] ?? '';
}

// `YYYY-MM-DD` (día civil, sin hora) → «14 oct 2026».
export function formatDay(day: string): string {
  const p = dateParts(new Date(`${day}T12:00:00Z`), 'UTC');
  return `${p['day']} ${monthName(p['month'])} ${p['year']}`;
}

// Instante ISO → «14 oct 2026 05:00» en hora de Bogotá.
export function formatAt(iso: string): string {
  const p = dateParts(new Date(iso), TZ);
  const hour = (p['hour'] ?? '').padStart(2, '0');
  const minute = (p['minute'] ?? '').padStart(2, '0');
  return `${p['day']} ${monthName(p['month'])} ${p['year']} ${hour}:${minute}`;
}

export function baselineText(): string {
  const weak = BASELINE.weak.map((ph) => `/${ph}/`).join(', ');
  return `Línea base: ${BASELINE.pron} (${formatDay(BASELINE.date)}) · débiles ${weak}`;
}

function hoursMinutes(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const min = Math.floor((seconds % 3600) / 60);
  return `${h} h ${min} min`;
}

export function usageText(seconds: number): string {
  return `Uso de Azure este mes: ${hoursMinutes(seconds)} de ${QUOTA_SECONDS / 3600} h`;
}

const number = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });

const CHART_W = 300;
const CHART_H = 100;

function trendPoints(attempts: PronResult[]): string {
  if (attempts.length === 0) {
    return '';
  }
  const step = attempts.length > 1 ? CHART_W / (attempts.length - 1) : 0;
  return attempts
    .map((a, i) => {
      const x = attempts.length > 1 ? i * step : CHART_W / 2;
      const y =
        CHART_H - (Math.min(100, Math.max(0, a.scores.pron)) / 100) * CHART_H;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

interface ProgressData {
  stats: PhonemeStat[];
  attempts: PronResult[];
  usage: number;
}

export default function Progress(): JSX.Element {
  const [data, setData] = useState<ProgressData | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [stats, attempts, usage] = await Promise.all([
        loadStats(),
        listAttempts({ limit: HISTORY_LIMIT }),
        getUsage(monthOf(new Date())),
      ]);
      if (!cancelled) {
        setData({
          stats: [...stats].sort((a, b) => a.ema - b.ema),
          attempts,
          usage,
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (data === null) {
    return (
      <section>
        <h1>{PROGRESS_TEXT.title}</h1>
        <p role="status">{PROGRESS_TEXT.loading}</p>
      </section>
    );
  }

  const chronological = [...data.attempts].reverse();

  return (
    <section>
      <h1>{PROGRESS_TEXT.title}</h1>
      <p>{baselineText()}</p>
      <p>{usageText(data.usage)}</p>

      <h2>{PROGRESS_TEXT.phonemes}</h2>
      {data.stats.length === 0 ? (
        <p>{PROGRESS_TEXT.noStats}</p>
      ) : (
        <table aria-label={PROGRESS_TEXT.phonemes}>
          <thead>
            <tr>
              <th scope="col">{PROGRESS_TEXT.phoneme}</th>
              <th scope="col">{PROGRESS_TEXT.score}</th>
            </tr>
          </thead>
          <tbody>
            {data.stats.map((stat) => {
              const value = Math.round(stat.ema);
              return (
                <tr key={stat.phoneme}>
                  <th scope="row">{stat.phoneme}</th>
                  <td>
                    <meter
                      min={0}
                      max={100}
                      value={stat.ema}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={value}
                      aria-label={`/${stat.phoneme}/`}
                    />
                    {number.format(stat.ema)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <h2>{PROGRESS_TEXT.trend}</h2>
      <svg
        role="img"
        aria-label={PROGRESS_TEXT.trend}
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        width="100%"
        height={CHART_H}
        preserveAspectRatio="none"
      >
        <polyline
          points={trendPoints(chronological)}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <table aria-label={PROGRESS_TEXT.trendTable} style={VISUALLY_HIDDEN}>
        <thead>
          <tr>
            <th scope="col">{PROGRESS_TEXT.date}</th>
            <th scope="col">{PROGRESS_TEXT.score}</th>
          </tr>
        </thead>
        <tbody>
          {chronological.map((a) => (
            <tr key={a.id}>
              <td>{formatAt(a.at)}</td>
              <td>{number.format(a.scores.pron)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>{PROGRESS_TEXT.history}</h2>
      {data.attempts.length === 0 ? (
        <p>{PROGRESS_TEXT.noHistory}</p>
      ) : (
        <ul aria-label={PROGRESS_TEXT.history}>
          {data.attempts.map((a) => (
            <li key={a.id}>
              <time dateTime={a.at}>{formatAt(a.at)}</time>{' '}
              <span lang="fr">{a.reference_text}</span>{' '}
              {number.format(a.scores.pron)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
