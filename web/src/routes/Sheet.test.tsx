import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import type {
  CardOut,
  ContentIndex,
  ItemOut,
  StudySheet,
} from '../contracts/generated';
import { makeCard, makeIndex, TestContentProvider } from '../data/testing';
import Sheet from './Sheet';

const ISO = '2026-10-15T04:30:00.000000Z';

function makeItem(partial: Partial<ItemOut> & { id: string }): ItemOut {
  return {
    alternate_link: null,
    attachment_ids: [],
    card_ids: [],
    course_id: 'c1',
    created_at: ISO,
    due_at: null,
    first_seen_at: ISO,
    has_sheet: false,
    kind: 'material',
    text: '',
    text_lang: 'es',
    title: null,
    topic_id: null,
    updated_at: ISO,
    ...partial,
  };
}

function makeSheet(
  partial: Partial<StudySheet> & { item_id: string },
): StudySheet {
  return {
    grammar: [],
    key_phrases: [],
    summary_es: '',
    vocab_card_ids: [],
    ...partial,
  };
}

function renderSheet(index: ContentIndex, path: string) {
  return render(
    <TestContentProvider index={index}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/item/:id/sheet" element={<Sheet />} />
        </Routes>
      </MemoryRouter>
    </TestContentProvider>,
  );
}

test('renders the four sections with french marked', () => {
  const card: CardOut = makeCard({ id: 'c_ecole', front_fr: 'l’école' });
  const item = makeItem({ id: 'mt_1', title: 'Leçon 1', has_sheet: true });
  const sheet = makeSheet({
    item_id: 'mt_1',
    summary_es: 'Resumen de la lección',
    vocab_card_ids: ['c_ecole'],
    grammar: [
      {
        title: 'Le présent',
        explanation_es: 'El presente',
        examples: [{ fr: 'Je vais à l’école.', es: 'Voy a la escuela.' }],
      },
    ],
    key_phrases: [{ fr: 'Bonjour !', es: '¡Hola!' }],
  });
  renderSheet(
    makeIndex({ items: [item], cards: [card], sheets: [sheet] }),
    '/item/mt_1/sheet',
  );
  expect(
    screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent),
  ).toEqual(['Resumen', 'Vocabulario', 'Gramática', 'Frases clave']);
  expect(
    screen
      .getByRole('link', { name: 'l’école' })
      .closest('[lang]')
      ?.getAttribute('lang'),
  ).toBe('fr');
  expect(screen.getByText('Je vais à l’école.').getAttribute('lang')).toBe(
    'fr',
  );
});

test('item without sheet shows message', () => {
  renderSheet(
    makeIndex({ items: [makeItem({ id: 'mt_2' })] }),
    '/item/mt_2/sheet',
  );
  expect(screen.getByText('Esta publicación no tiene ficha')).toBeTruthy();
});
