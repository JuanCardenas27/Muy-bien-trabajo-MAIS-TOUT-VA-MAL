import '@testing-library/jest-dom/vitest';
import 'fake-indexeddb/auto';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { beforeEach } from 'vitest';
import type { ContentIndex, ItemOut } from '../contracts/generated';
import { makeCard, makeIndex, TestContentProvider } from '../data/testing';
import { closeFrancesDbForTests, getSetting } from '../db/idb';
import Today from './Today';

const NOW = new Date('2026-10-14T12:00:00Z');

function renderRoute(ui: ReactNode, index: ContentIndex, path = '/') {
  return render(
    <TestContentProvider index={index}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </TestContentProvider>,
  );
}

function makeItem(partial: Partial<ItemOut>): ItemOut {
  return {
    alternate_link: 'https://classroom.google.com/c/demo',
    attachment_ids: [],
    card_ids: [],
    course_id: 'c1',
    created_at: '2026-10-01T10:00:00.000000Z',
    due_at: null,
    first_seen_at: '2026-10-01T10:00:00.000000Z',
    has_sheet: false,
    id: 'item',
    kind: 'material',
    text: '',
    text_lang: 'es',
    title: 'Publicación',
    topic_id: null,
    updated_at: '2026-10-01T10:00:00.000000Z',
    ...partial,
  };
}

const idxWithDueAndNew = makeIndex({
  cards: [makeCard({ id: 'c_uno', front_fr: 'chat' })],
  items: [
    makeItem({
      id: 'cw_uno',
      kind: 'coursework',
      title: 'Devoir 1',
      due_at: '2026-10-15T04:30:00.000000Z',
      first_seen_at: '2026-10-13T10:00:00.000000Z',
    }),
    makeItem({
      id: 'mt_uno',
      kind: 'material',
      title: 'Leçon 1',
      first_seen_at: '2026-10-13T10:00:00.000000Z',
    }),
  ],
});

beforeEach(async () => {
  await closeFrancesDbForTests();
});

test('shows the four blocks', async () => {
  renderRoute(<Today now={NOW} />, idxWithDueAndNew, '/');
  expect(
    (await screen.findAllByRole('heading', { level: 2 })).map(
      (h) => h.textContent,
    ),
  ).toEqual([
    'Para repasar hoy',
    'Próximas entregas',
    'Publicaciones nuevas',
    'Taladro sugerido',
  ]);
  expect(
    screen.getByRole('link', { name: 'Repasar ahora' }).getAttribute('href'),
  ).toBe('/review');
  expect(
    screen.getByRole('link', { name: 'Practicar /ɑ̃/' }).getAttribute('href'),
  ).toBe('/drill/%C9%91%CC%83');
  expect(screen.getByText('Línea base: 94 (14 oct 2026)')).toBeTruthy();
});

test('formats due dates in Bogota', async () => {
  renderRoute(<Today now={NOW} />, idxWithDueAndNew, '/');
  expect(await screen.findByText('14 oct 23:30')).toBeTruthy();
});

test('shows empty state', async () => {
  renderRoute(<Today now={NOW} />, makeIndex(), '/');
  expect(await screen.findByText('Nada pendiente hoy')).toBeTruthy();
});

test('updates last_visit_at on leave', async () => {
  const { unmount } = renderRoute(<Today now={NOW} />, idxWithDueAndNew, '/');
  await screen.findByText('Línea base: 94 (14 oct 2026)');
  unmount();
  await waitFor(async () => {
    expect(await getSetting('last_visit_at')).toBe(NOW.toISOString());
  });
});
