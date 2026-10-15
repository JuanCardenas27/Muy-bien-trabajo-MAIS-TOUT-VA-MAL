import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import type { JSX } from 'react';

export function Root(): JSX.Element {
  return <h1>Frances</h1>;
}

const el = document.getElementById('root');
if (el !== null) {
  createRoot(el).render(
    <StrictMode>
      <Root />
    </StrictMode>,
  );
}
