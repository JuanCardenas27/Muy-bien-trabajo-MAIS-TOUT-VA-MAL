import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { pwaOptions } from './src/sw/pwaConfig';

declare const process: { env: Record<string, string | undefined> };

export default defineConfig({
  base: process.env['VITE_BASE'] ?? '/',
  plugins: [react(), VitePWA(pwaOptions)],
  test: {
    environment: 'jsdom',
    globals: true,
  },
});
