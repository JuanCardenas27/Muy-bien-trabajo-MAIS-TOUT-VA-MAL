// Máquina de estados del grabador (Task PRN-02).
//
// Sin dependencias de React: expone un objeto `Recorder` con estado observable.
// La grabación siempre arranca desde `start()` (llamado desde un gesto del
// usuario, requerido por Safari iOS) y las pistas del micrófono se detienen
// siempre antes de terminar. El audio nunca se persiste.

import type { PronResult } from '../contracts/generated';
import { parseAzureResult } from './parse';
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
    // Micrófono ocupado, interrumpido o con restricciones imposibles: el
    // navegador sí permite grabar, así que se invita a reintentar.
    if (
      error.name === 'NotReadableError' ||
      error.name === 'AbortError' ||
      error.name === 'OverconstrainedError'
    ) {
      return RECORDER_MESSAGES.canceled;
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

function stopTracks(stream: MediaStream): void {
  for (const track of stream.getTracks()) {
    track.stop();
  }
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
  // Sesión en curso: cada `start` tiene su propio controller y su propio
  // stream. Una sesión abortada o reemplazada nunca toca el estado compartido.
  let session: {
    controller: AbortController;
    stream: MediaStream | null;
  } | null = null;

  const setState = (next: RecorderState) => {
    state = next;
    for (const listener of listeners) {
      listener(next);
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
      if (
        state.status === 'requesting_mic' ||
        state.status === 'recording' ||
        state.status === 'scoring'
      ) {
        return;
      }
      const mine: { controller: AbortController; stream: MediaStream | null } =
        { controller: new AbortController(), stream: null };
      session = mine;
      const signal = mine.controller.signal;
      const isCurrent = () => session === mine && !signal.aborted;
      const finish = (next: RecorderState) => {
        if (mine.stream) {
          stopTracks(mine.stream);
          mine.stream = null;
        }
        if (isCurrent()) {
          session = null;
          setState(next);
        }
      };
      setState({ status: 'requesting_mic' });

      let captured: MediaStream;
      try {
        captured = await getUserMedia({ audio: true });
      } catch (error) {
        finish({ status: 'error', message: micErrorMessage(error) });
        return;
      }
      if (!isCurrent()) {
        stopTracks(captured);
        return;
      }
      mine.stream = captured;

      setState({ status: 'recording' });
      let outcome: { json: unknown; durationMs: number };
      try {
        outcome = await recognizer.assess(referenceText, signal);
      } catch (error) {
        finish({ status: 'error', message: recognizerErrorMessage(error) });
        return;
      }
      if (mine.stream) {
        stopTracks(mine.stream);
        mine.stream = null;
      }
      if (!isCurrent()) {
        return;
      }

      setState({ status: 'scoring' });
      let next: RecorderState;
      try {
        const result = parseAzureResult(
          outcome.json,
          referenceText,
          cardId,
          now(),
          outcome.durationMs,
        );
        next = { status: 'done', result };
      } catch {
        // `PronParseError` es el caso esperado; cualquier otro error del
        // parser (p. ej. TypeError) tampoco debe dejar el grabador en `scoring`.
        next = { status: 'error', message: RECORDER_MESSAGES.canceled };
      }
      finish(next);
    },

    abort() {
      const current = session;
      session = null;
      if (current) {
        current.controller.abort();
        if (current.stream) {
          stopTracks(current.stream);
          current.stream = null;
        }
      }
      if (state.status !== 'idle') {
        setState({ status: 'idle' });
      }
    },
  };
}
