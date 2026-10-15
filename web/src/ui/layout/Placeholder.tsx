import type { JSX } from 'react';
import { t } from '../../i18n/es';

export function Placeholder(): JSX.Element {
  return <p>{t('app.placeholder')}</p>;
}

export default Placeholder;
