// Etiquetas canónicas de fonemas fr-FR (Task PRN-01).
//
// La etiqueta canónica es IPA en forma NFC (R-11). Esta tabla se transcribe a
// mano de ADR-004 (`docs/decisions/ADR-004-azure-phonemes.md`), la única fuente
// de verdad compartida con CRD-06 (`ESPEAK_TO_AZURE`). Se usa para normalizar
// la etiqueta cruda que devuelve Azure a la misma etiqueta que
// `CardOut.phonemes`, `DrillDeck.phoneme`, `PhonemeStat.phoneme` y `SEED_WEAK`.

export const PHONEME_LABELS: Readonly<Record<string, string>> = {
  // Vocales orales (12)
  a: 'a',
  ɑ: 'ɑ',
  e: 'e',
  ɛ: 'ɛ',
  i: 'i',
  o: 'o',
  ɔ: 'ɔ',
  u: 'u',
  y: 'y',
  ø: 'ø',
  œ: 'œ',
  ə: 'ə',
  // Vocales nasales (4)
  ɑ̃: 'ɑ̃',
  ɔ̃: 'ɔ̃',
  ɛ̃: 'ɛ̃',
  œ̃: 'œ̃',
  // Consonantes (18)
  p: 'p',
  b: 'b',
  t: 't',
  d: 'd',
  k: 'k',
  ɡ: 'ɡ',
  f: 'f',
  v: 'v',
  s: 's',
  z: 'z',
  ʃ: 'ʃ',
  ʒ: 'ʒ',
  m: 'm',
  n: 'n',
  ɲ: 'ɲ',
  ŋ: 'ŋ',
  l: 'l',
  ʁ: 'ʁ',
  // Semivocales (3)
  j: 'j',
  w: 'w',
  ɥ: 'ɥ',
};

// Devuelve la etiqueta canónica (IPA en NFC, R-11): aplica NFC y, si el
// resultado está en la tabla, lo sustituye; si no, devuelve el propio NFC.
export function normalizePhoneme(label: string): string {
  const nfc = label.normalize('NFC');
  return PHONEME_LABELS[nfc] ?? nfc;
}
