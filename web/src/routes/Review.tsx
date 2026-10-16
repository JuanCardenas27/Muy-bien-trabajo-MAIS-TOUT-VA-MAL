// Pantalla de repaso FSRS (Task WEB-08).
//
// Toma las tarjetas activas (sin obsoletas), pide al store las que tocan
// hoy y las repasa una a una. La respuesta se muestra con «Mostrar
// respuesta» o la barra espaciadora; con la respuesta visible se puntúa
// con los botones «Otra vez (1)»…«Fácil (4)» o las teclas 1–4.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { JSX } from 'react';
import { useContent } from '../data/ContentContext';
import { t } from '../i18n/es';
import type { EsKey } from '../i18n/es';
import { createSrsStore } from '../srs/store';
import type { Rating } from '../srs/store';
import AudioPlayer from '../ui/AudioPlayer';

const RATING_BUTTONS: { rating: Rating; key: EsKey }[] = [
  { rating: 1, key: 'review.again' },
  { rating: 2, key: 'review.hard' },
  { rating: 3, key: 'review.good' },
  { rating: 4, key: 'review.easy' },
];

export default function Review(): JSX.Element {
  const { index } = useContent();
  const [queue, setQueue] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);

  const cardById = useMemo(() => {
    const map = new Map(index.cards.map((card) => [card.id, card]));
    return map;
  }, [index.cards]);

  const activeIds = useMemo(
    () => index.cards.filter((card) => !card.stale).map((card) => card.id),
    [index.cards],
  );

  const storeRef = useRef(createSrsStore(activeIds));
  storeRef.current = createSrsStore(activeIds);

  useEffect(() => {
    let cancelled = false;
    const store = createSrsStore(activeIds);
    store
      .dueCardIds(new Date(), activeIds.length)
      .then((ids) => {
        if (!cancelled) {
          setQueue(ids);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeIds]);

  const currentId = queue[0];
  const current = currentId !== undefined ? cardById.get(currentId) : undefined;

  const rate = useCallback(
    (rating: Rating): void => {
      if (currentId === undefined) {
        return;
      }
      void storeRef.current.rate(currentId, rating, new Date());
      setQueue((prev) => prev.slice(1));
      setShowAnswer(false);
    },
    [currentId],
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (currentId === undefined) {
        return;
      }
      if (event.key === ' ' || event.key === 'Spacebar') {
        event.preventDefault();
        if (!showAnswer) {
          setShowAnswer(true);
        }
        return;
      }
      if (!showAnswer) {
        return;
      }
      const digit = Number(event.key);
      if (digit >= 1 && digit <= 4) {
        event.preventDefault();
        rate(digit as Rating);
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [currentId, showAnswer, rate]);

  if (!loaded) {
    return <p role="status">{t('app.loading')}</p>;
  }

  return (
    <section>
      <h1>{t('review.title')}</h1>
      {current === undefined ? (
        <p>{t('review.done')}</p>
      ) : (
        <>
          <p>{t('review.left', { n: queue.length })}</p>
          <div className="review-card">
            <p lang="fr">{current.front_fr}</p>
            <AudioPlayer card={current} field="front" />
            {showAnswer ? (
              <>
                {current.back_es !== null && <p>{current.back_es}</p>}
                {current.example_fr !== null && (
                  <p lang="fr">{current.example_fr}</p>
                )}
                <div className="review-ratings">
                  {RATING_BUTTONS.map(({ rating, key }) => (
                    <button
                      key={rating}
                      type="button"
                      onClick={() => rate(rating)}
                    >
                      {`${t(key)} (${rating})`}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <button type="button" onClick={() => setShowAnswer(true)}>
                {t('review.show')}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
