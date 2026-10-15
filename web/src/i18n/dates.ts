export const TZ = 'America/Bogota';

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

function parts(iso: string): {
  day: string;
  month: string;
  year: string;
  hour: string;
  minute: string;
} {
  const found: Record<string, string> = {};
  for (const p of new Intl.DateTimeFormat('es-CO', {
    timeZone: TZ,
    day: 'numeric',
    month: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    hourCycle: 'h23',
  }).formatToParts(new Date(iso))) {
    if (p.type !== 'literal') {
      found[p.type] = p.value;
    }
  }
  const monthIndex = Number(found['month']) - 1;
  return {
    day: found['day'] as string,
    month: MONTHS[monthIndex] as string,
    year: found['year'] as string,
    hour: (found['hour'] as string).padStart(2, '0'),
    minute: (found['minute'] as string).padStart(2, '0'),
  };
}

export function formatShort(iso: string): string {
  const p = parts(iso);
  return `${p.day} ${p.month} ${p.hour}:${p.minute}`;
}

export function formatLong(iso: string): string {
  const p = parts(iso);
  return `${p.day} ${p.month} ${p.year} ${p.hour}:${p.minute}`;
}

export function bogotaDay(d: Date): string {
  const found: Record<string, string> = {};
  for (const p of new Intl.DateTimeFormat('es-CO', {
    timeZone: TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hourCycle: 'h23',
  }).formatToParts(d)) {
    if (p.type !== 'literal') {
      found[p.type] = p.value;
    }
  }
  return `${found['year']}-${found['month']}-${found['day']}`;
}
