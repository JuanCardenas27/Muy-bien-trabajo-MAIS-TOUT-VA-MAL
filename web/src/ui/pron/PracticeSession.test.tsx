import '@testing-library/jest-dom/vitest';
import 'fake-indexeddb/auto';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { ReactElement } from 'react';
import bonjour from '../../../../tests/fixtures/azure/bonjour.json';
import { makeCard, TestContentProvider } from '../../data/testing';
import { closeFrancesDbForTests } from '../../db/idb';
import { listAttempts } from '../../pron/attempts';
import { getUsage } from '../../pron/quota';
import type { Recognizer } from '../../pron/recognizer';
import { RecognizerError } from '../../pron/recognizer';
import { loadStats } from '../../pron/stats';
import { PracticeSession } from './PracticeSession';

// JSON «allez» de PRN-01 (PronScore 94; fonemas a/l/e 98/95/62) más una
// palabra omitida, todo sintético.
const allez = {
  DisplayText: 'Allez.',
  NBest: [
    {
      PronunciationAssessment: {
        AccuracyScore: 92,
        FluencyScore: 97,
        CompletenessScore: 100,
        PronScore: 94,
      },
      Words: [
        {
          Word: 'allez',
          PronunciationAssessment: { AccuracyScore: 81, ErrorType: 'None' },
          Phonemes: [
            { Phoneme: 'a', PronunciationAssessment: { AccuracyScore: 98 } },
            { Phoneme: 'l', PronunciationAssessment: { AccuracyScore: 95 } },
            { Phoneme: 'e', PronunciationAssessment: { AccuracyScore: 62 } },
          ],
        },
        {
          Word: 'vite',
          PronunciationAssessment: { AccuracyScore: 0, ErrorType: 'Omission' },
          Phonemes: [],
        },
      ],
    },
  ],
};

const card = makeCard({
  id: 'c_0123456789abcdef',
  front_fr: 'Allez vite !',
  back_es: '¡Vamos rápido!',
});

const stop = vi.fn();

function fakeRecognizer(json: unknown, durationMs = 1840) {
  return {
    assess: vi.fn<Recognizer['assess']>(async () => ({ json, durationMs })),
  };
}

let fakeRec = fakeRecognizer(allez);

function renderSession(ui: ReactElement): void {
  render(<TestContentProvider>{ui}</TestContentProvider>);
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
  fakeRec = fakeRecognizer(allez);
});

afterEach(() => {
  vi.useRealTimers();
});

test('renders scores words and phoneme chips from result', async () => {
  const user = userEvent.setup();
  renderSession(<PracticeSession card={card} recognizer={fakeRec} />);
  expect(screen.getByText('Allez vite !')).toHaveAttribute('lang', 'fr');
  await user.click(screen.getByRole('button', { name: 'Grabar' }));
  const total = await screen.findByRole('region', { name: 'Puntaje global' });
  expect(within(total).getByText('94')).toBeInTheDocument();
  expect(within(total).getByText('Excelente')).toBeInTheDocument();
  for (const text of [
    'Exactitud 92',
    'Fluidez 97',
    'Completitud 100',
    'omitida',
  ]) {
    expect(screen.getByText(text)).toBeInTheDocument();
  }
  const word = screen.getByRole('button', { name: 'allez' });
  expect(word).toHaveAttribute('lang', 'fr');
  await user.click(word);
  const chips = within(
    screen.getByRole('list', { name: 'Fonemas de allez' }),
  ).getAllByRole('listitem');
  expect(chips.map((c) => c.textContent)).toEqual(['a 98', 'l 95', 'e 62']);
  expect(screen.getByRole('button', { name: 'Siguiente' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Repetir' })).toBeInTheDocument();
  expect(stop).toHaveBeenCalled();
});

test('finishing saves attempt stats and seconds', async () => {
  const user = userEvent.setup();
  const onFinished = vi.fn();
  renderSession(
    <PracticeSession
      card={card}
      recognizer={fakeRec}
      onFinished={onFinished}
    />,
  );
  await user.click(screen.getByRole('button', { name: 'Grabar' }));
  await waitFor(() => expect(onFinished).toHaveBeenCalledOnce());
  const attempts = await listAttempts();
  expect(attempts).toHaveLength(1);
  expect(attempts[0]).toMatchObject({
    card_id: 'c_0123456789abcdef',
    at: '2026-10-14T21:04:57.000000Z',
    reference_text: 'Allez vite !',
  });
  expect(await loadStats()).toContainEqual(
    expect.objectContaining({ phoneme: 'e', ema: 62, n: 1 }),
  );
  expect(await getUsage('2026-10')).toBe(2);
  expect(onFinished.mock.calls[0][0]).toMatchObject({ id: attempts[0].id });
});

test('space bar starts recording', async () => {
  const user = userEvent.setup();
  renderSession(<PracticeSession card={card} recognizer={fakeRec} />);
  await user.keyboard(' ');
  expect(fakeRec.assess).toHaveBeenCalledOnce();
  expect(fakeRec.assess.mock.calls[0][0]).toBe('Allez vite !');
  await screen.findByRole('region', { name: 'Puntaje global' });
});

test('stop button aborts while recording', async () => {
  const user = userEvent.setup();
  const pending: Recognizer = {
    assess: (_text, signal) =>
      new Promise((_resolve, reject) => {
        signal?.addEventListener('abort', () =>
          reject(new RecognizerError('canceled')),
        );
      }),
  };
  renderSession(<PracticeSession card={card} recognizer={pending} />);
  await user.click(screen.getByRole('button', { name: 'Grabar' }));
  await user.click(await screen.findByRole('button', { name: 'Detener' }));
  expect(
    await screen.findByRole('button', { name: 'Grabar' }),
  ).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Puntaje global' })).toBeNull();
  expect(await listAttempts()).toHaveLength(0);
});

// Depende del arreglo de PRN-02: `start()` acepta `idle | done | error`.
test('recognizer error is shown as alert and recording can be retried', async () => {
  const user = userEvent.setup();
  const failing = {
    assess: vi
      .fn()
      .mockRejectedValueOnce(new RecognizerError('no_match'))
      .mockResolvedValueOnce({ json: allez, durationMs: 1840 }),
  };
  renderSession(<PracticeSession card={card} recognizer={failing} />);
  await user.click(screen.getByRole('button', { name: 'Grabar' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'No se escuchó nada, intenta de nuevo',
  );
  await user.click(screen.getByRole('button', { name: 'Grabar' }));
  expect(
    await screen.findByRole('region', { name: 'Puntaje global' }),
  ).toBeInTheDocument();
  expect(screen.queryByRole('alert')).toBeNull();
});

// Depende del arreglo de PRN-02: `start()` acepta `idle | done | error`.
test('repeat starts a new attempt and next calls onNext', async () => {
  const user = userEvent.setup();
  const onNext = vi.fn();
  renderSession(
    <PracticeSession card={card} recognizer={fakeRec} onNext={onNext} />,
  );
  await user.click(screen.getByRole('button', { name: 'Grabar' }));
  await user.click(await screen.findByRole('button', { name: 'Repetir' }));
  // «Repetir» vuelve a llamar a `start()` en el mismo Recorder.
  await waitFor(() => expect(fakeRec.assess).toHaveBeenCalledTimes(2));
  await user.click(await screen.findByRole('button', { name: 'Siguiente' }));
  expect(onNext).toHaveBeenCalledOnce();
  expect(fakeRec.assess).toHaveBeenCalledTimes(2);
  expect(await listAttempts()).toHaveLength(2);
});

test('azure fixture with unlabeled phonemes renders and keeps stats clean', async () => {
  const user = userEvent.setup();
  const onFinished = vi.fn();
  renderSession(
    <PracticeSession
      card={makeCard({
        id: 'c_bonjour',
        front_fr: 'Bonjour, comment allez-vous ?',
      })}
      recognizer={fakeRecognizer(bonjour, 1750)}
      onFinished={onFinished}
    />,
  );
  await user.click(screen.getByRole('button', { name: 'Grabar' }));
  const total = await screen.findByRole('region', { name: 'Puntaje global' });
  expect(within(total).getByText('94')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Bonjour' }));
  const chips = within(
    screen.getByRole('list', { name: 'Fonemas de Bonjour' }),
  ).getAllByRole('listitem');
  expect(chips.map((c) => c.textContent)).toEqual([
    '? 100',
    '? 100',
    '? 100',
    '? 100',
    '? 71',
  ]);
  await waitFor(() => expect(onFinished).toHaveBeenCalledOnce());
  expect(await loadStats()).toEqual([]);
});

test('without recognizer shows unavailable message and no record button', () => {
  renderSession(<PracticeSession card={card} recognizer={null} />);
  expect(
    screen.getByText(
      'La evaluación de pronunciación no está disponible en este bundle',
    ),
  ).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Grabar' })).toBeNull();
});
