import { readFileSync } from 'node:fs';
import { contrastRatio } from './contrast';

const css = readFileSync(new URL('../theme.css', import.meta.url), 'utf8');

const tokens = new Map<string, string>();
for (const m of css.matchAll(/--([\w-]+)\s*:\s*(#[0-9a-fA-F]{6})/g)) {
  tokens.set(m[1] as string, m[2] as string);
}

const PAIRS: [string, string][] = [
  ['c-text', 'c-bg'],
  ['c-text', 'c-surface'],
  ['c-text-muted', 'c-bg'],
  ['c-text-muted', 'c-surface'],
  ['c-on-accent', 'c-accent'],
  ['c-danger', 'c-bg'],
  ['c-score-excellent', 'c-bg'],
  ['c-score-excellent', 'c-surface'],
  ['c-score-good', 'c-bg'],
  ['c-score-good', 'c-surface'],
  ['c-score-improve', 'c-bg'],
  ['c-score-improve', 'c-surface'],
  ['c-score-repeat', 'c-bg'],
  ['c-score-repeat', 'c-surface'],
];

test('theme tokens meet AA', () => {
  for (const [fg, bg] of PAIRS) {
    const fgHex = tokens.get(fg);
    const bgHex = tokens.get(bg);
    expect(fgHex).toBeDefined();
    expect(bgHex).toBeDefined();
    expect(contrastRatio(fgHex as string, bgHex as string)).toBeGreaterThanOrEqual(
      4.5,
    );
  }
});
