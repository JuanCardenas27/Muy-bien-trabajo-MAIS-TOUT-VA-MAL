import { Component } from 'react';
import type { JSX, ReactNode } from 'react';
import { t } from '../../i18n/es';

export function ErrorFallback(): JSX.Element {
  return (
    <div role="alert">
      <p>{t('app.error')}</p>
      <button type="button" onClick={() => window.location.reload()}>
        {t('app.reload')}
      </button>
    </div>
  );
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(): void {
    // El error queda registrado en la consola del navegador; la UI muestra
    // un mensaje en español con una vía de recuperación.
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <ErrorFallback />;
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
