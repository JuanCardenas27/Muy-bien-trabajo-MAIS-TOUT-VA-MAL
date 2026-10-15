import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import type {
  AttachmentOut,
  ContentIndex,
  ItemOut,
} from '../contracts/generated';
import { makeIndex, TestContentProvider } from '../data/testing';
import ItemDetail from './ItemDetail';

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

function makeAttachment(
  partial: Partial<AttachmentOut> & { id: string; item_id: string },
): AttachmentOut {
  return {
    file: null,
    kind: 'drive_file',
    mime_type: null,
    status: 'downloaded',
    title: null,
    url: null,
    view_pdf: null,
    ...partial,
  };
}

function renderDetail(index: ContentIndex, path: string) {
  return render(
    <TestContentProvider index={index}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/item/:id" element={<ItemDetail />} />
        </Routes>
      </MemoryRouter>
    </TestContentProvider>,
  );
}

test('forbidden attachment shows Classroom link', () => {
  const item = makeItem({
    id: 'mt_1',
    title: 'Document protégé',
    alternate_link: 'https://classroom.google.com/c/1/a/2',
    attachment_ids: ['at_1'],
  });
  const att = makeAttachment({
    id: 'at_1',
    item_id: 'mt_1',
    status: 'forbidden',
  });
  renderDetail(makeIndex({ items: [item], attachments: [att] }), '/item/mt_1');
  expect(
    screen.getByText('No se pudo descargar: ábrelo en Classroom'),
  ).toBeTruthy();
  const a = screen.getByRole('link', { name: 'Abrir en Classroom' });
  expect(a.getAttribute('rel')).toBe('noopener noreferrer');
  expect(a.getAttribute('target')).toBe('_blank');
});

test('text urls become safe links', () => {
  const item = makeItem({ id: 'mt_1', text: 'Ver https://ejemplo.org/x' });
  renderDetail(makeIndex({ items: [item] }), '/item/mt_1');
  const link = screen.getByRole('link', {
    name: 'https://ejemplo.org/x',
  });
  expect(link.getAttribute('href')).toBe('https://ejemplo.org/x');
  expect(link.getAttribute('rel')).toBe('noopener noreferrer');
});

test('item text gets lang fr only when text_lang is fr', () => {
  const itemFr = makeItem({
    id: 'mt_fr',
    text: 'Bonjour à tous',
    text_lang: 'fr',
  });
  const itemMx = makeItem({
    id: 'mt_mx',
    text: 'Hola, bonjour',
    text_lang: 'mixed',
  });
  const index = makeIndex({ items: [itemFr, itemMx] });
  const { unmount } = renderDetail(index, '/item/mt_fr');
  expect(
    screen.getByText('Bonjour à tous').closest('[lang]')?.getAttribute('lang'),
  ).toBe('fr');
  unmount();
  renderDetail(index, '/item/mt_mx');
  expect(screen.getByText('Hola, bonjour').closest('[lang]')).toBeNull();
});

test('missing item shows not found message', () => {
  renderDetail(makeIndex(), '/item/mt_missing');
  expect(screen.getByText('Publicación no encontrada')).toBeTruthy();
});
