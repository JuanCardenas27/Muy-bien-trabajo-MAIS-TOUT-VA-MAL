import { useContext } from 'react';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';
import { t } from '../../i18n/es';
import { LockStatusContext } from './lockStatus';

export function RequireUnlocked({ children }: { children: ReactNode }) {
  const status = useContext(LockStatusContext);
  const { pathname, search } = useLocation();
  if (status === 'ready') {
    return <>{children}</>;
  }
  if (status === 'loading') {
    return <p role="status">{t('app.loading')}</p>;
  }
  return (
    <Navigate
      to={`/unlock?next=${encodeURIComponent(pathname + search)}`}
      replace
    />
  );
}

export default RequireUnlocked;
