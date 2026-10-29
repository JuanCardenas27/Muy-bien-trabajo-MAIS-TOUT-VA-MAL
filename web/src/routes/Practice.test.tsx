import '@testing-library/jest-dom/vitest';
import 'fake-indexeddb/auto';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import type { ContentIndex } from '../contracts/generated';
import { makeCard, makeIndex, TestContentProvider } from '../data/testing';
import { closeFrancesDbForTests } from '../db/idb';
import { addSeconds } from '../pron/quota';
import Practice from './Practice';

const card = makeCard({
  id: 'c_0123456789abcdef',
  front_fr: 'Allez vite !',
  back_es: '¡Vamos rápido!',
  audio: [
    {
      field: 'front',
      voice_id: 'fr-FR-DeniseNeural',
      file: {
        id: '0123456789abcdef0123456789abcdef',
        size: 10,
        mime: 'audio/mpeg',
        sha256: '0'.repeat(64),
      },
    },
  ],
});

// Credenciales sintéticas: `getRecognizer` crea el recognizer de Azure de
// forma perezosa (el SDK solo se carga al evaluar), así que no hay red.
const withSpeech = makeIndex({
  cards: [card],
  speech: { key: 'fake-key', region: 'westeurope', locale: 'fr-FR' },
});

function renderRoute(path: string, index: ContentIndex = withSpeech): void {
  render(
    <TestContentProvider index={index}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/practice/:cardId" element={<Practice />} />
        </Routes>
      </MemoryRouter>
    </TestContentProvider>,
  );
}

beforeEach(async () => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-14T21:04:57Z'));
  await closeFrancesDbForTests();
});

afterEach(() => {
  vi.useRealTimers();
});

test('shows quota warning banner at 4 h and still allows recording', async () => {
  await addSeconds('2026-10', 14400);
  renderRoute('/practice/c_0123456789abcdef');
  expect(
    await screen.findByText('Llevas 4 h de las 5 h gratis de este mes'),
  ).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Grabar' })).toBeEnabled();
});

test('shows exceeded banner at 5 h and still allows recording', async () => {
  await addSeconds('2026-10', 18000);
  renderRoute('/practice/c_0123456789abcdef');
  expect(
    await screen.findByText(
      'Es probable que Azure rechace los intentos hasta el próximo mes',
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Grabar' })).toBeEnabled();
});

test('front is french and model audio is present', async () => {
  renderRoute('/practice/c_0123456789abcdef');
  expect(
    (await screen.findByText(card.front_fr)).closest('[lang]'),
  ).toHaveAttribute('lang', 'fr');
  expect(
    await screen.findByRole('button', { name: /Reproducir/ }),
  ).toBeInTheDocument();
});

test('missing speech credentials shows message', async () => {
  renderRoute('/practice/c_0123456789abcdef', makeIndex({ cards: [card] }));
  expect(
    await screen.findByText(
      'La evaluación de pronunciación no está disponible en este bundle',
    ),
  ).toBeInTheDocument();
});

test('unknown card shows not found message', async () => {
  renderRoute('/practice/c_ffffffffffffffff');
  expect(await screen.findByText('Tarjeta no encontrada')).toBeInTheDocument();
});
