import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, test, vi } from 'vitest';

const register = vi.hoisted(() => ({
  needRefresh: false,
  updateServiceWorker: vi.fn(),
}));

vi.mock('virtual:pwa-register/react', () => ({
  useRegisterSW: () => ({
    needRefresh: [register.needRefresh, vi.fn()],
    offlineReady: [false, vi.fn()],
    updateServiceWorker: register.updateServiceWorker,
  }),
}));

import PwaStatus from './PwaStatus';

beforeEach(() => {
  register.needRefresh = false;
  register.updateServiceWorker.mockClear();
  vi.restoreAllMocks();
});

test('offline banner when navigator is offline', () => {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
  render(<PwaStatus />);
  expect(screen.getByRole('status').textContent).toBe(
    'Sin conexión: mostrando lo último descargado',
  );
});

test('update prompt calls updateServiceWorker', async () => {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
  register.needRefresh = true;
  render(<PwaStatus />);
  expect(screen.getByText('Hay una versión nueva')).toBeTruthy();
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar' }));
  expect(register.updateServiceWorker).toHaveBeenCalledTimes(1);
});
