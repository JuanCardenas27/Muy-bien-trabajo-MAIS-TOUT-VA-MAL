import '@testing-library/jest-dom/vitest';
import 'fake-indexeddb/auto';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeAll, beforeEach, onTestFinished, vi } from 'vitest';
import type { Mock } from 'vitest';
import { makeIndex, TestContentProvider } from '../data/testing';
import { loadKey, saveKey } from '../crypto/keystore';
import { closeFrancesDbForTests, getSetting, openFrancesDb } from '../db/idb';
import Settings from './Settings';

// jsdom no implementa `showModal`/`close` de <dialog>: stub solo aquí.
beforeAll(() => {
  const proto = HTMLDialogElement.prototype as unknown as {
    showModal: () => void;
    close: () => void;
  };
  proto.showModal = function (this: HTMLDialogElement): void {
    this.setAttribute('open', '');
  };
  proto.close = function (this: HTMLDialogElement): void {
    this.removeAttribute('open');
    this.dispatchEvent(new Event('close'));
  };
});

beforeEach(async () => {
  await closeFrancesDbForTests();
});

afterEach(() => {
  vi.restoreAllMocks();
});

const setup = (lock: Mock = vi.fn().mockResolvedValue(undefined)) =>
  render(
    <TestContentProvider index={makeIndex()} lock={lock}>
      <MemoryRouter initialEntries={['/settings']}>
        <Routes>
          <Route path="/settings" element={<Settings />} />
          <Route path="/unlock" element={<p>pantalla desbloquear</p>} />
        </Routes>
      </MemoryRouter>
    </TestContentProvider>,
  );

const validFile = new File(
  [
    JSON.stringify({
      format: 'frances-progress',
      version: 1,
      exported_at: '2026-10-15T12:00:00.000Z',
      srs: [{ card_id: 'c9' }],
      review_log: [],
      attempts: [],
      phoneme_stats: [],
      usage: [],
    }),
  ],
  'frances-progreso-2026-10-15.json',
  { type: 'application/json' },
);

test('import asks confirmation in accessible dialog', async () => {
  setup();
  await userEvent.upload(screen.getByLabelText('Importar progreso'), validFile);
  const dialog = await screen.findByRole('dialog', {
    name: '¿Reemplazar tu progreso?',
  });
  expect(dialog).toBeTruthy();
  expect(document.activeElement).toBe(
    screen.getByRole('button', { name: 'Cancelar' }),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Reemplazar' }));
  expect(await screen.findByText('Progreso importado')).toBeTruthy();
  const db = await openFrancesDb();
  expect(await db.getAll('srs')).toEqual([{ card_id: 'c9' }]);
});

test('cancel keeps current progress', async () => {
  const db = await openFrancesDb();
  await db.put('srs', { card_id: 'mio' });
  setup();
  await userEvent.upload(screen.getByLabelText('Importar progreso'), validFile);
  await screen.findByRole('dialog', { name: '¿Reemplazar tu progreso?' });
  await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(await db.getAll('srs')).toEqual([{ card_id: 'mio' }]);
});

test('invalid import file shows spanish error', async () => {
  setup();
  const bad = new File(['{"format":"otra"}'], 'x.json', {
    type: 'application/json',
  });
  await userEvent.upload(screen.getByLabelText('Importar progreso'), bad);
  expect((await screen.findByRole('alert')).textContent).toBe(
    'El archivo no es un progreso de Frances válido',
  );
  expect(screen.queryByRole('dialog')).toBeNull();
});

test('export downloads json with bogota file name', async () => {
  const created: Blob[] = [];
  const createObjectURL = vi.fn((blob: Blob) => {
    created.push(blob);
    return 'blob:fake';
  });
  const revokeObjectURL = vi.fn();
  const original = {
    create: URL.createObjectURL,
    revoke: URL.revokeObjectURL,
  };
  URL.createObjectURL = createObjectURL;
  URL.revokeObjectURL = revokeObjectURL;
  onTestFinished(() => {
    URL.createObjectURL = original.create;
    URL.revokeObjectURL = original.revoke;
  });
  let downloaded = '';
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    downloaded = this.download;
  });
  setup();
  await userEvent.click(
    screen.getByRole('button', { name: 'Exportar progreso' }),
  );
  await waitFor(() =>
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake'),
  );
  expect(downloaded).toMatch(/^frances-progreso-\d{4}-\d{2}-\d{2}\.json$/);
  const blob = created[0] as Blob;
  const parsed = JSON.parse(await blob.text()) as { format: string };
  expect(parsed.format).toBe('frances-progress');
});

test('turning remember off clears the stored key', async () => {
  const key = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    false,
    ['decrypt'],
  );
  await saveKey(key);
  setup();
  const box = await screen.findByRole('checkbox', {
    name: 'Recordar en este dispositivo',
  });
  await waitFor(() => expect(box).toBeChecked());
  await userEvent.click(box);
  await waitFor(async () => expect(await loadKey()).toBeNull());
  expect(await getSetting('remember_key')).toBe(false);
  expect(
    screen.getByText('Se aplica la próxima vez que desbloquees'),
  ).toBeTruthy();
});

test('shows generated date and saves new per day', async () => {
  setup();
  expect(screen.getByText('Datos generados: 14 oct 2026 05:17')).toBeTruthy();
  const input = await screen.findByLabelText('Tarjetas nuevas por día');
  await waitFor(() => expect(input).toHaveValue(20));
  await userEvent.clear(input);
  await userEvent.type(input, '7');
  await waitFor(async () => expect(await getSetting('new_per_day')).toBe(7));
});

test('preferred voices are saved', async () => {
  setup();
  const henri = await screen.findByRole('checkbox', { name: 'Henri' });
  await userEvent.click(henri);
  await waitFor(async () =>
    expect(await getSetting('preferred_voices')).toEqual(['fr-FR-HenriNeural']),
  );
});

test('lock calls lock and goes to unlock', async () => {
  const lock = vi.fn().mockResolvedValue(undefined);
  setup(lock);
  await userEvent.click(screen.getByRole('button', { name: 'Bloquear' }));
  expect(await screen.findByText('pantalla desbloquear')).toBeTruthy();
  expect(lock).toHaveBeenCalledTimes(1);
});
