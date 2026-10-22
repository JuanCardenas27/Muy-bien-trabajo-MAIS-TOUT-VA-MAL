import '@testing-library/jest-dom/vitest';
import 'fake-indexeddb/auto';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import type { ContentIndex } from '../contracts/generated';
import { makeCard, makeIndex, TestContentProvider } from '../data/testing';
import { closeFrancesDbForTests } from '../db/idb';
import type { Recognizer } from '../pron/recognizer';
import { saveStats } from '../pron/stats';
import Drill from './Drill';

// Datos sintéticos: cada intento puntúa el fonema ɑ̃ con 80.
const nasal = {
  DisplayText: 'Dans.',
  NBest: [
    {
      PronunciationAssessment: {
        AccuracyScore: 80,
        FluencyScore: 90,
        CompletenessScore: 100,
        PronScore: 85,
      },
      Words: [
        {
          Word: 'dans',
          PronunciationAssessment: { AccuracyScore: 80, ErrorType: 'None' },
          Phonemes: [
            { Phoneme: 'd', PronunciationAssessment: { AccuracyScore: 95 } },
            { Phoneme: 'ɑ̃', PronunciationAssessment: { AccuracyScore: 80 } },
          ],
        },
      ],
    },
  ],
};

const cards = [
  makeCard({
    id: 'c_drill00',
    kind: 'drill',
    front_fr: 'Dans le vent',
    phonemes: ['ɑ̃'],
  }),
  makeCard({
    id: 'c_drill01',
    kind: 'drill',
    front_fr: 'Un grand enfant',
    phonemes: ['ɑ̃'],
  }),
];

const index = makeIndex({
  cards,
  drills: [
    {
      id: 'd_an',
      phoneme: 'ɑ̃',
      curated: true,
      title_es: 'Nasal ɑ̃',
      card_ids: cards.map((c) => c.id),
    },
  ],
});

const stop = vi.fn();

function renderRoute(path: string, idx: ContentIndex = index): void {
  render(
    <TestContentProvider index={idx}>
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
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn(
        async () => ({ getTracks: () => [{ stop }] }) as unknown as MediaStream,
      ),
    },
  });
  const fake: Recognizer = {
    assess: vi.fn<Recognizer['assess']>(async () => ({
      json: nasal,
      durationMs: 1500,
    })),
  };
  vi.stubEnv('VITE_E2E', '1');
  (
    window as unknown as { __francesFakeRecognizer?: Recognizer }
  ).__francesFakeRecognizer = fake;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  delete (window as unknown as { __francesFakeRecognizer?: Recognizer })
    .__francesFakeRecognizer;
});

test('drill route decodes phoneme and finishes with summary', async () => {
  await saveStats([
    { phoneme: 'ɑ̃', ema: 70, n: 3, last_at: '2026-10-13T10:00:00Z' },
  ]);
  const user = userEvent.setup();
  renderRoute(`/drill/${encodeURIComponent('ɑ̃')}`);
  expect(
    await screen.findByRole('heading', { level: 1, name: 'Taladro /ɑ̃/' }),
  ).toBeInTheDocument();
  for (let i = 0; i < 2; i++) {
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
