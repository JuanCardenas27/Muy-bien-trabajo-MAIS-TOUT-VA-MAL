import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { Root } from './main';

it('renders app title', () => {
  render(<Root />);
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
    'Frances',
  );
});
