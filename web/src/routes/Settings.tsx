// Pantalla Ajustes (Task WEB-11).
//
// Voces preferidas, tarjetas nuevas por día, «Recordar en este
// dispositivo» (desactivarlo borra la clave guardada), fecha de los datos,
// exportar/importar el progreso y bloquear. Importar pide confirmación en
// un <dialog> modal con foco inicial en «Cancelar».

import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent, JSX } from 'react';
import { useNavigate } from 'react-router';
import { clearKey } from '../crypto/keystore';
import { useContent } from '../data/ContentContext';
import { getSetting, setSetting } from '../db/idb';
import { formatLong } from '../i18n/dates';
import { t } from '../i18n/es';
import {
  ProgressImportError,
  exportProgress,
  importProgress,
  progressFileName,
} from '../progress/exportImport';

export default function Settings(): JSX.Element {
  const { index, lock } = useContent();
  const navigate = useNavigate();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [voices, setVoices] = useState<string[]>([]);
  const [newPerDay, setNewPerDay] = useState<string>('');
  const [remember, setRemember] = useState(true);
  const [pending, setPending] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      getSetting('preferred_voices'),
      getSetting('new_per_day'),
      getSetting('remember_key'),
    ]).then(([v, n, r]) => {
      if (!cancelled) {
        setVoices(v);
        setNewPerDay(String(n));
        setRemember(r);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (pending !== null && dialog !== null) {
      if (!dialog.open) {
        dialog.showModal();
      }
      cancelRef.current?.focus();
    }
  }, [pending]);

  function toggleVoice(id: string, on: boolean): void {
    const next = on
      ? [...voices.filter((v) => v !== id), id]
      : voices.filter((v) => v !== id);
    setVoices(next);
    void setSetting('preferred_voices', next);
  }

  function onNewPerDay(event: ChangeEvent<HTMLInputElement>): void {
    const raw = event.target.value;
    setNewPerDay(raw);
    const n = Number(raw);
    if (raw !== '' && Number.isInteger(n) && n >= 0) {
      void setSetting('new_per_day', n);
    }
  }

  async function onRemember(on: boolean): Promise<void> {
    setRemember(on);
    await setSetting('remember_key', on);
    if (!on) {
      await clearKey();
    }
  }

  async function onExport(): Promise<void> {
    const now = new Date();
    const data = await exportProgress(now);
    const blob = new Blob([JSON.stringify(data)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    try {
      const a = document.createElement('a');
      a.href = url;
      a.download = progressFileName(now);
      document.body.appendChild(a);
      a.click();
      a.remove();
    } finally {
      // WebKit cancela la descarga si la URL se revoca en el mismo tick.
      setTimeout(() => URL.revokeObjectURL(url), 100);
    }
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    setMessage(null);
    setError(null);
    const file = event.target.files?.[0];
    if (file === undefined) {
      return;
    }
    let data: unknown;
    try {
      data = JSON.parse(await file.text());
      if (
        typeof data !== 'object' ||
        data === null ||
        (data as { format?: unknown }).format !== 'frances-progress'
      ) {
        throw new ProgressImportError();
      }
    } catch {
      setError(t('settings.importInvalid'));
      resetFile();
      return;
    }
    setPending(data);
  }

  function resetFile(): void {
    if (fileRef.current !== null) {
      fileRef.current.value = '';
    }
  }

  function closeDialog(): void {
    dialogRef.current?.close();
    setPending(null);
    resetFile();
  }

  async function onReplace(): Promise<void> {
    const data = pending;
    closeDialog();
    try {
      await importProgress(data);
      setMessage(t('settings.imported'));
    } catch (err) {
      setError(
        err instanceof ProgressImportError
          ? err.message
          : t('settings.importInvalid'),
      );
    }
  }

  async function onLock(): Promise<void> {
    await lock();
    navigate('/unlock', { replace: true });
  }

  return (
    <section>
      <h1>{t('settings.title')}</h1>

      <fieldset>
        <legend>{t('settings.voices')}</legend>
        {index.voices.map((voice) => (
          <p key={voice.id}>
            <label>
              <input
                type="checkbox"
                checked={voices.includes(voice.id)}
                onChange={(event) =>
                  toggleVoice(voice.id, event.target.checked)
                }
              />{' '}
              {voice.label}
            </label>
          </p>
        ))}
      </fieldset>

      <p>
        <label htmlFor="settings-new-per-day">{t('settings.newPerDay')}</label>{' '}
        <input
          id="settings-new-per-day"
          type="number"
          min={0}
          step={1}
          value={newPerDay}
          onChange={onNewPerDay}
        />
      </p>

      <p>
        <label htmlFor="settings-remember">
          <input
            id="settings-remember"
            type="checkbox"
            checked={remember}
            aria-describedby="settings-remember-note"
            onChange={(event) => void onRemember(event.target.checked)}
          />{' '}
          {t('settings.remember')}
        </label>
      </p>
      <p id="settings-remember-note">{t('settings.rememberNote')}</p>

      <p>{t('settings.generated', { date: formatLong(index.generated_at) })}</p>

      <p>
        <button type="button" onClick={() => void onExport()}>
          {t('settings.export')}
        </button>
      </p>
      <p>
        <label htmlFor="settings-import">{t('settings.import')}</label>{' '}
        <input
          ref={fileRef}
          id="settings-import"
          type="file"
          accept="application/json,.json"
          onChange={(event) => void onFile(event)}
        />
      </p>
      {message !== null ? <p role="status">{message}</p> : null}
      {error !== null ? <p role="alert">{error}</p> : null}

      <p>
        <button type="button" onClick={() => void onLock()}>
          {t('settings.lock')}
        </button>
      </p>

      {pending !== null ? (
        <dialog
          ref={dialogRef}
          aria-labelledby="settings-confirm-title"
          onCancel={() => {
            setPending(null);
            resetFile();
          }}
        >
          <h2 id="settings-confirm-title">{t('settings.confirmTitle')}</h2>
          <button ref={cancelRef} type="button" onClick={closeDialog}>
            {t('settings.cancel')}
          </button>{' '}
          <button type="button" onClick={() => void onReplace()}>
            {t('settings.replace')}
          </button>
        </dialog>
      ) : null}
    </section>
  );
}
