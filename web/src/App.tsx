import { Suspense, lazy } from 'react';
import type { ComponentType, JSX, LazyExoticComponent, ReactNode } from 'react';
import { RouterProvider, createBrowserRouter } from 'react-router';
import type { RouteObject } from 'react-router';
import { t } from './i18n/es';
import { ErrorBoundary, ErrorFallback } from './ui/layout/ErrorBoundary';
import { Layout } from './ui/layout/Layout';
import { Placeholder } from './ui/layout/Placeholder';
import { RequireUnlocked } from './ui/layout/RequireUnlocked';

export const ROUTES: { path: string; module: string; protected: boolean }[] = [
  { path: '/unlock', module: 'Unlock', protected: false },
  { path: '/', module: 'Today', protected: true },
  { path: '/classroom', module: 'Classroom', protected: true },
  { path: '/item/:id', module: 'ItemDetail', protected: true },
  { path: '/item/:id/sheet', module: 'Sheet', protected: true },
  { path: '/review', module: 'Review', protected: true },
  { path: '/cards', module: 'Cards', protected: true },
  { path: '/practice/:cardId', module: 'Practice', protected: true },
  { path: '/drill/:phoneme', module: 'Drill', protected: true },
  { path: '/progress', module: 'Progress', protected: true },
  { path: '/settings', module: 'Settings', protected: true },
];

type RouteModule = { default: ComponentType };

const routeModules = import.meta.glob<RouteModule>('./routes/*.tsx');

const lazyCache = new Map<string, LazyExoticComponent<ComponentType>>();

function routeComponent(module: string): LazyExoticComponent<ComponentType> {
  const cached = lazyCache.get(module);
  if (cached !== undefined) {
    return cached;
  }
  const loader = routeModules[`./routes/${module}.tsx`];
  const Comp = lazy(
    loader ?? (() => Promise.resolve({ default: Placeholder })),
  );
  lazyCache.set(module, Comp);
  return Comp;
}

function RouteElement({ module }: { module: string }): JSX.Element {
  const Comp = routeComponent(module);
  return (
    <Suspense fallback={<p role="status">{t('app.loading')}</p>}>
      <Comp />
    </Suspense>
  );
}

function protectedParent(): RouteObject {
  return {
    element: (
      <RequireUnlocked>
        <Layout />
      </RequireUnlocked>
    ),
    errorElement: <ErrorFallback />,
    children: ROUTES.filter((r) => r.protected).map((r): RouteObject => ({
      path: r.path,
      element: <RouteElement module={r.module} />,
    })),
  };
}

export const appRoutes: RouteObject[] = [
  ...ROUTES.filter((r) => !r.protected).map((r): RouteObject => ({
    path: r.path,
    element: <RouteElement module={r.module} />,
    errorElement: <ErrorFallback />,
  })),
  protectedParent(),
];

type ContentModule = {
  ContentProvider?: ComponentType<{ children: ReactNode }>;
};

const contentModules = import.meta.glob('./data/ContentContext.tsx', {
  eager: true,
}) as Record<string, ContentModule>;

type PwaModule = { default?: ComponentType };

const pwaModules = import.meta.glob('./sw/PwaStatus.tsx', {
  eager: true,
}) as Record<string, PwaModule>;

function findContentProvider(): ComponentType<{ children: ReactNode }> | null {
  for (const mod of Object.values(contentModules)) {
    if (mod.ContentProvider !== undefined) {
      return mod.ContentProvider;
    }
  }
  return null;
}

function findPwaStatus(): ComponentType | null {
  for (const mod of Object.values(pwaModules)) {
    if (mod.default !== undefined) {
      return mod.default;
    }
  }
  return null;
}

export default function App(): JSX.Element {
  const router = createBrowserRouter(appRoutes, {
    basename: import.meta.env.BASE_URL,
  });
  const ContentProvider = findContentProvider();
  const PwaStatus = findPwaStatus();
  let page: JSX.Element = <RouterProvider router={router} />;
  if (PwaStatus !== null) {
    const Status = PwaStatus;
    page = (
      <>
        {page}
        <Status />
      </>
    );
  }
  if (ContentProvider !== null) {
    page = <ContentProvider>{page}</ContentProvider>;
  }
  return <ErrorBoundary>{page}</ErrorBoundary>;
}
