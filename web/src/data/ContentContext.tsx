// Contexto de contenido descifrado (Task WEB-03).
//
// `ContentProvider` carga el manifiesto, restaura la clave guardada y, si
// la hay, el índice: `loading` → `ready` (o `locked` sin clave, `error`
// ante un fallo). `useContent` solo funciona en `ready`; `useContentState`
// expone el estado y `unlockWith` para la pantalla Desbloquear (WEB-04).

import { createContext, useCallback, useEffect, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { useContext, useState } from 'react';
import type {
  BundleManifest,
  ContentIndex,
  FileRef,
} from '../contracts/generated';
import { clearKey } from '../crypto/keystore';
import { setSetting } from '../db/idb';
import { LockStatusContext } from '../ui/layout/lockStatus';
import type { LockStatus } from '../ui/layout/lockStatus';
import { clearBlobCache, configureBlobs, getBlob as fetchBlob } from './blobs';
import {
  DATA_BASE_URL,
  loadIndex,
  loadManifest,
  restoreKey,
  unlock,
} from './loader';

export interface ContentValue {
  index: ContentIndex;
  getBlob: (ref: FileRef) => Promise<Blob>;
  lock: () => Promise<void>;
}

export interface ContentStateValue {
  status: LockStatus;
  error: string | null;
  unlockWith: (passphrase: string, remember: boolean) => Promise<boolean>;
}

// Valor del proveedor de bajo nivel: alimenta los tres contextos
// (contenido, estado y `LockStatusContext` de WEB-01).
export interface ContentContextValue extends ContentStateValue {
  index: ContentIndex | null;
  getBlob: (ref: FileRef) => Promise<Blob>;
  lock: () => Promise<void>;
}

const ContentContext = createContext<ContentValue | null>(null);
const ContentStateContext = createContext<ContentStateValue | null>(null);

export function useContent(): ContentValue {
  const value = useContext(ContentContext);
  if (value === null) {
    throw new Error('useContent: el contenido no está listo');
  }
  return value;
}

export function useContentState(): ContentStateValue {
  const value = useContext(ContentStateContext);
  if (value === null) {
    throw new Error('useContentState: falta ContentProvider');
  }
  return value;
}

export function ContentContextProvider({
  value,
  children,
}: {
  value: ContentContextValue;
  children: ReactNode;
}): ReactNode {
  const content: ContentValue | null =
    value.status === 'ready' && value.index !== null
      ? { index: value.index, getBlob: value.getBlob, lock: value.lock }
      : null;
  const state: ContentStateValue = {
    status: value.status,
    error: value.error,
    unlockWith: value.unlockWith,
  };
  return (
    <LockStatusContext.Provider value={value.status}>
      <ContentStateContext.Provider value={state}>
        <ContentContext.Provider value={content}>
          {children}
        </ContentContext.Provider>
      </ContentStateContext.Provider>
    </LockStatusContext.Provider>
  );
}

export function ContentProvider({
  children,
  baseUrl,
}: {
  children: ReactNode;
  baseUrl?: string;
}): ReactNode {
  const base = baseUrl ?? DATA_BASE_URL;
  const baseRef = useRef(base);
  baseRef.current = base;
  const manifestRef = useRef<BundleManifest | null>(null);
  const [status, setStatus] = useState<LockStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState<ContentIndex | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const manifest = await loadManifest(baseRef.current);
        if (cancelled) {
          return;
        }
        manifestRef.current = manifest;
        const key = await restoreKey(manifest);
        if (cancelled) {
          return;
        }
        if (key === null) {
          setStatus('locked');
          return;
        }
        configureBlobs(key, baseRef.current);
        const loaded = await loadIndex(manifest, key, baseRef.current);
        if (cancelled) {
          return;
        }
        setIndex(loaded);
        setStatus('ready');
      } catch (err) {
        if (cancelled) {
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
        setStatus('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const unlockWith = useCallback(
    async (passphrase: string, remember: boolean): Promise<boolean> => {
      try {
        let manifest = manifestRef.current;
        if (manifest === null) {
          manifest = await loadManifest(baseRef.current);
          manifestRef.current = manifest;
        }
        const key = await unlock(manifest, passphrase, { remember });
        if (key === null) {
          return false;
        }
        const loaded = await loadIndex(manifest, key, baseRef.current);
        configureBlobs(key, baseRef.current);
        await setSetting('remember_key', remember);
        setIndex(loaded);
        setError(null);
        setStatus('ready');
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setStatus('error');
        return false;
      }
    },
    [],
  );

  const lock = useCallback(async (): Promise<void> => {
    await clearKey();
    configureBlobs(null, baseRef.current);
    clearBlobCache();
    setIndex(null);
    setError(null);
    setStatus('locked');
  }, []);

  const value = useMemo<ContentContextValue>(
    () => ({
      status,
      error,
      unlockWith,
      index,
      getBlob: (ref: FileRef) => fetchBlob(ref),
      lock,
    }),
    [status, error, unlockWith, index, lock],
  );

  return (
    <ContentContextProvider value={value}>{children}</ContentContextProvider>
  );
}
