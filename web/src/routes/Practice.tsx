// Pantalla Práctica (Task PRN-03), ruta `/practice/:cardId`.
//
// Toma la tarjeta de `index.cards`, el recognizer de
// `getRecognizer(index.speech)` y el aviso de cuota de
// `quotaState(getUsage(mes en Bogotá))`. El aviso no bloquea la grabación.
// «Siguiente» lleva a la próxima tarjeta vigente del índice.

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { JSX } from 'react';
import { useNavigate, useParams } from 'react-router';
import { useContent } from '../data/ContentContext';
import { getUsage, monthOf, QUOTA_MESSAGES, quotaState } from '../pron/quota';
import { getRecognizer } from '../pron/recognizer';
import { PracticeSession } from '../ui/pron/PracticeSession';

// Cadenas propias de P06 (R-18): no van a `es.ts`.
export const PRACTICE_ROUTE_MESSAGES = {
  title: 'Práctica',
  notFound: 'Tarjeta no encontrada',
} as const;

type QuotaLevel = 'ok' | 'warn' | 'exceeded';

export default function Practice(): JSX.Element {
  const { cardId } = useParams();
  const { index } = useContent();
  const navigate = useNavigate();
  const [quota, setQuota] = useState<QuotaLevel>('ok');

  const card = index.cards.find((c) => c.id === cardId);
  const recognizer = useMemo(() => getRecognizer(index.speech), [index.speech]);

  const refreshQuota = useCallback((): (() => void) => {
    let cancelled = false;
    getUsage(monthOf(new Date()))
      .then((seconds) => {
        if (!cancelled) {
          setQuota(quotaState(seconds));
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => refreshQuota(), [refreshQuota]);

  const nextId = useMemo(() => {
    const active = index.cards.filter((c) => !c.stale);
    if (active.length === 0) {
      return null;
    }
    const at = active.findIndex((c) => c.id === cardId);
    const next = active[(at + 1) % active.length];
    return next !== undefined && next.id !== cardId ? next.id : null;
  }, [index.cards, cardId]);

  const onNext = useCallback((): void => {
    void navigate(
      nextId !== null ? `/practice/${encodeURIComponent(nextId)}` : '/cards',
    );
  }, [navigate, nextId]);

  return (
    <section>
      <h1>{PRACTICE_ROUTE_MESSAGES.title}</h1>
      {quota !== 'ok' && <p className="banner">{QUOTA_MESSAGES[quota]}</p>}
      {card === undefined ? (
        <p>{PRACTICE_ROUTE_MESSAGES.notFound}</p>
      ) : (
        <PracticeSession
          key={card.id}
          card={card}
          recognizer={recognizer}
          onFinished={() => {
            refreshQuota();
          }}
          onNext={onNext}
        />
      )}
    </section>
  );
}
