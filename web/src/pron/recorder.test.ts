import { expect, test, vi } from 'vitest';
import { createRecorder } from './recorder';
import { RecognizerError } from './recognizer';
import type { Recognizer } from './recognizer';

// JSON «allez» de PRN-01: PronScore 94 y fonemas a/l/e con 98/95/62.
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
      ],
    },
  ],
};

const stop = vi.fn();
const okGum = vi.fn(
  async () => ({ getTracks: () => [{ stop }] }) as unknown as MediaStream,
);

test('mic denied moves to error state with message', async () => {
  const rec = { assess: vi.fn() } as unknown as Recognizer;
  const seen: string[] = [];
  const r = createRecorder(rec, () =>
    Promise.reject(new DOMException('denied', 'NotAllowedError')),
  );
  r.subscribe((s) => seen.push(s.status));
  await r.start('Bonjour', null);
  expect(seen).toEqual(['requesting_mic', 'error']);
  expect(r.getState()).toEqual({
    status: 'error',
    message:
      'Permiso de micrófono denegado: actívalo en la configuración del navegador',
  });
  expect(rec.assess).not.toHaveBeenCalled();
});

test('no microphone and no mediaDevices messages', async () => {
  const nf = createRecorder({ assess: vi.fn() } as unknown as Recognizer, () =>
    Promise.reject(new DOMException('x', 'NotFoundError')),
  );
  await nf.start('Bonjour', null);
  expect(nf.getState()).toEqual({
    status: 'error',
    message: 'No se encontró micrófono',
  });

  vi.stubGlobal('navigator', {});
  const none = createRecorder({ assess: vi.fn() } as unknown as Recognizer);
  await none.start('Bonjour', null);
  expect(none.getState()).toEqual({
    status: 'error',
    message: 'Este navegador no permite grabar aquí',
  });
  vi.unstubAllGlobals();
});

test('happy path goes to done with parsed result and stops tracks', async () => {
  const r = createRecorder(
    { assess: async () => ({ json: allez, durationMs: 1840 }) },
    okGum,
    () => new Date('2026-10-14T21:04:57.216Z'),
  );
  const seen: string[] = [];
  r.subscribe((s) => seen.push(s.status));
  await r.start('Allez !', 'c_0123456789abcdef');
  expect(seen).toEqual(['requesting_mic', 'recording', 'scoring', 'done']);
  expect(stop).toHaveBeenCalled();
  const s = r.getState();
  expect(s.status === 'done' && s.result.scores.pron).toBe(94);
});

test.each([
  ['no_match', 'No se escuchó nada, intenta de nuevo'],
  ['unauthorized', 'Clave de Azure inválida'],
  ['quota', 'Cuota de Azure agotada por ahora'],
] as const)('recognizer %s maps to message', async (code, message) => {
  const r = createRecorder(
    { assess: () => Promise.reject(new RecognizerError(code)) },
    okGum,
  );
  await r.start('Bonjour', null);
  expect(r.getState()).toEqual({ status: 'error', message });
});

test('abort returns to idle and aborts the signal', async () => {
  let sig: AbortSignal | undefined;
  const r = createRecorder(
    {
      assess: (_referenceText, signal) => {
        sig = signal;
        return new Promise<{ json: unknown; durationMs: number }>(
          () => undefined,
        );
      },
    },
    okGum,
  );
  void r.start('Bonjour', null);
  await vi.waitFor(() => expect(r.getState().status).toBe('recording'));
  r.abort();
  expect(sig?.aborted).toBe(true);
  expect(r.getState()).toEqual({ status: 'idle' });
});

const neverAssess = () =>
  new Promise<{ json: unknown; durationMs: number }>(() => undefined);

const fakeStream = () => {
  const trackStop = vi.fn();
  const s = {
    getTracks: () => [{ stop: trackStop }],
  } as unknown as MediaStream;
  return { stream: s, trackStop };
};

test('start again after done and after error', async () => {
  let fail = false;
  const r = createRecorder(
    {
      assess: () =>
        fail
          ? Promise.reject(new RecognizerError('no_match'))
          : Promise.resolve({ json: allez, durationMs: 1840 }),
    },
    okGum,
  );
  await r.start('Allez !', null);
  expect(r.getState().status).toBe('done');
  fail = true;
  await r.start('Allez !', null);
  expect(r.getState()).toEqual({
    status: 'error',
    message: 'No se escuchó nada, intenta de nuevo',
  });
  fail = false;
  await r.start('Allez !', null);
  expect(r.getState().status).toBe('done');
  r.abort();
  expect(r.getState()).toEqual({ status: 'idle' });
});

test('start is ignored while a session is in progress', async () => {
  const assess = vi.fn(neverAssess);
  const r = createRecorder({ assess }, okGum);
  void r.start('Bonjour', null);
  await vi.waitFor(() => expect(r.getState().status).toBe('recording'));
  await r.start('Bonjour', null);
  expect(assess).toHaveBeenCalledTimes(1);
  expect(r.getState().status).toBe('recording');
});

test('aborted session during getUserMedia does not touch the new session', async () => {
  const old = fakeStream();
  const fresh = fakeStream();
  let resolveOld: (s: MediaStream) => void = () => undefined;
  const gum = vi
    .fn<(c: MediaStreamConstraints) => Promise<MediaStream>>()
    .mockImplementationOnce(
      () =>
        new Promise<MediaStream>((resolve) => {
          resolveOld = resolve;
        }),
    )
    .mockImplementationOnce(async () => fresh.stream);
  const r = createRecorder({ assess: neverAssess }, gum);
  void r.start('Bonjour', null);
  await vi.waitFor(() => expect(r.getState().status).toBe('requesting_mic'));
  r.abort();
  void r.start('Bonjour', null);
  await vi.waitFor(() => expect(r.getState().status).toBe('recording'));
  resolveOld(old.stream);
  await vi.waitFor(() => expect(old.trackStop).toHaveBeenCalled());
  expect(fresh.trackStop).not.toHaveBeenCalled();
  expect(r.getState().status).toBe('recording');
});

test('aborted session during assess does not stop the new session tracks', async () => {
  const old = fakeStream();
  const fresh = fakeStream();
  let rejectOld: (e: unknown) => void = () => undefined;
  const assess = vi
    .fn<Recognizer['assess']>()
    .mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectOld = reject;
        }),
    )
    .mockImplementationOnce(neverAssess);
  const gum = vi
    .fn<(c: MediaStreamConstraints) => Promise<MediaStream>>()
    .mockImplementationOnce(async () => old.stream)
    .mockImplementationOnce(async () => fresh.stream);
  const r = createRecorder({ assess }, gum);
  void r.start('Bonjour', null);
  await vi.waitFor(() => expect(r.getState().status).toBe('recording'));
  r.abort();
  expect(old.trackStop).toHaveBeenCalled();
  void r.start('Bonjour', null);
  await vi.waitFor(() => expect(assess).toHaveBeenCalledTimes(2));
  rejectOld(new RecognizerError('canceled'));
  await Promise.resolve();
  await Promise.resolve();
  expect(fresh.trackStop).not.toHaveBeenCalled();
  expect(r.getState().status).toBe('recording');
});

test('unexpected parser error goes to error state instead of hanging in scoring', async () => {
  const r = createRecorder(
    {
      assess: async () => ({
        json: { NBest: [{ Words: 5 }] },
        durationMs: 10,
      }),
    },
    okGum,
  );
  await r.start('Bonjour', null);
  expect(r.getState()).toEqual({
    status: 'error',
    message: 'No se pudo evaluar, intenta de nuevo',
  });
});

test.each(['NotReadableError', 'AbortError', 'OverconstrainedError'])(
  '%s from getUserMedia maps to the canceled message',
  async (name) => {
    const r = createRecorder({ assess: vi.fn() } as unknown as Recognizer, () =>
      Promise.reject(new DOMException('x', name)),
    );
    await r.start('Bonjour', null);
    expect(r.getState()).toEqual({
      status: 'error',
      message: 'No se pudo evaluar, intenta de nuevo',
    });
  },
);
