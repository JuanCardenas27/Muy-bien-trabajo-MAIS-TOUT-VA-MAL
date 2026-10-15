// Pantalla Buscador de tarjetas (Task WEB-09).
//
// Lista las tarjetas del índice con búsqueda insensible a acentos y
// mayúsculas (`foldForSearch`), filtro por tipo, por publicación de origen
// y por obsoletas. El detalle (`?card=<id>`, consumido por WEB-07/WEB-13)
// muestra un `AudioPlayer` por voz disponible, las voces pendientes y el
// enlace a la pantalla de práctica.

import { useMemo, useState } from 'react';
import type { JSX } from 'react';
import { Link, useSearchParams } from 'react-router';
import type { CardOut } from '../contracts/generated';
import { useContent } from '../data/ContentContext';
import { t } from '../i18n/es';
import type { EsKey } from '../i18n/es';
import { AudioPlayer, voiceLabel } from '../ui/AudioPlayer';

// Clave de búsqueda: NFD sin marcas, apóstrofo tipográfico normalizado y
// minúsculas. Así «l’école», «l'école» y «ECOLE» coinciden.
export function foldForSearch(s: string): string {
  return s
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .replace(/’/g, "'")
    .toLowerCase();
}

type KindFilter = 'all' | CardOut['kind'];

const KIND_OPTIONS: { value: KindFilter; key: EsKey }[] = [
  { value: 'all', key: 'ckind.all' },
  { value: 'vocab', key: 'ckind.vocab' },
  { value: 'phrase', key: 'ckind.phrase' },
  { value: 'grammar', key: 'ckind.grammar' },
  { value: 'conjugation', key: 'ckind.conjugation' },
  { value: 'drill', key: 'ckind.drill' },
];

function uniqueVoices(
  entries: { field: CardOut['audio'][number]['field']; voice_id: string }[],
): string[] {
  const seen: string[] = [];
  for (const entry of entries) {
    if (entry.field === 'front' && !seen.includes(entry.voice_id)) {
      seen.push(entry.voice_id);
    }
  }
  return seen;
}

function CardDetail({ card }: { card: CardOut }): JSX.Element {
  const { index } = useContent();
  const labelFor = (id: string): string => {
    const voice = index.voices.find((v) => v.id === id);
    return voice === undefined ? id : voiceLabel(voice);
  };
  const available = uniqueVoices(card.audio);
  const pending = uniqueVoices(card.audio_pending);

  return (
    <article>
      <h1 lang="fr">{card.front_fr}</h1>
      <p>{card.back_es}</p>
      {card.example_fr !== null && (
        <p lang="fr">
          {card.example_fr}
          {card.example_es !== null ? ` — ${card.example_es}` : ''}
        </p>
      )}
      {card.ipa !== null && <p lang="fr">{card.ipa}</p>}
      {available.map((id) => (
        <AudioPlayer key={id} card={card} field="front" voiceId={id} />
      ))}
      {pending.map((id) => (
        <p key={id}>{t('cards.pending', { voice: labelFor(id) })}</p>
      ))}
      <p>
        <Link to={`/practice/${card.id}`}>{t('cards.practice')}</Link>
      </p>
    </article>
  );
}

export default function Cards(): JSX.Element {
  const { index } = useContent();
  const [searchParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<KindFilter>('all');
  const [source, setSource] = useState('all');
  const [includeStale, setIncludeStale] = useState(false);

  const titleById = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of index.items) {
      map.set(item.id, item.title ?? t('item.untitled'));
    }
    return map;
  }, [index.items]);

  const visible = useMemo(() => {
    const needle = foldForSearch(query.trim());
    return index.cards.filter((card) => {
      if (!includeStale && card.stale) {
        return false;
      }
      if (kind !== 'all' && card.kind !== kind) {
        return false;
      }
      if (source !== 'all' && !card.source_item_ids.includes(source)) {
        return false;
      }
      if (needle !== '') {
        const haystack = foldForSearch(
          [card.front_fr, card.back_es, card.tags.join(' ')].join(' '),
        );
        if (!haystack.includes(needle)) {
          return false;
        }
      }
      return true;
    });
  }, [index.cards, query, kind, source, includeStale]);

  const detailId = searchParams.get('card');
  if (detailId !== null) {
    const card = index.cards.find((c) => c.id === detailId);
    if (card === undefined) {
      return <p>{t('cards.empty')}</p>;
    }
    return <CardDetail card={card} />;
  }

  return (
    <section>
      <h1>{t('cards.title')}</h1>
      <p>
        <label htmlFor="cards-search">{t('cards.search')}</label>
        <input
          id="cards-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </p>
      <p>
        <label htmlFor="cards-kind">{t('cards.kind')}</label>
        <select
          id="cards-kind"
          value={kind}
          onChange={(event) => setKind(event.target.value as KindFilter)}
        >
          {KIND_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {t(option.key)}
            </option>
          ))}
        </select>
      </p>
      <p>
        <label htmlFor="cards-source">{t('cards.source')}</label>
        <select
          id="cards-source"
          value={source}
          onChange={(event) => setSource(event.target.value)}
        >
          <option value="all">{t('cards.allSources')}</option>
          {index.items.map((item) => (
            <option key={item.id} value={item.id}>
              {titleById.get(item.id)}
            </option>
          ))}
        </select>
      </p>
      <p>
        <label htmlFor="cards-stale">
          <input
            id="cards-stale"
            type="checkbox"
            checked={includeStale}
            onChange={(event) => setIncludeStale(event.target.checked)}
          />{' '}
          {t('cards.stale')}
        </label>
      </p>
      {visible.length === 0 ? (
        <p>{t('cards.empty')}</p>
      ) : (
        <ul>
          {visible.map((card) => (
            <li key={card.id}>
              <Link to={`/cards?card=${card.id}`} lang="fr">
                {card.front_fr}
              </Link>
              {' — '}
              <span>{card.back_es}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}