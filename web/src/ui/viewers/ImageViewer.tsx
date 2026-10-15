// Visor de imágenes (Task WEB-06): descarga y descifra el blob con
// `getBlob`, lo muestra con una object URL y la revoca al desmontar o al
// cambiar de archivo.

import { useEffect, useState } from 'react';
import type { JSX } from 'react';
import type { FileRef } from '../../contracts/generated';
import { useContent } from '../../data/ContentContext';
import { t } from '../../i18n/es';

export function ImageViewer({
  file,
  alt,
}: {
  file: FileRef;
  alt: string;
}): JSX.Element {
  const { getBlob } = useContent();
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setUrl(null);
    setFailed(false);
    (async () => {
      const blob = await getBlob(file);
      if (cancelled) {
        return;
      }
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    })().catch(() => {
      if (!cancelled) {
        setFailed(true);
      }
    });
    return () => {
      cancelled = true;
      if (objectUrl !== null) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [file, getBlob]);

  if (failed) {
    return <p>{t('att.unavailable')}</p>;
  }
  if (url === null) {
    return <p role="status">{t('app.loading')}</p>;
  }
  return <img src={url} alt={alt} />;
}
