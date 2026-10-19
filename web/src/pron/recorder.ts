// Máquina de estados del grabador (Task PRN-02).
//
// Sin dependencias de React: expone un objeto `Recorder` con estado observable.
// La grabación siempre arranca desde `start()` (llamado desde un gesto del
// usuario, requerido por Safari iOS) y las pistas del micrófono se detienen
// siempre antes de terminar. El audio nunca se persiste.

import type { PronResult } from '../contracts/generated';
import { PronParseError, parseAzureResult } from './parse';
import type { Recognizer } from './recognizer';
import { RecognizerError } from './recognizer';

export type RecorderState =
  | { status: 'idle' | 'requesting_mic' | 'recording' | 'scoring' }
  | { status: 'done'; result: PronResult }
  | { status: 'error'; message: string };

export interface Recorder {
  getState(): RecorderState;
  subscribe(fn: (state: RecorderState) => void): () => void;
  start(referenceText: string, cardId: string | null): Promise<void>;
  abort(): void;
}

// Cadenas propias de P06 (R-18): no van a `es.ts` de WEB-01.
export const RECORDER_MESSAGES = {
  denied:
    'Permiso de micrófono denegado: actívalo en la configuración del navegador',
  no_microphone: 'No se encontró micrófono',
  unsupported: 'Este navegador no permite grabar aquí',
  no_match: 'No se escuchó nada, intenta de nuevo',
  unauthorized: 'Clave de Azure inválida',
  quota: 'Cuota de Azure agotada por ahora',
  canceled: 'No se pudo evaluar, intenta de nuevo',
} as const;

function defaultGetUserMedia(
  constraints: MediaStreamConstraints,
): Promise<MediaStream> {
  const devices = navigator.mediaDevices;
  if (!devices || typeof devices.getUserMedia !== 'function') {
    return Promise.reject(
      new DOMException('sin getUserMedia', 'NotSupportedError'),
    );
  }
  return devices.getUserMedia(constraints);
}

function micErrorMessage(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError' || error.name === 'SecurityError') {
      return RECORDER_MESSAGES.denied;
    }
    if (
      error.name === 'NotFoundError' ||
      error.name === 'DevicesNotFoundError'
    ) {
      return RECORDER_MESSAGES.no_microphone;
    }
  }
  return RECORDER_MESSAGES.unsupported;
}

function recognizerErrorMessage(error: unknown): string {
  if (error instanceof RecognizerError) {
    return RECORDER_MESSAGES[error.code];
  }
  return RECORDER_MESSAGES.canceled;
}

export function createRecorder(
  recognizer: Recognizer,
  getUserMedia: (
    constraints: MediaStreamConstraints,
  ) => Promise<MediaStream> = defaultGetUserMedia,
  now: () => Date = () => new Date(),
): Recorder {
  let state: RecorderState = { status: 'idle' };
  const listeners = new Set<(state: RecorderState) => void>();
  let controller: AbortController | null = null;
  let stream: MediaStream | null = null;

  const setState = (next: RecorderState) => {
    state = next;
    for (const listener of listeners) {
      listener(next);
    }
  };

  const stopTracks = () => {
    if (stream) {
      for (const track of stream.getTracks()) {
        track.stop();
      }
      stream = null;
    }
  };

  return {
    getState: () => state,

    subscribe(fn) {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },

    async start(referenceText, cardId) {
      if (state.status !== 'idle') {
        return;
      }
      controller = new AbortController();
      const signal = controller.signal;
      setState({ status: 'requesting_mic' });

      let captured: MediaStream;
      try {
        captured = await getUserMedia({ audio: true });
      } catch (error) {
        if (signal.aborted) {
          setState({ status: 'idle' });
          return;
        }
        setState({ status: 'error', message: micErrorMessage(error) });
        return;
      }
      stream = captured;
      if (signal.aborted) {
        stopTracks();
        setState({ status: 'idle' });
        return;
      }

      setState({ status: 'recording' });
      let outcome: { json: unknown; durationMs: number };
      try {
        outcome = await recognizer.assess(referenceText, signal);
      } catch (error) {
        stopTracks();
        if (signal.aborted) {
          setState({ status: 'idle' });
          return;
        }
        setState({ status: 'error', message: recognizerErrorMessage(error) });
        return;
      }
      stopTracks();
      if (signal.aborted) {
        setState({ status: 'idle' });
        return;
      }

      setState({ status: 'scoring' });
      try {
        const result = parseAzureResult(
          outcome.json,
          referenceText,
          cardId,
          now(),
          outcome.durationMs,
        );
        setState({ status: 'done', result });
      } catch (error) {
        if (error instanceof PronParseError) {
          setState({ status: 'error', message: RECORDER_MESSAGES.canceled });
          return;
        }
        throw error;
      }
    },

    abort() {
      controller?.abort();
      stopTracks();
      if (state.status !== 'done') {
        setState({ status: 'idle' });
      }
    },
  };
}
