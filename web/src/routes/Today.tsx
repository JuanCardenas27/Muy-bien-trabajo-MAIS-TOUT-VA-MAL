// Pantalla Hoy (Task WEB-05).
//
// Resumen diario con cuatro bloques: tarjetas para repasar (SRS, WEB-08),
// próximas entregas (coursework con vencimiento en 14 días), publicaciones
// nuevas desde la última visita y un taladro sugerido a partir de las
// debilidades por fonema (PRN-04). Al desmontar guarda `last_visit_at`
// para calcular las novedades de la próxima visita.

import { useEffect, useMemo, useRef, useState } from 'react';
import type { JSX } from 'react';
import { Link } from 'react-router';
import type { ItemOut } from '../contracts/generated';
import { useContent } from '../data/ContentContext';
import { getSetting, setSetting } from '../db/idb';
import { formatShort } from '../i18n/dates';
import { t } from '../i18n/es';
import { loadStats, weakPhonemes } from '../pron/stats';
import { createSrsStore } from '../srs/store';

const SEED_WEAK = ['ɑ̃', 'e', 'ʁ'];
const DAY_MS = 24 * 60 * 60 * 1000;
const DEADLINE_WINDOW_MS = 14 * DAY_MS;
const NEW_WINDOW_MS = 7 * DAY_MS;
const NEW_LIMIT = 10;

export default function Today(props: { now?: Date }): JSX.Element {
  const { index } = useContent();
  const nowRef = useRef<Date>(props.now ?? new Date());
  const now = nowRef.current;

  const [dueCount, setDueCount] = useState(0);
  const [weak, setWeak] = useState<string[]>([]);
  const [lastVisit, setLastVisit] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const activeIds = useMemo(
    () => index.cards.filter((card) => !card.stale).map((card) => card.id),
    [index.cards],
  );

  useEffect(() => {
    const nowIso = now.toISOString();
    let cancelled = false;
    void (async () => {
      const [count, stats, storedLastVisit] = await Promise.all([
        createSrsStore(activeIds).countDue(now),
        loadStats(),
        getSetting('last_visit_at'),
      ]);
      if (cancelled) {
        return;
      }
      setDueCount(count);
      setWeak(weakPhonemes(stats, SEED_WEAK, 1));
      setLastVisit(storedLastVisit);
      setLoaded(true);
    })();
    return () => {
      cancelled = true;
      void setSetting('last_visit_at', nowIso);
    };
  }, [activeIds, now]);

  const deadlines = useMemo<ItemOut[]>(() => {
    const from = now.getTime();
    const to = from + DEADLINE_WINDOW_MS;
    return index.items
      .filter((item) => {
        if (item.kind !== 'coursework' || item.due_at === null) {
          return false;
        }
        const due = new Date(item.due_at).getTime();
        return due >= from && due <= to;
      })
      .sort((a, b) => (a.due_at ?? '').localeCompare(b.due_at ?? ''));
  }, [index.items, now]);

  const newItems = useMemo<ItemOut[]>(() => {
    const threshold =
      lastVisit !== null
        ? new Date(lastVisit).getTime()
        : now.getTime() - NEW_WINDOW_MS;
    return index.items
      .filter((item) => new Date(item.first_seen_at).getTime() > threshold)
      .sort((a, b) => b.first_seen_at.localeCompare(a.first_seen_at))
      .slice(0, NEW_LIMIT);
  }, [index.items, lastVisit, now]);

  const drillPhoneme = weak[0];

  if (!loaded) {
    return <p role="status">{t('app.loading')}</p>;
  }

  return (
    <section>
      <h1>{t('today.title')}</h1>
      {dueCount === 0 && deadlines.length === 0 && newItems.length === 0 && (
        <p>{t('today.empty')}</p>
      )}
      <section>
        <h2>{t('today.due')}</h2>
        <p>{t('today.dueCount', { n: dueCount })}</p>
        {dueCount > 0 && <Link to="/review">{t('today.reviewNow')}</Link>}
      </section>
      <section>
        <h2>{t('today.deadlines')}</h2>
        <ul>
          {deadlines.map((item) => {
            const due = item.due_at;
            return (
              <li key={item.id}>
                <Link to={`/item/${item.id}`}>
                  {item.title ?? t('item.untitled')}
                </Link>{' '}
                <span>{due === null ? '' : formatShort(due)}</span>
              </li>
            );
          })}
        </ul>
      </section>
      <section>
        <h2>{t('today.new')}</h2>
        <ul>
          {newItems.map((item) => (
            <li key={item.id}>
              <Link to={`/item/${item.id}`}>
                {item.title ?? t('item.untitled')}
              </Link>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2>{t('today.drill')}</h2>
        {drillPhoneme !== undefined && (
          <p>
            <Link to={`/drill/${encodeURIComponent(drillPhoneme)}`}>
              {t('today.drillLink', { phoneme: drillPhoneme })}
            </Link>
          </p>
        )}
        <p>{t('today.baseline')}</p>
      </section>
    </section>
  );
}
