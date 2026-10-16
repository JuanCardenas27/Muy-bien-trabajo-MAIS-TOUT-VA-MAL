import { describe, expect, test } from 'vitest';
import { pwaOptions } from './pwaConfig';

type Matcher = {
  urlPattern: unknown;
  handler: string;
  options?: { expiration?: { maxEntries?: number } };
};
type UrlCallback = (ctx: { url: URL }) => boolean;

const match = (entry: Matcher, href: string): boolean =>
  (entry.urlPattern as UrlCallback)({ url: new URL(href) });

describe('pwaOptions', () => {
  test('caches bins cache-first and manifest network-first, same-origin or Worker', () => {
    const runtime = pwaOptions.workbox!.runtimeCaching!;
    const bins = runtime[0] as unknown as Matcher;
    const manifest = runtime[1] as unknown as Matcher;
    const bin = 'a'.repeat(32) + '.bin';

    expect(match(bins, 'https://u.github.io/repo/demo/data/d/' + bin)).toBe(
      true,
    );
    expect(match(bins, 'https://frances-data.x.workers.dev/d/' + bin)).toBe(
      true,
    );
    expect(match(bins, 'https://frances-data.x.workers.dev/bundle.json')).toBe(
      false,
    );
    expect(bins.handler).toBe('CacheFirst');
    expect(bins.options?.expiration?.maxEntries).toBe(2000);

    expect(
      match(manifest, 'https://frances-data.x.workers.dev/bundle.json'),
    ).toBe(true);
    expect(match(manifest, 'https://u.github.io/repo/data/bundle.json')).toBe(
      true,
    );
    expect(manifest.handler).toBe('NetworkFirst');

    expect(
      pwaOptions.workbox!.navigateFallbackDenylist!.some((r) =>
        r.test('/repo/demo/'),
      ),
    ).toBe(true);
    expect(pwaOptions.manifest && pwaOptions.manifest.name).toBe(
      'Français — Estudio',
    );
    expect(pwaOptions.registerType).toBe('prompt');
    expect(pwaOptions.workbox!.clientsClaim).toBe(true);
  });
});
