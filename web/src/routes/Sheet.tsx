// Ficha de estudio (Task WEB-07): resumen, vocabulario, gramática y frases
// clave de una publicación. Todo el texto francés va dentro de un elemento
// con `lang="fr"`. El vocabulario enlaza a la tarjeta en `/cards?card=<id>`
// y, si está disponible, incluye el reproductor de audio de WEB-10.

import type { ComponentType, JSX } from 'react';
import { Link, useParams } from 'react-router';
import type { CardOut, StudySheet } from '../contracts/generated';
import { useContent } from '../data/ContentContext';
import { t } from '../i18n/es';

type AudioPlayerProps = {
  card: CardOut;
  field: 'front' | 'example';
  voiceId?: string;
};

type AudioPlayerModule = {
  AudioPlayer?: ComponentType<AudioPlayerProps>;
  default?: ComponentType<AudioPlayerProps>;
};

// WEB-10 (AudioPlayer) es una dependencia apilada que aún puede no estar
// fusionada; se carga de forma opcional para no romper la ficha. Cuando el
// módulo existe, se usa su `AudioPlayer`.
const audioModules = import.meta.glob<AudioPlayerModule>(
  '../ui/AudioPlayer.tsx',
  { eager: true },
) as Record<string, AudioPlayerModule>;

function findAudioPlayer(): ComponentType<AudioPlayerProps> | null {
  for (const mod of Object.values(audioModules)) {
    if (mod.AudioPlayer !== undefined) {
      return mod.AudioPlayer;
    }
    if (mod.default !== undefined) {
      return mod.default;
    }
  }
  return null;
}

const AudioPlayer = findAudioPlayer();

function GrammarSection({ sheet }: { sheet: StudySheet }): JSX.Element {
  return (
    <>
      <h2>{t('sheet.grammar')}</h2>
      <ul>
        {sheet.grammar.map((point, index) => (
          <li key={index}>
            <h3>{point.title}</h3>
            <p>{point.explanation_es}</p>
            <ul>
              {point.examples.map((example, exampleIndex) => (
                <li key={exampleIndex}>
                  <span lang="fr">{example.fr}</span>
                  <span> — {example.es}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </>
  );
}

function PhrasesSection({ sheet }: { sheet: StudySheet }): JSX.Element {
  return (
    <>
      <h2>{t('sheet.phrases')}</h2>
      <ul>
        {sheet.key_phrases.map((phrase, index) => (
          <li key={index}>
            <span lang="fr">{phrase.fr}</span>
            <span> — {phrase.es}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function VocabSection({ sheet }: { sheet: StudySheet }): JSX.Element {
  const { index } = useContent();
  const cards = sheet.vocab_card_ids
    .map((cardId) => index.cards.find((card) => card.id === cardId))
    .filter((card): card is CardOut => card !== undefined);

  return (
    <>
      <h2>{t('sheet.vocab')}</h2>
      <ul>
        {cards.map((card) => (
          <li key={card.id}>
            <Link lang="fr" to={`/cards?card=${card.id}`}>
              {card.front_fr}
            </Link>
            {AudioPlayer !== null && <AudioPlayer card={card} field="front" />}
          </li>
        ))}
      </ul>
    </>
  );
}

export default function Sheet(): JSX.Element {
  const { index } = useContent();
  const { id } = useParams();
  const item = index.items.find((candidate) => candidate.id === id);
  const sheet = index.sheets.find((candidate) => candidate.item_id === id);

  if (item === undefined || sheet === undefined) {
    return <p>{t('sheet.none')}</p>;
  }

  const title = item.title ?? t('item.untitled');

  return (
    <article>
      <h1>{t('sheet.title', { title })}</h1>
      <h2>{t('sheet.summary')}</h2>
      <p>{sheet.summary_es}</p>
      <VocabSection sheet={sheet} />
      <GrammarSection sheet={sheet} />
      <PhrasesSection sheet={sheet} />
    </article>
  );
}
