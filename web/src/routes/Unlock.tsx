// Pantalla Desbloquear (Task WEB-04).
//
// Pide la passphrase y llama a `unlockWith` de WEB-03. Si es incorrecta,
// muestra una alerta en español, conserva el valor y devuelve el foco al
// input; si acierta, navega a `next` (solo rutas internas). Mientras se
// deriva la clave, el botón indica `unlock.busy` con `aria-busy`.

import { useRef, useState } from 'react';
import type { FormEvent, JSX } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useContentState } from '../data/ContentContext';
import { t } from '../i18n/es';

// Solo se acepta un `next` interno: empieza por `/` y no por `//`
// (protocol-relative, que apuntaría a otro dominio).
export function safeNext(raw: string | null): string {
  if (raw === null || !raw.startsWith('/') || raw.startsWith('//')) {
    return '/';
  }
  return raw;
}

export default function Unlock(): JSX.Element {
  const { status, error, unlockWith } = useContentState();
  const navigate = useNavigate();
  const location = useLocation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [passphrase, setPassphrase] = useState('');
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [wrong, setWrong] = useState(false);

  const next = safeNext(new URLSearchParams(location.search).get('next'));

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setWrong(false);
    setBusy(true);
    const ok = await unlockWith(passphrase, remember);
    setBusy(false);
    if (ok) {
      navigate(next, { replace: true });
      return;
    }
    setWrong(true);
    inputRef.current?.focus();
  }

  return (
    <form onSubmit={onSubmit}>
      <h1>{t('unlock.title')}</h1>
      {status === 'error' && error !== null ? (
        <p role="alert">{error}</p>
      ) : null}
      <p>
        <label htmlFor="unlock-passphrase">{t('unlock.label')}</label>
      </p>
      <p>
        <input
          ref={inputRef}
          id="unlock-passphrase"
          type="password"
          autoComplete="current-password"
          value={passphrase}
          onChange={(event) => setPassphrase(event.target.value)}
        />
      </p>
      <p>
        <label htmlFor="unlock-remember">
          <input
            id="unlock-remember"
            type="checkbox"
            checked={remember}
            onChange={(event) => setRemember(event.target.checked)}
          />{' '}
          {t('unlock.remember')}
        </label>
      </p>
      {wrong ? <p role="alert">{t('unlock.wrong')}</p> : null}
      <button type="submit" disabled={busy} aria-busy={busy}>
        {busy ? t('unlock.busy') : t('unlock.submit')}
      </button>
    </form>
  );
}
