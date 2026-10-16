// Banner de estado PWA (Task WEB-12): sin conexión y versión nueva.
//
// `useRegisterSW` (vite-plugin-pwa) avisa cuando hay una versión nueva; el
// banner ofrece el botón «Actualizar». El estado offline se sigue con los
// eventos `online`/`offline` del navegador. El componente no renderiza nada
// cuando todo está al día y hay conexión.

import { useCallback, useEffect, useState } from 'react';
import type { JSX } from 'react';
import { useRegisterSW } from 'virtual:pwa-register/react';
import { t } from '../i18n/es';

function useOnline(): boolean {
  const [online, setOnline] = useState<boolean>(() => navigator.onLine);
  useEffect(() => {
    const goOnline = (): void => setOnline(true);
    const goOffline = (): void => setOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);
  return online;
}

export default function PwaStatus(): JSX.Element | null {
  const online = useOnline();
  const {
    needRefresh: [needRefresh],
    updateServiceWorker,
  } = useRegisterSW();

  const update = useCallback((): void => {
    void updateServiceWorker(true);
  }, [updateServiceWorker]);

  if (!online) {
    return <p role="status">{t('pwa.offline')}</p>;
  }
  if (needRefresh) {
    return (
      <p role="status">
        {t('pwa.update')}{' '}
        <button type="button" onClick={update}>
          {t('pwa.reload')}
        </button>
      </p>
    );
  }
  return null;
}
