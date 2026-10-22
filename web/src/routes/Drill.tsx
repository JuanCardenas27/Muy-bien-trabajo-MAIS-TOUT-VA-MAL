// Taladro por fonema débil (Task PRN-05), ruta `/drill/:phoneme`.
//
// Lee las estadísticas al montar (antes), recorre la sesión del día con
// `PracticeSession` («Siguiente» pasa a la próxima tarjeta) y, al terminar
// la última, vuelve a leerlas (después) y muestra `/<fonema>/: antes →
// después`. `PracticeSession` llama a `onFinished` después de guardar, así
// que al pulsar «Siguiente» la estadística ya incluye el último intento.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { JSX } from 'react';
import { useParams } from 'react-router';
import { useContent } from '../data/ContentContext';
import { bogotaDay } from '../i18n/dates';
import { buildSession, deckFor, drillSummary } from '../pron/drill';
import { normalizePhoneme } from '../pron/phonemeLabels';
import { getRecognizer } from '../pron/recognizer';
import { loadStats } from '../pron/stats';
import type { PhonemeStat } from '../pron/stats';
import { PracticeSession } from '../ui/pron/PracticeSession';

// Cadenas propias de P06 (R-18): no van a `es.ts`.
export const DRILL_MESSAGES = {
  title: (phoneme: string): string => `Taladro /${phoneme}/`,
  empty: 'No hay taladro para este fonema',
  progress: (n: number, total: number): string => `Tarjeta ${n} de ${total}`,
  finished: 'Sesión terminada',
  summary: (phoneme: string, before: string, after: string): string =>
    `/${phoneme}/: ${before} → ${after}`,
  noData: '—',
} as const;

const emaFormat = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 });

function formatEma(ema: number | null): string {
  return ema === null ? DRILL_MESSAGES.noData : emaFormat.format(ema);
}

export default function Drill(): JSX.Element {
  const { phoneme: param } = useParams();
  const { index } = useContent();
  const phoneme = normalizePhoneme(param ?? '');

  const session = useMemo(() => {
    const deck = deckFor(phoneme, index);
    return deck === null
      ? []
      : buildSession(deck, index.cards, bogotaDay(new Date()));
  }, [phoneme, index]);
  const recognizer = useMemo(() => getRecognizer(index.speech), [index.speech]);

  const [step, setStep] = useState(0);
  const [summary, setSummary] = useState<string | null>(null);
  const beforeRef = useRef<Promise<PhonemeStat[]> | null>(null);

  useEffect(() => {
    beforeRef.current = loadStats().catch(() => []);
    setStep(0);
    setSummary(null);
  }, [phoneme]);

  const onNext = useCallback((): void => {
    if (step + 1 < session.length) {
      setStep(step + 1);
      return;
    }
    const before = beforeRef.current ?? Promise.resolve([]);
    void Promise.all([before, loadStats().catch(() => [])]).then(([b, a]) => {
      const s = drillSummary(b, a, phoneme);
      setSummary(
        DRILL_MESSAGES.summary(
          phoneme,
          formatEma(s.before),
          formatEma(s.after),
        ),
      );
    });
  }, [step, session.length, phoneme]);

  const card = session[step];

  let body: JSX.Element;
  if (card === undefined) {
    body = <p>{DRILL_MESSAGES.empty}</p>;
  } else if (summary !== null) {
    body = (
      <>
        <p>{DRILL_MESSAGES.finished}</p>
        <p>{summary}</p>
      </>
    );
  } else {
    body = (
      <>
        <p>{DRILL_MESSAGES.progress(step + 1, session.length)}</p>
        <PracticeSession
          key={card.id}
          card={card}
          recognizer={recognizer}
          onNext={onNext}
        />
      </>
    );
  }

  return (
    <section>
      <h1>{DRILL_MESSAGES.title(phoneme)}</h1>
      {body}
    </section>
  );
}
