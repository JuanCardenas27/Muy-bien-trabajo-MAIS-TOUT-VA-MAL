import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { vi } from 'vitest';
import type { Mock } from 'vitest';
import { TestContentProvider } from '../data/testing';
import Unlock from './Unlock';

const setup = (unlockWith: Mock, entry = '/unlock') =>
  render(
    <TestContentProvider status="locked" unlockWith={unlockWith}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/unlock" element={<Unlock />} />
          <Route path="/" element={<p>inicio</p>} />
          <Route path="/cards" element={<p>tarjetas</p>} />
        </Routes>
      </MemoryRouter>
    </TestContentProvider>,
  );

test('wrong passphrase shows error and keeps input', async () => {
  // REVIEW FOCUS 5
  setup(vi.fn().mockResolvedValue(false));
  const input = screen.getByLabelText('Passphrase') as HTMLInputElement;
  await userEvent.type(input, 'mala clave');
  await userEvent.click(screen.getByRole('button', { name: 'Desbloquear' }));
  expect((await screen.findByRole('alert')).textContent).toBe(
    'Passphrase incorrecta',
  );
  expect(input.value).toBe('mala clave');
  expect(document.activeElement).toBe(input);
  expect(
    screen.getByRole('button', { name: 'Desbloquear' }),
  ).not.toHaveProperty('disabled', true);
});

test('success navigates to next', async () => {
  setup(vi.fn().mockResolvedValue(true), '/unlock?next=%2Fcards');
  await userEvent.type(screen.getByLabelText('Passphrase'), 'y'.repeat(24));
  await userEvent.click(screen.getByRole('button', { name: 'Desbloquear' }));
  expect(await screen.findByText('tarjetas')).toBeTruthy();
});

test('remember unchecked does not persist key', async () => {
  const fn = vi.fn().mockResolvedValue(true);
  setup(fn);
  await userEvent.click(
    screen.getByRole('checkbox', { name: 'Recordar en este dispositivo' }),
  );
  await userEvent.type(screen.getByLabelText('Passphrase'), 'y'.repeat(24));
  await userEvent.click(screen.getByRole('button', { name: 'Desbloquear' }));
  expect(fn).toHaveBeenCalledWith('y'.repeat(24), false);
});

test('ignores external next', async () => {
  setup(vi.fn().mockResolvedValue(true), '/unlock?next=%2F%2Fevil.example');
  await userEvent.type(screen.getByLabelText('Passphrase'), 'y'.repeat(24));
  await userEvent.click(screen.getByRole('button', { name: 'Desbloquear' }));
  expect(await screen.findByText('inicio')).toBeTruthy();
});

test('shows busy text while deriving', async () => {
  let resolveUnlock: (value: boolean) => void = () => undefined;
  const pending = new Promise<boolean>((resolve) => {
    resolveUnlock = resolve;
  });
  setup(vi.fn().mockReturnValue(pending));
  await userEvent.type(screen.getByLabelText('Passphrase'), 'y'.repeat(24));
  await userEvent.click(screen.getByRole('button', { name: 'Desbloquear' }));
  const button = await screen.findByRole('button', { name: 'Abriendo…' });
  expect(button.getAttribute('aria-busy')).toBe('true');
  resolveUnlock(true);
});
