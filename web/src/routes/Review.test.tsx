import '@testing-library/jest-dom/vitest';
import 'fake-indexeddb/auto';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach } from 'vitest';
import type { ReactElement } from 'react';
import type { ContentIndex } from '../contracts/generated';
import { makeCard, makeIndex, TestContentProvider } from '../data/testing';
import { closeFrancesDbForTests, setSetting } from '../db/idb';
import Review from './Review';

function renderReview(index: ContentIndex): void {
  render(
    (
      <TestContentProvider index={index}>
        <Review />
      </TestContentProvider>
    ) as ReactElement,
  );
}

beforeEach(async () => {
  await closeFrancesDbForTests();
  await setSetting('new_per_day', 20);
});

test('stale cards excluded', async () => {
  renderReview(
    makeIndex({
      cards: [
        makeCard({ id: 'c1', front_fr: 'chat', stale: true }),
        makeCard({ id: 'c2', front_fr: 'chien' }),
      ],
    }),
  );
  expect((await screen.findByText('chien')).getAttribute('lang')).toBe('fr');
  expect(screen.queryByText('chat')).toBeNull();
  expect(screen.getByText('Quedan 1')).toBeTruthy();
});

test('keyboard 1-4 rates', async () => {
  renderReview(
    makeIndex({
      cards: [
        makeCard({ id: 'c1', front_fr: 'chat' }),
        makeCard({ id: 'c2', front_fr: 'chien' }),
      ],
    }),
  );
  await screen.findByText('Quedan 2');
  await userEvent.keyboard(' ');
  expect(screen.getByRole('button', { name: 'Bien (3)' })).toBeTruthy();
  await userEvent.keyboard('3');
  expect(await screen.findByText('Quedan 1')).toBeTruthy();
});
