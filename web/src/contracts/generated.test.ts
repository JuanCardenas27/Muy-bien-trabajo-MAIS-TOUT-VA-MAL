import type { BundleManifest, ContentIndex } from './generated';

it('ContentIndex accepts a minimal demo index', () => {
  const idx: ContentIndex = {
    schema_version: 1,
    generated_at: '2026-10-14T15:20:24.000000Z',
    courses: [],
    topics: [],
    items: [],
    attachments: [],
    cards: [],
    sheets: [],
    voices: [],
    drills: [],
    speech: null,
  };
  const m: Pick<BundleManifest, 'format'> = { format: 'FRB1' };
  expect(idx.cards).toEqual([]);
  expect(m.format).toBe('FRB1');
});
