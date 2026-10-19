import { expect, test, vi } from 'vitest';
import type { SpeechCredentials } from '../contracts/generated';

// Doble del SDK: cuenta `sdkLoads` en la fábrica del mock, de modo que la
// primera `assess` (que hace `await import(...)`) la dispara. Los resultados
// reconocidos/cancelados/sin-coincidencia se preparan con los helpers.
const H = vi.hoisted(() => {
  const state = {
    sdkLoads: 0,
    recognized: null as { duration: number; json: string } | null,
    cancelErrorCode: null as number | null,
    noMatch: false,
  };

  const GradingSystem = { HundredMark: 2 };
  const Granularity = { Phoneme: 1 };
  const ResultReason = { NoMatch: 0, Canceled: 1, RecognizedSpeech: 3 };
  const CancellationErrorCode = {
    NoError: 0,
    AuthenticationFailure: 1,
    TooManyRequests: 3,
  };
  const PropertyId = { SpeechServiceResponse_JsonResult: 'json' };

  const speechConfig: { speechRecognitionLanguage?: string } = {};
  const fromSubscription = vi.fn(() => speechConfig);
  const audioConfig = {};
  const fromDefaultMicrophoneInput = vi.fn(() => audioConfig);

  const applyTo = vi.fn();
  const close = vi.fn();
  const PronunciationAssessmentConfig = vi.fn(function (this: {
    applyTo: typeof applyTo;
  }) {
    this.applyTo = applyTo;
  });

  const makeResult = () => {
    if (state.noMatch) {
      return {
        reason: ResultReason.NoMatch,
        duration: 0,
        properties: { getProperty: () => '' },
      };
    }
    if (state.cancelErrorCode !== null) {
      return {
        reason: ResultReason.Canceled,
        errorCode: state.cancelErrorCode,
        duration: 0,
        properties: { getProperty: () => '' },
      };
    }
    return {
      reason: ResultReason.RecognizedSpeech,
      duration: state.recognized?.duration ?? 0,
      properties: { getProperty: () => state.recognized?.json ?? '{}' },
    };
  };

  const recognizeOnceAsync = vi.fn(
    (cb?: (result: unknown) => void, err?: (error: string) => void) => {
      try {
        cb?.(makeResult());
      } catch (error) {
        err?.(String(error));
      }
    },
  );

  const SpeechRecognizer = vi.fn(function (this: {
    recognizeOnceAsync: typeof recognizeOnceAsync;
    close: typeof close;
  }) {
    this.recognizeOnceAsync = recognizeOnceAsync;
    this.close = close;
  });

  const CancellationDetails = {
    fromResult: vi.fn((result: { errorCode?: number }) => ({
      ErrorCode: result.errorCode,
    })),
  };

  return {
    state,
    GradingSystem,
    Granularity,
    ResultReason,
    CancellationErrorCode,
    PropertyId,
    speechConfig,
    fromSubscription,
    fromDefaultMicrophoneInput,
    applyTo,
    close,
    PronunciationAssessmentConfig,
    SpeechRecognizer,
    recognizeOnceAsync,
    CancellationDetails,
  };
});

vi.mock('microsoft-cognitiveservices-speech-sdk', () => {
  H.state.sdkLoads += 1;
  return {
    SpeechConfig: { fromSubscription: H.fromSubscription },
    AudioConfig: { fromDefaultMicrophoneInput: H.fromDefaultMicrophoneInput },
    SpeechRecognizer: H.SpeechRecognizer,
    PronunciationAssessmentConfig: H.PronunciationAssessmentConfig,
    PronunciationAssessmentGradingSystem: H.GradingSystem,
    PronunciationAssessmentGranularity: H.Granularity,
    ResultReason: H.ResultReason,
    CancellationDetails: H.CancellationDetails,
    CancellationErrorCode: H.CancellationErrorCode,
    PropertyId: H.PropertyId,
  };
});

import { createAzureRecognizer, getRecognizer } from './recognizer';

const creds: SpeechCredentials = {
  region: 'eastus',
  key: 'k',
  locale: 'fr-FR',
};

const mockRecognized = (result: { duration: number; json: string }) => {
  H.state.recognized = result;
  H.state.cancelErrorCode = null;
  H.state.noMatch = false;
};
const mockCanceled = (status: number) => {
  H.state.cancelErrorCode =
    status === 401
      ? H.CancellationErrorCode.AuthenticationFailure
      : H.CancellationErrorCode.TooManyRequests;
  H.state.recognized = null;
  H.state.noMatch = false;
};
const mockNoMatch = () => {
  H.state.noMatch = true;
  H.state.recognized = null;
  H.state.cancelErrorCode = null;
};

test('loads speech sdk lazily', async () => {
  const rec = createAzureRecognizer(creds);
  expect(H.state.sdkLoads).toBe(0);
  mockRecognized({ duration: 0, json: '{}' });
  await rec.assess('Bonjour');
  expect(H.state.sdkLoads).toBe(1);
});

test('configures fr-FR hundred mark phoneme miscue and converts ticks', async () => {
  mockRecognized({ duration: 18_400_000, json: '{}' });
  const out = await createAzureRecognizer(creds).assess('Bonjour');
  expect(out.durationMs).toBe(1840);
  expect(H.fromSubscription).toHaveBeenCalledWith('k', 'eastus');
  expect(H.speechConfig.speechRecognitionLanguage).toBe('fr-FR');
  expect(H.PronunciationAssessmentConfig).toHaveBeenCalledWith(
    'Bonjour',
    H.GradingSystem.HundredMark,
    H.Granularity.Phoneme,
    true,
  );
});

test('canceled and no match map to error codes', async () => {
  const cases: [() => void, string][] = [
    [() => mockCanceled(401), 'unauthorized'],
    [() => mockCanceled(429), 'quota'],
    [mockNoMatch, 'no_match'],
  ];
  for (const [mock, code] of cases) {
    mock();
    await expect(
      createAzureRecognizer(creds).assess('x'),
    ).rejects.toMatchObject({ code });
  }
});

test('getRecognizer uses e2e fake only when VITE_E2E is 1', () => {
  const fake = { assess: vi.fn() };
  Object.assign(window, { __francesFakeRecognizer: fake });
  vi.stubEnv('VITE_E2E', '1');
  expect(getRecognizer(null)).toBe(fake);
  vi.stubEnv('VITE_E2E', '0');
  expect(getRecognizer(null)).toBeNull();
  vi.unstubAllEnvs();
  delete (window as unknown as Record<string, unknown>).__francesFakeRecognizer;
});
