import { createContext } from 'react';

export type LockStatus = 'locked' | 'loading' | 'ready' | 'error';

export const LockStatusContext = createContext<LockStatus>('locked');
