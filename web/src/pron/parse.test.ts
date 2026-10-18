import miscueFixture from '../../../tests/fixtures/azure/miscue_marche.json';
import { normalizePhoneme } from './phonemeLabels';
import { parseAzureResult, PronParseError } from './parse';
import type { AzureJson, AzureWord } from './parse';

const allez: AzureJson = {
  DisplayText: 'Allez.',
  NBest: [
    {
      PronunciationAssessment: {
        AccuracyScore: 92,
        FluencyScore: 97,
        CompletenessScore: 100,
        PronScore: 94,
      },
      Words: [
        {
          Word: 'allez',
          PronunciationAssessment: { AccuracyScore: 81, ErrorType: 'None' },
          Phonemes: [
            { Phoneme: 'a', PronunciationAssessment: { AccuracyScore: 98 } },
            { Phoneme: 'l', PronunciationAssessment: { AccuracyScore: 95 } },
            { Phoneme: 'e', PronunciationAssessment: { AccuracyScore: 62 } },
          ],
        },
      ],
    },
  ],
};

const at = new Date('2026-10-14T21:04:57.216Z');

test('maps scores words and phonemes', () => {
  const r = parseAzureResult(allez, 'Allez !', 'c_0123456789abcdef', at, 1840);
  expect(r.scores).toEqual({
    pron: 94,
    accuracy: 92,
    fluency: 97,
    completeness: 100,
  });
  expect(r.words[0]).toEqual({
    word: 'allez',
    accuracy: 81,
    error_type: 'None',
    phonemes: [
      { phoneme: 'a', accuracy: 98 },
      { phoneme: 'l', accuracy: 95 },
      { phoneme: 'e', accuracy: 62 },
    ],
  });
  expect([r.recognized_text, r.reference_text, r.card_id]).toEqual([
    'Allez.',
    'Allez !',
    'c_0123456789abcdef',
  ]);
  expect(r.at).toBe('2026-10-14T21:04:57.216000Z');
  expect(r.duration_ms).toBe(1840);
  expect(r.id).toMatch(/^[0-9a-f-]{36}$/);
});

// El fixture real `miscue_marche.json` capturado por SPK-04 con audio sintético
// no trae ninguna palabra `Omission` (ADR-004 documenta esa limitación), aunque
// la aceptación de SPK-04 la exigía. Se anexa el caso a la forma real del
// fixture para probar que el parser conserva la palabra omitida con su puntaje.
test('miscue fixture keeps omission word', () => {
  const base = miscueFixture as AzureJson;
  const raw: AzureWord[] = base.NBest?.[0]?.Words ?? [];
  const omission: AzureWord = {
    Word: 'demain',
    PronunciationAssessment: { AccuracyScore: 0, ErrorType: 'Omission' },
    Phonemes: [],
  };
  const input: AzureJson = {
    ...base,
    NBest: [{ ...base.NBest?.[0], Words: [...raw, omission] }],
  };
  const r = parseAzureResult(input, 'Nous allons au marché demain.', null, at, 900);
  const words = input.NBest?.[0]?.Words ?? [];
  const i = words.findIndex(
    (w) => w.PronunciationAssessment?.ErrorType === 'Omission',
  );
  expect(i).toBeGreaterThanOrEqual(0);
  expect(r.words).toHaveLength(words.length);
  expect(r.words[i]).toMatchObject({
    word: words[i].Word,
    accuracy: words[i].PronunciationAssessment?.AccuracyScore,
    error_type: 'Omission',
  });
});

test('missing NBest throws PronParseError', () =>
  expect(() =>
    parseAzureResult({ DisplayText: '' }, 'x', null, at, 0),
  ).toThrow(PronParseError));

test('parses every azure fixture with its raw pron score and canonical phonemes', () => {
  const all = import.meta.glob('../../../tests/fixtures/azure/*.json', {
    eager: true,
    import: 'default',
  });
  expect(Object.keys(all).map((k) => k.split('/').pop())).toEqual(
    expect.arrayContaining([
      'bonjour.json',
      'beau.json',
      'enfants.json',
      'rendezvous.json',
      'restaurant.json',
      'vin.json',
      'miscue_marche.json',
    ]),
  );
  for (const raw of Object.values(all) as AzureJson[]) {
    const r = parseAzureResult(raw, 'x', null, at, 1);
    expect(r.scores.pron).toBe(raw.NBest?.[0]?.PronunciationAssessment?.PronScore);
    for (const p of r.words.flatMap((w) => w.phonemes)) {
      expect(p.phoneme).toBe(normalizePhoneme(p.phoneme));
    }
  }
});
