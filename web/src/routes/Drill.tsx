// Pantalla Taladro (Task PRN-05), ruta `/drill/:phoneme`.
//
// Elige el mazo del fonema (`deckFor`: curado primero, si no el automático),
// arma la sesión del día con `buildSession` (barajado determinista del día en
// Bogotá) y la recorre con `PracticeSession`. Al montar lee la estadística
// EMA (antes) y al terminar la vuelve a leer (después) para mostrar
// `/fonema/: antes → después` con un decimal (`es-CO`; 70 → 75,1 con α 0.3).

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { JSX } from 'react';
import { useParams } from 'react-router';
import type { CardOut } from '../contracts/generated';
import { useContent } from '../data/ContentContext';
import { bogotaDay } from '../i18n/dates';
import { buildSession, deckFor, drillSummary } from '../pron/drill';
import { normalizePhoneme } from '../pron/phonemeLabels';
import { getRecognizer } from '../pron/recognizer';
import type { PhonemeStat } from '../pron/stats';
import { loadStats } from '../pron/stats';
import { PracticeSession } from '../ui/pron/PracticeSession';

// Cadenas propias de P06 (R-18): no van a `es.ts`.
export const DRILL_MESSAGES = {
  title: 'Taladro',
  empty: 'No hay taladro para este fonema',
} as const;

const numberFormat = new Intl.NumberFormat('es-CO', {
  maximumFractionDigits: 1,
});

function fmt(value: number | null): string {
  return value === null ? '—' : numberFormat.format(value);
}

export default function Drill(): JSX.Element {
  const params = useParams();
  const { index } = useContent();
  const phoneme = normalizePhoneme(params.phoneme ?? '');
  const deck = useMemo(() => deckFor(phoneme, index), [phoneme, index]);
  const recognizer = useMemo(() => getRecognizer(index.speech), [index.speech]);
  const day = bogotaDay(new Date());

  const session = useMemo<CardOut[]>(
    () => (deck === null ? [] : buildSession(deck, index.cards, day)),
    [deck, index.cards, day],
  );

  const [pos, setPos] = useState(0);
  const [finished, setFinished] = useState(false);
  const [before, setBefore] = useState<PhonemeStat[] | null>(null);
  const [after, setAfter] = useState<PhonemeStat[] | null>(null);

  // Antes: la estadística tal como estaba al montar la pantalla.
  useEffect(() => {
    let cancelled = false;
    loadStats()
      .then((stats) => {
        if (!cancelled) {
          setBefore(stats);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const onNext = useCallback((): void => {
    if (pos + 1 >= session.length) {
      setFinished(true);
      // Después: releer la estadística cuando termina la sesión.
      loadStats()
        .then((stats) => setAfter(stats))
        .catch(() => undefined);
    } else {
      setPos(pos + 1);
    }
  }, [pos, session.length]);

  const summary = finished
    ? drillSummary(before ?? [], after ?? [], phoneme)
    : null;
  const card = finished ? undefined : session[pos];

  return (
    <section>
      <h1>{`${DRILL_MESSAGES.title} /${phoneme}/`}</h1>
      {deck === null || session.length === 0 ? (
        <p>{DRILL_MESSAGES.empty}</p>
      ) : summary !== null ? (
        <p className="drill-summary">
          {`/${phoneme}/: ${fmt(summary.before)} → ${fmt(summary.after)}`}
        </p>
      ) : card !== undefined ? (
        <PracticeSession
          key={card.id}
          card={card}
          recognizer={recognizer}
          onNext={onNext}
        />
      ) : null}
    </section>
  );
}
