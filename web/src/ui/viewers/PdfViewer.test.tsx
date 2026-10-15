import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import type { FileRef } from '../../contracts/generated';
import { TestContentProvider } from '../../data/testing';
import { PdfViewer } from './PdfViewer';

vi.mock('pdfjs-dist', () => {
  const page = {
    getViewport: () => ({ width: 100, height: 100 }),
    render: () => ({ promise: Promise.resolve(), cancel: () => undefined }),
  };
  return {
    GlobalWorkerOptions: { workerSrc: '' },
    getDocument: () => ({
      promise: Promise.resolve({
        numPages: 3,
        getPage: () => Promise.resolve(page),
      }),
    }),
  };
});

const file: FileRef = {
  id: 'a'.repeat(32),
  mime: 'application/pdf',
  sha256: 'b'.repeat(64),
  size: 10,
};

test('pdf viewer pages through document', async () => {
  render(
    <TestContentProvider>
      <PdfViewer file={file} title="Doc" />
    </TestContentProvider>,
  );
  expect(await screen.findByText('Página 1 de 3')).toBeTruthy();
  await userEvent.click(
    screen.getByRole('button', { name: 'Página siguiente' }),
  );
  expect(screen.getByText('Página 2 de 3')).toBeTruthy();
  expect(
    screen.getByRole('button', { name: 'Página anterior' }),
  ).toBeTruthy();
});
