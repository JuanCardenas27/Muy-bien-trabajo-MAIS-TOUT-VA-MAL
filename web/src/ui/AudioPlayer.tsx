// Reproductor de audio de tarjeta (Task WEB-10).
//
// Elige la voz por `voiceId` → primera preferida disponible → primera
// disponible. Pide el blob solo al pulsar «Reproducir» y revoca la URL de
// objeto al cambiar de voz, al terminar y al desmontar. Si la tarjeta no
// tiene clip para el campo, muestra el estado «Audio pendiente (voz)» o
// «Sin audio».

import type { JSX } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import type {
  AudioRef,
  CardOut,
  Field,
  VoiceOut,
} from '../contracts/generated';
import { useContent } from '../data/ContentContext';
import { getSetting } from '../db/idb';
import { t } from '../i18n/es';

function ageLabel(voice: VoiceOut): string {
  if (voice.age === 'teen') {
    return t('age.teen');
  }
  if (voice.age === 'child') {
    return t(voice.gender === 'female' ? 'age.child.female' : 'age.child.male');
  }
  return t(voice.gender === 'female' ? 'age.adult.female' : 'age.adult.male');
}

export function voiceLabel(voice: VoiceOut): string {
  return `${voice.label} · ${ageLabel(voice)}`;
}

function chooseVoiceId(
  available: string[],
  preferred: string[],
  voiceId: string | undefined,
): string | null {
  if (available.length === 0) {
    return null;
  }
  if (voiceId !== undefined && available.includes(voiceId)) {
    return voiceId;
  }
  const preferredMatch = preferred.find((id) => available.includes(id));
  return preferredMatch ?? available[0] ?? null;
}

export function AudioPlayer({
  card,
  field,
  voiceId,
}: {
  card: CardOut;
  field: Field;
  voiceId?: string;
}): JSX.Element {
  const { index, getBlob } = useContent();
  const [preferred, setPreferred] = useState<string[] | null>(null);
  const [override, setOverride] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const mountedRef = useRef(true);

  const available = useMemo(
    () => card.audio.filter((ref: AudioRef) => ref.field === field),
    [card.audio, field],
  );
  const availableIds = useMemo(
    () => available.map((ref) => ref.voice_id),
    [available],
  );
  const pendingIds = useMemo(
    () =>
      card.audio_pending
        .filter((pending) => pending.field === field)
        .map((pending) => pending.voice_id),
    [card.audio_pending, field],
  );

  useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;
    getSetting('preferred_voices')
      .then((voices) => {
        if (!cancelled) {
          setPreferred(voices);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPreferred([]);
        }
      });
    return () => {
      cancelled = true;
      mountedRef.current = false;
      if (urlRef.current !== null) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = null;
      }
    };
  }, []);

  const selected =
    override ??
    (preferred === null
      ? null
      : chooseVoiceId(availableIds, preferred, voiceId));

  const voiceById = useMemo(() => {
    const map = new Map<string, VoiceOut>();
    for (const voice of index.voices) {
      map.set(voice.id, voice);
    }
    return map;
  }, [index.voices]);

  function labelFor(id: string): string {
    const voice = voiceById.get(id);
    return voice !== undefined ? voiceLabel(voice) : id;
  }

  function releaseUrl(): void {
    if (urlRef.current !== null) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }

  function stop(): void {
    const element = audioRef.current;
    if (element !== null) {
      element.pause();
      element.removeAttribute('src');
    }
    releaseUrl();
    setPlaying(false);
  }

  async function play(id: string): Promise<void> {
    const clip = available.find((ref) => ref.voice_id === id);
    if (clip === undefined) {
      return;
    }
    releaseUrl();
    const blob = await getBlob(clip.file);
    if (!mountedRef.current) {
      return;
    }
    const url = URL.createObjectURL(blob);
    urlRef.current = url;
    const element = audioRef.current;
    if (element !== null) {
      element.src = url;
    }
    setPlaying(true);
    if (element !== null) {
      void element.play().catch(() => undefined);
    }
  }

  function onToggle(): void {
    if (playing) {
      stop();
      return;
    }
    const id =
      selected ?? chooseVoiceId(availableIds, preferred ?? [], voiceId);
    if (id !== null) {
      void play(id);
    }
  }

  function onSelect(id: string): void {
    if (playing) {
      stop();
    }
    setOverride(id);
  }

  function onEnded(): void {
    releaseUrl();
    setPlaying(false);
  }

  if (available.length === 0) {
    const pendingId =
      voiceId !== undefined && pendingIds.includes(voiceId)
        ? voiceId
        : (pendingIds[0] ?? null);
    if (pendingId !== null) {
      return <p>{t('audio.pending', { voice: labelFor(pendingId) })}</p>;
    }
    return <p>{t('audio.none')}</p>;
  }

  return (
    <div className="audio-player">
      {preferred !== null && (
        <p>
          <label htmlFor={`audio-voice-${card.id}`}>{t('audio.voice')}</label>
          <select
            id={`audio-voice-${card.id}`}
            value={selected ?? ''}
            onChange={(event) => onSelect(event.target.value)}
          >
            {available.map((ref) => (
              <option key={ref.voice_id} value={ref.voice_id}>
                {labelFor(ref.voice_id)}
              </option>
            ))}
          </select>
        </p>
      )}
      <button type="button" onClick={onToggle}>
        {playing ? t('audio.stop') : t('audio.play')}
      </button>
      <audio ref={audioRef} hidden onEnded={onEnded}>
        <track kind="captions" />
      </audio>
    </div>
  );
}

export default AudioPlayer;
