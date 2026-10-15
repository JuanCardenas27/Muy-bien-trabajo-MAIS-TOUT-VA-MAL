import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { appRoutes } from './App';
import { LockStatusContext } from './ui/layout/lockStatus';
import type { LockStatus } from './ui/layout/lockStatus';

function renderAt(entry: string, status: LockStatus) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [entry] });
  render(
    <LockStatusContext.Provider value={status}>
      <RouterProvider router={router} />
    </LockStatusContext.Provider>,
  );
  return router;
}

test('redirects to unlock when locked', async () => {
  const router = renderAt('/cards', 'locked');
  await waitFor(() => expect(router.state.location.pathname).toBe('/unlock'));
  expect(router.state.location.search).toBe('?next=%2Fcards');
});

test('nav marks current route', async () => {
  renderAt('/review', 'ready');
  const nav = await screen.findByRole('navigation', { name: 'Principal' });
  expect(
    within(nav)
      .getByRole('link', { name: 'Repaso' })
      .getAttribute('aria-current'),
  ).toBe('page');
  expect(
    within(nav).getByRole('link', { name: 'Hoy' }).getAttribute('aria-current'),
  ).toBeNull();
});

test('loading shows status instead of redirect', async () => {
  const router = renderAt('/cards', 'loading');
  expect((await screen.findByRole('status')).textContent).toBe('Cargando…');
  expect(router.state.location.pathname).toBe('/cards');
});
