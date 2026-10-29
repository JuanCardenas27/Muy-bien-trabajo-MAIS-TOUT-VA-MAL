// Tests de la ruta Taladro (Task PRN-05): decodifica el fonema de la URL,
// recorre la sesión con `PracticeSession` y al terminar muestra el resumen
// EMA `/fonema/: antes → después`. Fonema sin mazo → mensaje vacío.

import '@testing-library/jest-dom/vitest';
import 'fake-indexeddb/auto';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { ContentIndex } from '../contracts/generated';
import { makeCard, makeIndex, TestContentProvider } from '../data/testing';
import { closeFrancesDbForTests } from '../db/idb';
import type { Recognizer } from '../pron/recognizer';
import { saveStats } from '../pron/stats';
import Drill from './Drill';

// Evaluación sintética: «Vent» puntúa ɑ̃ en 80 (v 85, t 75); con α = 0.3 la
// EMA de ɑ̃ pasa de 70 a 73 y a 75,1 tras los dos intentos de la sesión.
const vent = {
  DisplayText: 'Vent.',
  NBest: [
    {
      PronunciationAssessment: {
        AccuracyScore: 80,
        FluencyScore: 82,
        CompletenessScore: 100,
        PronScore: 80,
      },
      Words: [
        {
          Word: 'Vent',
          PronunciationAssessment: { AccuracyScore: 80, ErrorType: 'None' },
          Phonemes: [
            { Phoneme: 'v', PronunciationAssessment: { AccuracyScore: 85 } },
            { Phoneme: 'ɑ̃', PronunciationAssessment: { AccuracyScore: 80 } },
            { Phoneme: 't', PronunciationAssessment: { AccuracyScore: 75 } },
          ],
        },
      ],
    },
  ],
};

const cards = [
  makeCard({ id: 'c_vent1', front_fr: 'Le vent souffle' }),
  makeCard({ id: 'c_vent2', front_fr: 'Vingt ans' }),
];

const drillIndex = makeIndex({
  cards,
  drills: [
    {
      id: 'd_an',
      phoneme: 'ɑ̃',
      title_es: 'La nasal ɑ̃',
      curated: true,
      card_ids: cards.map((c) => c.id),
    },
  ],
  speech: { key: 'fake-key', region: 'westeurope', locale: 'fr-FR' },
});

// Recognizer falso: solo `assess`, sin SDK ni red; se inyecta por la vía
// E2E (`getRecognizer` con `VITE_E2E=1`).
const fake = {
  assess: vi.fn<Recognizer['assess']>(async () => ({
    json: vent,
    durationMs: 1840,
  })),
};

function renderRoute(path: string, index: ContentIndex = drillIndex): void {
  render(
    <TestContentProvider index={index}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/drill/:phoneme" element={<Drill />} />
        </Routes>
      </MemoryRouter>
    </TestContentProvider>,
  );
}

beforeEach(async () => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-14T21:04:57Z'));
  await closeFrancesDbForTests();
  await saveStats([
    { phoneme: 'ɑ̃', ema: 70, n: 3, last_at: '2026-10-14T20:00:00.000000Z' },
  ]);
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn(
        async () =>
          ({ getTracks: () => [{ stop: vi.fn() }] }) as unknown as MediaStream,
      ),
    },
  });
  Object.assign(window, { __francesFakeRecognizer: fake });
  vi.stubEnv('VITE_E2E', '1');
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  delete (window as unknown as Record<string, unknown>).__francesFakeRecognizer;
});

test('drill route decodes phoneme and finishes with summary', async () => {
  const user = userEvent.setup();
  renderRoute(`/drill/${encodeURIComponent('ɑ̃')}`);
  expect(
    await screen.findByRole('heading', { level: 1, name: 'Taladro /ɑ̃/' }),
  ).toBeInTheDocument();
  for (let i = 0; i < 2; i += 1) {
    await user.click(await screen.findByRole('button', { name: 'Grabar' }));
    await user.click(await screen.findByRole('button', { name: 'Siguiente' }));
  }
  expect(await screen.findByText('/ɑ̃/: 70 → 75,1')).toBeInTheDocument();
});

test('unknown phoneme shows empty message', async () => {
  renderRoute('/drill/y');
  expect(
    await screen.findByText('No hay taladro para este fonema'),
  ).toBeInTheDocument();
});
