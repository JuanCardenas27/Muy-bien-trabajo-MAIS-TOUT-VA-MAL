import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import type { ContentIndex, ItemOut, TopicOut } from '../contracts/generated';
import { makeIndex, TestContentProvider } from '../data/testing';
import Classroom from './Classroom';

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

function renderClassroom(index: ContentIndex) {
  return render(
    <TestContentProvider index={index}>
      <MemoryRouter>
        <Classroom />
      </MemoryRouter>
    </TestContentProvider>,
  );
}

test('groups items by topic with Sin tema last', () => {
  const topicA: TopicOut = { id: 't1', course_id: 'c1', name: 'Lecciones' };
  renderClassroom(
    makeIndex({
      topics: [topicA],
      items: [
        makeItem({ id: 'mt_1', title: 'Leçon 1', topic_id: 't1' }),
        makeItem({ id: 'mt_2', title: 'Annonce' }),
      ],
    }),
  );
  expect(
    screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent),
  ).toEqual(['Lecciones', 'Sin tema']);
});

test('kind filter shows only announcements', async () => {
  renderClassroom(
    makeIndex({
      items: [
        makeItem({ id: 'cw_1', title: 'Devoir 1', kind: 'coursework' }),
        makeItem({ id: 'an_1', title: 'Annonce', kind: 'announcement' }),
      ],
    }),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Anuncios' }));
  expect(
    screen
      .getByRole('button', { name: 'Anuncios' })
      .getAttribute('aria-pressed'),
  ).toBe('true');
  expect(screen.queryByText('Devoir 1')).toBeNull();
  expect(screen.getByText('Annonce')).toBeTruthy();
});
