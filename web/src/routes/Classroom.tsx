// Pantalla Classroom (Task WEB-06): publicaciones agrupadas por tema, con
// búsqueda por título y filtro por tipo. UI en español; el título de cada
// publicación no lleva `lang` (el texto en francés se marca en el detalle).

import { useMemo, useState } from 'react';
import type { JSX } from 'react';
import { Link } from 'react-router';
import type { ItemOut } from '../contracts/generated';
import { useContent } from '../data/ContentContext';
import { t } from '../i18n/es';
import type { EsKey } from '../i18n/es';

type KindFilter = 'all' | ItemOut['kind'];

const KIND_FILTERS: { value: KindFilter; key: EsKey }[] = [
  { value: 'all', key: 'kind.all' },
  { value: 'coursework', key: 'kind.coursework' },
  { value: 'material', key: 'kind.material' },
  { value: 'announcement', key: 'kind.announcement' },
];

const NO_TOPIC = '__no_topic__';

interface Group {
  key: string;
  label: string;
  items: ItemOut[];
}

export default function Classroom(): JSX.Element {
  const { index } = useContent();
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<KindFilter>('all');

  const groups = useMemo<Group[]>(() => {
    const needle = query.trim().toLowerCase();
    const visible = index.items.filter((item) => {
      if (kind !== 'all' && item.kind !== kind) {
        return false;
      }
      if (needle !== '') {
        const title = (item.title ?? '').toLowerCase();
        if (!title.includes(needle)) {
          return false;
        }
      }
      return true;
    });
    const topics = [...index.topics].sort((a, b) =>
      a.name.localeCompare(b.name, 'es'),
    );
    const result: Group[] = [];
    for (const topic of topics) {
      const topicItems = visible.filter((item) => item.topic_id === topic.id);
      if (topicItems.length > 0) {
        result.push({ key: topic.id, label: topic.name, items: topicItems });
      }
    }
    const withoutTopic = visible.filter((item) => item.topic_id === null);
    if (withoutTopic.length > 0) {
      result.push({
        key: NO_TOPIC,
        label: t('classroom.noTopic'),
        items: withoutTopic,
      });
    }
    return result;
  }, [index, query, kind]);

  return (
    <section>
      <h1>{t('classroom.title')}</h1>
      <label htmlFor="classroom-search">{t('classroom.search')}</label>
      <input
        id="classroom-search"
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="classroom-filters">
        {KIND_FILTERS.map(({ value, key }) => (
          <button
            key={value}
            type="button"
            aria-pressed={kind === value}
            onClick={() => setKind(value)}
          >
            {t(key)}
          </button>
        ))}
      </div>
      {groups.map((group) => (
        <section key={group.key}>
          <h2>{group.label}</h2>
          <ul>
            {group.items.map((item) => (
              <li key={item.id}>
                <Link to={`/item/${item.id}`}>
                  {item.title ?? t('item.untitled')}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </section>
  );
}
