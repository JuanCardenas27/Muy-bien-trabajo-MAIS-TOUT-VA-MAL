import '@testing-library/jest-dom/vitest';
import 'fake-indexeddb/auto';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import type { ContentIndex } from '../contracts/generated';
import { makeCard, makeIndex, TestContentProvider } from '../data/testing';
import Cards from './Cards';

function renderRoute(ui: ReactNode, index: ContentIndex, path: string) {
  return render(
    <TestContentProvider index={index}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </TestContentProvider>,
  );
}

const idx = makeIndex({
  cards: [
    makeCard({
      id: 'c_ecole',
      front_fr: 'l’école',
      back_es: 'la escuela',
      tags: ['école'],
      audio_pending: [{ field: 'front', voice_id: 'fr-FR-EloiseNeural' }],
    }),
    makeCard({
      id: 'c_chien',
      front_fr: 'chien',
      back_es: 'perro',
      tags: ['animaux'],
    }),
    makeCard({
      id: 'c_vieille',
      front_fr: 'vieille',
      back_es: 'vieja',
      stale: true,
    }),
    makeCard({
      id: 'c_drill',
      kind: 'drill',
      front_fr: 'Bonjour',
      back_es: 'Bonjour',
    }),
  ],
});

test('search ignores accents and case', async () => {
  renderRoute(<Cards />, idx, '/cards');
  await userEvent.type(screen.getByLabelText('Buscar tarjetas'), 'ECOLE');
  expect(screen.getByText('l’école')).toBeTruthy();
  expect(screen.queryByText('chien')).toBeNull();
});

test('kind and stale filters', async () => {
  renderRoute(<Cards />, idx, '/cards');
  await userEvent.selectOptions(screen.getByLabelText('Tipo'), 'Taladro');
  expect(screen.getAllByRole('listitem')).toHaveLength(1);
  expect(screen.queryByText('vieille')).toBeNull();
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Incluir obsoletas' }),
  );
});

test('detail lists pending voices and practice link', () => {
  renderRoute(<Cards />, idx, '/cards?card=c_ecole');
  expect(screen.getByText('Pendiente: Eloise · niña')).toBeTruthy();
  expect(
    screen.getByRole('link', { name: 'Practicar' }).getAttribute('href'),
  ).toBe('/practice/c_ecole');
});
