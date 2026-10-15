import '@testing-library/jest-dom/vitest';
import 'fake-indexeddb/auto';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, vi } from 'vitest';
import type { AudioRef, CardOut, Field } from '../contracts/generated';
import { TestContentProvider, makeCard } from '../data/testing';
import { closeFrancesDbForTests, setSetting } from '../db/idb';
import { AudioPlayer } from './AudioPlayer';

beforeEach(async () => {
  await closeFrancesDbForTests();
});

function ref(voiceId: string, field: Field = 'front'): AudioRef {
  return {
    field,
    voice_id: voiceId,
    file: {
      id: voiceId,
      size: 3,
      mime: 'audio/mpeg',
      sha256: 'a'.repeat(64),
    },
  };
}

function renderPlayer(card: CardOut, voiceId?: string) {
  return render(
    <TestContentProvider>
      <AudioPlayer card={card} field="front" voiceId={voiceId} />
    </TestContentProvider>,
  );
}

test('picks preferred voice', async () => {
  await setSetting('preferred_voices', ['fr-FR-HenriNeural']);
  renderPlayer(
    makeCard({
      audio: [ref('fr-FR-DeniseNeural'), ref('fr-FR-HenriNeural')],
    }),
  );
  const select = (await screen.findByLabelText('Voz')) as HTMLSelectElement;
  expect(select.value).toBe('fr-FR-HenriNeural');
});

test('shows pending audio', () => {
  renderPlayer(
    makeCard({
      audio: [],
      audio_pending: [{ field: 'front', voice_id: 'fr-FR-EloiseNeural' }],
    }),
    'fr-FR-EloiseNeural',
  );
  expect(screen.getByText('Audio pendiente (Eloise · niña)')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Reproducir' })).toBeNull();
});

test('revokes object url on unmount', async () => {
  const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x');
  const revoke = vi.spyOn(URL, 'revokeObjectURL');
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  const { unmount } = renderPlayer(
    makeCard({ audio: [ref('fr-FR-DeniseNeural')] }),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Reproducir' }));
  expect(await screen.findByRole('button', { name: 'Detener' })).toBeTruthy();
  unmount();
  expect(create).toHaveBeenCalledOnce();
  expect(revoke).toHaveBeenCalledWith('blob:x');
});
