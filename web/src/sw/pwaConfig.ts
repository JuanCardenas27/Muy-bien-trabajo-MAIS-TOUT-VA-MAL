// Configuración de la PWA offline (Task WEB-12).
//
// El service worker usa la estrategia `generateSW` de Workbox: precachea el
// shell (JS/CSS/HTML/SVG) y cachea en runtime los `d/<id>.bin` (cache-first,
// inmutables por contenido) y `bundle.json` (network-first, para detectar
// versiones nuevas). Los `urlPattern` son funciones sobre `url.pathname`, así
// valen igual cuando los datos vienen del mismo origen (demo) o del Worker de
// OPS-09 (app real). El `navigateFallbackDenylist` deja fuera `data/` y el
// subdirectorio `demo/`, que publica su propio service worker (OPS-06).

import type { VitePWAOptions } from 'vite-plugin-pwa';

const BIN_PATTERN = /\/d\/[0-9a-f]{32}\.bin$/;
const MANIFEST_PATTERN = /\/bundle\.json$/;

export const pwaOptions: Partial<VitePWAOptions> = {
  strategies: 'generateSW',
  registerType: 'prompt',
  manifest: {
    name: 'Français — Estudio',
    short_name: 'Français',
    description: 'Estudio offline de francés con fichas, audio y repaso.',
    lang: 'es',
    start_url: '.',
    scope: '.',
    display: 'standalone',
    background_color: '#ffffff',
    theme_color: '#1d4ed8',
    icons: [
      {
        src: 'icon.svg',
        sizes: 'any',
        type: 'image/svg+xml',
        purpose: 'any',
      },
    ],
  },
  workbox: {
    globPatterns: ['**/*.{js,css,html,svg,mjs}'],
    globIgnores: ['**/data/**'],
    navigateFallback: 'index.html',
    navigateFallbackDenylist: [/\/data\//, /\/demo\//],
    clientsClaim: true,
    skipWaiting: false,
    runtimeCaching: [
      {
        urlPattern: ({ url }) => BIN_PATTERN.test(url.pathname),
        handler: 'CacheFirst',
        options: {
          cacheName: 'frances-bins',
          expiration: {
            maxEntries: 2000,
            maxAgeSeconds: 60 * 60 * 24 * 365,
          },
        },
      },
      {
        urlPattern: ({ url }) => MANIFEST_PATTERN.test(url.pathname),
        handler: 'NetworkFirst',
        options: {
          cacheName: 'frances-manifest',
          networkTimeoutSeconds: 10,
          expiration: { maxEntries: 4 },
        },
      },
    ],
  },
};
