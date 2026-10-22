// Recognizer de Azure Pronunciation Assessment (Task PRN-02).
//
// El SDK (`microsoft-cognitiveservices-speech-sdk`) se carga de forma perezosa:
// solo se importa dinámicamente dentro de `assess`, nunca de forma estática.
// El audio solo va a Azure Speech; aquí no se escribe a disco ni a IndexedDB.

import type { SpeechCredentials } from '../contracts/generated';

export interface Recognizer {
  assess(
    referenceText: string,
    signal?: AbortSignal,
  ): Promise<{ json: unknown; durationMs: number }>;
}

export type RecognizerErrorCode =
  'no_match' | 'unauthorized' | 'quota' | 'canceled';

export class RecognizerError extends Error {
  readonly code: RecognizerErrorCode;

  constructor(code: RecognizerErrorCode, detail?: string) {
    super(detail ?? code);
    this.name = 'RecognizerError';
    this.code = code;
  }
}

// Tipo del módulo del SDK derivado con `typeof import(...)`: es un tipo, no un
// import estático, así el runtime del SDK sigue fuera del bundle inicial.
type SdkModule = typeof import('microsoft-cognitiveservices-speech-sdk');
type SpeechResult = InstanceType<SdkModule['SpeechRecognitionResult']>;

let sdkPromise: Promise<SdkModule> | null = null;

function loadSdk(): Promise<SdkModule> {
  if (sdkPromise === null) {
    sdkPromise = import('microsoft-cognitiveservices-speech-sdk');
  }
  return sdkPromise;
}

function interpret(
  sdk: SdkModule,
  result: SpeechResult,
): { json: unknown; durationMs: number } {
  if (result.reason === sdk.ResultReason.NoMatch) {
    throw new RecognizerError('no_match');
  }
  if (result.reason === sdk.ResultReason.Canceled) {
    const details = sdk.CancellationDetails.fromResult(result);
    if (details.ErrorCode === sdk.CancellationErrorCode.AuthenticationFailure) {
      throw new RecognizerError('unauthorized');
    }
    if (details.ErrorCode === sdk.CancellationErrorCode.TooManyRequests) {
      throw new RecognizerError('quota');
    }
    throw new RecognizerError('canceled');
  }
  const raw = result.properties.getProperty(
    sdk.PropertyId.SpeechServiceResponse_JsonResult,
  );
  return {
    json: JSON.parse(raw) as unknown,
    durationMs: Math.round(result.duration / 10000),
  };
}

export function createAzureRecognizer(creds: SpeechCredentials): Recognizer {
  return {
    async assess(referenceText, signal) {
      const sdk = await loadSdk();
      if (signal?.aborted) {
        throw new RecognizerError('canceled');
      }
      const speechConfig = sdk.SpeechConfig.fromSubscription(
        creds.key,
        creds.region,
      );
      speechConfig.speechRecognitionLanguage = creds.locale ?? 'fr-FR';
      const audioConfig = sdk.AudioConfig.fromDefaultMicrophoneInput();
      const recognizer = new sdk.SpeechRecognizer(speechConfig, audioConfig);
      const assessment = new sdk.PronunciationAssessmentConfig(
        referenceText,
        sdk.PronunciationAssessmentGradingSystem.HundredMark,
        sdk.PronunciationAssessmentGranularity.Phoneme,
        true,
      );
      assessment.applyTo(recognizer);

      let onAbort: () => void = () => undefined;
      try {
        const result = await new Promise<SpeechResult>((resolve, reject) => {
          // Una sola resolución: lo primero que llegue (callback del SDK o
          // abort) gana; lo demás se ignora.
          let settled = false;
          const settle = (fn: () => void) => {
            if (!settled) {
              settled = true;
              fn();
            }
          };
          onAbort = () => {
            settle(() => reject(new RecognizerError('canceled')));
            try {
              recognizer.close();
            } catch {
              // `close()` durante una cancelación no debe romper la máquina de estados.
            }
          };
          signal?.addEventListener('abort', onAbort, { once: true });
          recognizer.recognizeOnceAsync(
            (r) => settle(() => resolve(r)),
            (errorMessage) =>
              settle(() =>
                reject(new RecognizerError('canceled', errorMessage)),
              ),
          );
        });
        return interpret(sdk, result);
      } finally {
        signal?.removeEventListener('abort', onAbort);
        try {
          recognizer.close();
        } catch {
          // idem: cerrar un recognizer ya cerrado es inocuo.
        }
      }
    },
  };
}

export function getRecognizer(
  creds: SpeechCredentials | null,
): Recognizer | null {
  if (import.meta.env.VITE_E2E === '1') {
    const fake = (window as unknown as { __francesFakeRecognizer?: Recognizer })
      .__francesFakeRecognizer;
    if (fake) {
      return fake;
    }
  }
  if (creds === null) {
    return null;
  }
  return createAzureRecognizer(creds);
}
