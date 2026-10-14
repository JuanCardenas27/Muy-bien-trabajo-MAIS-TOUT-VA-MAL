# Evaluación de pronunciación -- Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Lee `AGENTS.md` antes de tomar una tarea.

**Goal:** Practicar cualquier tarjeta en voz alta, recibir puntajes de Azure Pronunciation Assessment por frase, palabra y fonema, y seguir la evolución por fonema (EMA) con taladro de los fonemas débiles. Línea base real: 94 global; débiles /ɑ̃/, la /e/ de «allez» y /ʁ/.

**Architecture:** Módulos puros en `web/src/pron/` (parser, estadística, cuota, taladro) probados sin red; un `Recognizer` que carga el SDK de Azure de forma perezosa y una máquina de estados del grabador sin React; pantallas `Practice`, `Drill` y `Progress` que componen esas piezas y persisten en IndexedDB (stores `attempts`, `phoneme_stats`, `usage` de `web/src/db/idb.ts`).

**Tech Stack:** TypeScript strict, React, `microsoft-cognitiveservices-speech-sdk` (import dinámico), `idb`, vitest + jsdom + `@testing-library/react`, `fake-indexeddb/auto`.

**Spec:** `docs/superpowers/specs/2026-10-14-frances-classroom-design.md` (§6.7, §6.8, §7)

Plan maestro: docs/superpowers/plans/2026-10-14-00-master-plan.md (Global Constraints y contratos aplican a todas las tareas)

## Restricciones del subsistema

- El audio del usuario solo va a Azure Speech (recurso `frances-speech`, tier F0, región `eastus` por defecto, leída de `index.speech.region`). Nunca se escribe a disco, a IndexedDB ni a otro endpoint.
- Los intentos (`PronResult`) y la estadística por fonema se guardan solo localmente en IndexedDB; salen del dispositivo únicamente por la exportación manual de WEB-11.
- El SDK se carga de forma perezosa: `microsoft-cognitiveservices-speech-sdk` solo con `import()` dentro de `assess`; ningún import estático en `web/src/**`.
- Locale `fr-FR` siempre (`SpeechCredentials.locale`), `HundredMark`, granularidad `Phoneme`, `enableMiscue = true`.
- En vitest `fetch` y el SDK siempre mockeados. Toda grabación arranca desde un gesto del usuario (Safari iOS).
- UI en español; texto en francés dentro de `lang="fr"`; cada color de puntaje va con texto.
- Las cadenas de P06 son constantes exportadas en su propio módulo (`RECORDER_MESSAGES` en `recorder.ts`, `QUOTA_MESSAGES` en `quota.ts`, `SCORE_LABEL` y `ERROR_LABEL` en `ui/pron/score.ts`); no van a `es.ts` de WEB-01 (R-18).
- Fonemas: la etiqueta canónica es IPA en NFC (R-11). `CardOut.phonemes`, `DrillDeck.phoneme`, `PhonemeStat.phoneme`, `SEED_WEAK` y los fonemas de `PronResult` usan siempre esa etiqueta.

## Review Focus

- Ítem 5 del plan maestro: micrófono denegado o Safari iOS sin permisos → mensaje claro en español, sin pantalla rota. Test: PRN-02 `mic denied moves to error state with message`.


### Task PRN-01: Parser del JSON de Azure → PronResult

Deps: [FND-02, SPK-04]

**Files:**
- Create: `web/src/pron/parse.ts`, `web/src/pron/phonemeLabels.ts` (owns de PRN-01 por R-10)
- Test: `web/src/pron/parse.test.ts`, `web/src/pron/phonemeLabels.test.ts`

**Interfaces:**
- Consumes: `PronResult`, `ErrorType` de `web/src/contracts/generated.ts` (FND-02); `tests/fixtures/azure/{bonjour,beau,enfants,rendezvous,restaurant,vin,miscue_marche}.json` (R-22) y la tabla de etiquetas de `docs/decisions/ADR-004-azure-phonemes.md` (SPK-04).
- Produces:
  - `export function parseAzureResult(json: unknown, referenceText: string, cardId: string | null, at: Date, durationMs: number): PronResult`
  - `export class PronParseError extends Error`; `export function normTs(at: Date): string` (`YYYY-MM-DDTHH:MM:SS.ffffffZ`)
  - `phonemeLabels.ts`: `export const PHONEME_LABELS: Readonly<Record<string, string>>`; `export function normalizePhoneme(label: string): string` — devuelve la etiqueta canónica (IPA en NFC, R-11) según la tabla de ADR-004, la misma que CRD-06 aplica a espeak; es la etiqueta de `CardOut.phonemes`, `DrillDeck.phoneme`, `PhonemeStat.phoneme` y `SEED_WEAK`

- [ ] **Step 1: Write the failing tests**

```ts
// parse.test.ts — import miscue from "../../../tests/fixtures/azure/miscue_marche.json"
const allez = { DisplayText: "Allez.", NBest: [{ PronunciationAssessment:
  { AccuracyScore: 92, FluencyScore: 97, CompletenessScore: 100, PronScore: 94 },
  Words: [{ Word: "allez", PronunciationAssessment: { AccuracyScore: 81, ErrorType: "None" },
    Phonemes: [["a", 98], ["l", 95], ["e", 62]].map(([p, s]) => ({ Phoneme: p, PronunciationAssessment: { AccuracyScore: s } })) }] }] };
const at = new Date("2026-10-14T21:04:57.216Z");
test("maps scores words and phonemes", () => {
  const r = parseAzureResult(allez, "Allez !", "c_0123456789abcdef", at, 1840);
  expect(r.scores).toEqual({ pron: 94, accuracy: 92, fluency: 97, completeness: 100 });
  expect(r.words[0]).toEqual({ word: "allez", accuracy: 81, error_type: "None",
    phonemes: [{ phoneme: "a", accuracy: 98 }, { phoneme: "l", accuracy: 95 }, { phoneme: "e", accuracy: 62 }] });
  expect([r.recognized_text, r.reference_text, r.card_id]).toEqual(["Allez.", "Allez !", "c_0123456789abcdef"]);
  expect(r.at).toBe("2026-10-14T21:04:57.216000Z"); expect(r.duration_ms).toBe(1840);
  expect(r.id).toMatch(/^[0-9a-f-]{36}$/);
});
test("miscue fixture keeps omission word", () => { // tests/fixtures/azure/miscue_marche.json (R-22)
  const raw = (miscue as AzureJson).NBest[0].Words, r = parseAzureResult(miscue, "x", null, at, 900);
  const i = raw.findIndex((w) => w.PronunciationAssessment.ErrorType === "Omission"); expect(i).toBeGreaterThanOrEqual(0);
  expect(r.words).toHaveLength(raw.length);
  expect(r.words[i]).toMatchObject({ word: raw[i].Word, accuracy: raw[i].PronunciationAssessment.AccuracyScore, error_type: "Omission" });
});
test("missing NBest throws PronParseError", () => expect(() => parseAzureResult({ DisplayText: "" }, "x", null, at, 0)).toThrow(PronParseError));
test("parses every azure fixture with its raw pron score and canonical phonemes", () => {
  const all = import.meta.glob("../../../tests/fixtures/azure/*.json", { eager: true, import: "default" });
  expect(Object.keys(all).map((k) => k.split("/").pop())).toEqual(expect.arrayContaining(["bonjour.json", "beau.json",
    "enfants.json", "rendezvous.json", "restaurant.json", "vin.json", "miscue_marche.json"]));
  for (const raw of Object.values(all) as AzureJson[]) {
    const r = parseAzureResult(raw, "x", null, at, 1); expect(r.scores.pron).toBe(raw.NBest[0].PronunciationAssessment.PronScore);
    for (const p of r.words.flatMap((w) => w.phonemes)) expect(p.phoneme).toBe(normalizePhoneme(p.phoneme));
  }
});
// phonemeLabels.test.ts
test("table entries normalize to their canonical label", () => { for (const [k, v] of Object.entries(PHONEME_LABELS)) expect(normalizePhoneme(k)).toBe(v); });
test("seed phonemes are fixed points", () => { for (const p of ["ɑ̃", "e", "ʁ"]) expect(normalizePhoneme(p)).toBe(p); });
```

- [ ] **Step 2: Run tests to verify they fail** — Run: `npm --prefix web test -- src/pron/parse.test.ts src/pron/phonemeLabels.test.ts` → Expected: FAIL with "Failed to resolve import "./parse""

- [ ] **Step 3: Implement `normalizePhoneme(label: string): string` in `web/src/pron/phonemeLabels.ts` and `parseAzureResult(...)` in `web/src/pron/parse.ts`** — `PHONEME_LABELS` se transcribe a mano de la tabla de ADR-004 (etiqueta cruda de Azure → IPA canónico en NFC; la misma tabla que usa CRD-06, R-11); `normalizePhoneme` aplica NFC, luego la tabla, y si no está devuelve la etiqueta NFC. El parser lee `NBest[0].PronunciationAssessment`, `NBest[0].Words[]` y `DisplayText`; cada `Phoneme` pasa por `normalizePhoneme`; `ErrorType` ausente → `"None"`; `Phonemes` ausente → `[]`; `id = crypto.randomUUID()`; `normTs` extiende los milisegundos de `toISOString()` a 6 decimales.

- [ ] **Step 4: Run tests to verify they pass** — Run: `npm --prefix web test -- src/pron/parse.test.ts src/pron/phonemeLabels.test.ts` → Expected: PASS (6 tests)

- [ ] **Step 5: Commit** — `git add web/src/pron/parse.ts web/src/pron/parse.test.ts web/src/pron/phonemeLabels.ts web/src/pron/phonemeLabels.test.ts && git commit -m "feat(pron): parse Azure pronunciation JSON into PronResult [PRN-01]"`

### Task PRN-04: Intentos + estadística EMA por fonema + debilidades

Deps: [PRN-01, WEB-01]

**Files:**
- Create: `web/src/pron/attempts.ts`, `web/src/pron/stats.ts`
- Test: `web/src/pron/attempts.test.ts`, `web/src/pron/stats.test.ts`

**Interfaces:**
- Consumes: `openFrancesDb(): Promise<IDBPDatabase<FrancesDb>>` (WEB-01; stores `attempts`, `phoneme_stats`); `normalizePhoneme` (PRN-01).
- Produces:
  - `export async function saveAttempt(result: PronResult): Promise<void>`; `export async function listAttempts(opts?: { cardId?: string; since?: string; limit?: number }): Promise<PronResult[]>` (más reciente primero)
  - `export interface PhonemeStat { phoneme: string; ema: number; n: number; last_at: string }`
  - `export function updateStats(stats: PhonemeStat[], result: PronResult, alpha = 0.3): PhonemeStat[]` (pura); `export function weakPhonemes(stats: PhonemeStat[], seed: string[], n: number): string[]`
  - `export async function loadStats(): Promise<PhonemeStat[]>`; `export async function saveStats(stats: PhonemeStat[]): Promise<void>` (los consume WEB-05 para leer las estadísticas, R-17)
  - `export const SEED_WEAK = ["ɑ̃", "e", "ʁ"]` (etiquetas canónicas IPA NFC, R-11), `WEAK_MIN_N = 3`, `WEAK_MAX_EMA = 80`, `BASELINE = { pron: 94, date: "2026-10-14", weak: SEED_WEAK }`

- [ ] **Step 1: Write the failing tests**

```ts
// stats.test.ts — helper result(at, [[phoneme, accuracy], ...]) arma un PronResult de una palabra
test("ema first observation then alpha 0.3", () => {
  let s = updateStats([], result("2026-10-14T21:00:00.000000Z", [["ʁ", 60]]));
  expect(s).toEqual([{ phoneme: "ʁ", ema: 60, n: 1, last_at: "2026-10-14T21:00:00.000000Z" }]);
  s = updateStats(s, result("2026-10-14T21:01:00.000000Z", [["ʁ", 80]])); expect(s[0].ema).toBeCloseTo(66, 10); expect(s[0].n).toBe(2);
  expect(updateStats(s, result("x", [["ʁ", 80]]), 0.5)[0].ema).toBeCloseTo(73, 10);
});
test("phoneme repeated in one attempt is averaged before ema", () => {
  expect(updateStats([], result("t", [["e", 50], ["e", 70]]))[0]).toMatchObject({ phoneme: "e", ema: 60, n: 1 });
});
test("weak requires n >= 3 and ema < 80 sorted ascending", () => {
  const st = (phoneme: string, ema: number, n: number) => ({ phoneme, ema, n, last_at: "" });
  expect(weakPhonemes([st("ɔ̃", 70, 3), st("y", 50, 2), st("ɛ̃", 65, 4), st("u", 80, 9)], [], 5)).toEqual(["ɛ̃", "ɔ̃"]);
});
test("weak fills with seed in order without repeats", () => {
  expect(weakPhonemes([{ phoneme: "ʁ", ema: 55, n: 3, last_at: "" }], SEED_WEAK, 3)).toEqual(["ʁ", "ɑ̃", "e"]);
  expect(weakPhonemes([], SEED_WEAK, 2)).toEqual(["ɑ̃", "e"]);
});
// attempts.test.ts (import "fake-indexeddb/auto")
test("save and list attempts newest first with filters", async () => {
  await saveAttempt(r1 /* c_a, 2026-10-14T20:00:00.000000Z */); await saveAttempt(r2 /* c_b, 21:00 */);
  expect((await listAttempts()).map((r) => r.id)).toEqual([r2.id, r1.id]);
  expect((await listAttempts({ cardId: "c_a" })).map((r) => r.id)).toEqual([r1.id]);
  expect(await listAttempts({ since: "2026-10-14T20:30:00.000000Z" })).toHaveLength(1);
  expect(await listAttempts({ limit: 1 })).toHaveLength(1);
});
test("stats roundtrip through phoneme_stats", async () => {
  const s = [{ phoneme: "ɑ̃", ema: 71.5, n: 3, last_at: "2026-10-14T21:00:00.000000Z" }]; await saveStats(s); expect(await loadStats()).toEqual(s);
});
```

- [ ] **Step 2: Run tests to verify they fail** — Run: `npm --prefix web test -- src/pron/stats.test.ts src/pron/attempts.test.ts` → Expected: FAIL with "Failed to resolve import "./stats""

- [ ] **Step 3: Implement `updateStats`, `weakPhonemes`, `loadStats`, `saveStats` in `web/src/pron/stats.ts` and `saveAttempt`, `listAttempts` in `web/src/pron/attempts.ts`** — Por intento: agrupar los fonemas de todas las palabras por `normalizePhoneme`, promediar `accuracy` → `x`; `ema = n === 0 ? x : alpha * x + (1 - alpha) * ema`; `n + 1`; `last_at = result.at`. `listAttempts` recorre el índice `at` (o `card_id` si se filtra) con cursor `prev`.

- [ ] **Step 4: Run tests to verify they pass** — Run: `npm --prefix web test -- src/pron/stats.test.ts src/pron/attempts.test.ts` → Expected: PASS (6 tests)

- [ ] **Step 5: Commit** — `git add web/src/pron/attempts.ts web/src/pron/attempts.test.ts web/src/pron/stats.ts web/src/pron/stats.test.ts && git commit -m "feat(pron): attempts store and per-phoneme EMA stats [PRN-04]"`

### Task PRN-02: Recognizer Azure + máquina de estados del grabador

Deps: [PRN-01, WEB-03]

**Files:**
- Create: `web/src/pron/recognizer.ts`, `web/src/pron/recorder.ts`
- Test: `web/src/pron/recognizer.test.ts`, `web/src/pron/recorder.test.ts`

**Interfaces:**
- Consumes: `SpeechCredentials` (FND-02, vía `useContent().index.speech` de WEB-03); `parseAzureResult`, `PronParseError` (PRN-01).
- Produces:
  - `Recognizer`, `createAzureRecognizer(creds)`, `getRecognizer(creds)` con las firmas exactas del plan maestro
  - `export class RecognizerError extends Error { code: "no_match" | "unauthorized" | "quota" | "canceled" }`; `export type RecorderState = { status: "idle" | "requesting_mic" | "recording" | "scoring" } | { status: "done"; result: PronResult } | { status: "error"; message: string }`
  - `export interface Recorder { getState(): RecorderState; subscribe(fn: (s: RecorderState) => void): () => void; start(referenceText: string, cardId: string | null): Promise<void>; abort(): void }`
  - `export function createRecorder(recognizer: Recognizer, getUserMedia?: (c: MediaStreamConstraints) => Promise<MediaStream>, now?: () => Date): Recorder`; `export const RECORDER_MESSAGES` (los seis textos de error, constante exportada de `recorder.ts`, R-18)

- [ ] **Step 1: Write the failing tests**

```ts
// recorder.test.ts — okGum resuelve un MediaStream falso con getTracks() → [{ stop }]
test("mic denied moves to error state with message", async () => {
  const rec = { assess: vi.fn() }, seen: string[] = [];
  const r = createRecorder(rec, () => Promise.reject(new DOMException("denied", "NotAllowedError")));
  r.subscribe((s) => seen.push(s.status)); await r.start("Bonjour", null); expect(seen).toEqual(["requesting_mic", "error"]);
  expect(r.getState()).toEqual({ status: "error",
    message: "Permiso de micrófono denegado: actívalo en la configuración del navegador" });
  expect(rec.assess).not.toHaveBeenCalled();
});
test("no microphone and no mediaDevices messages", async () => {
  const nf = createRecorder({ assess: vi.fn() }, () => Promise.reject(new DOMException("x", "NotFoundError")));
  await nf.start("Bonjour", null); expect(nf.getState()).toEqual({ status: "error", message: "No se encontró micrófono" });
  vi.stubGlobal("navigator", {}); const none = createRecorder({ assess: vi.fn() });
  await none.start("Bonjour", null); expect(none.getState()).toEqual({ status: "error", message: "Este navegador no permite grabar aquí" });
});
test("happy path goes to done with parsed result and stops tracks", async () => {
  const r = createRecorder({ assess: async () => ({ json: allez, durationMs: 1840 }) }, okGum,
    () => new Date("2026-10-14T21:04:57.216Z"));
  const seen: string[] = []; r.subscribe((s) => seen.push(s.status)); await r.start("Allez !", "c_0123456789abcdef");
  expect(seen).toEqual(["requesting_mic", "recording", "scoring", "done"]); expect(stop).toHaveBeenCalled();
  const s = r.getState(); expect(s.status === "done" && s.result.scores.pron).toBe(94);
});
test.each([["no_match", "No se escuchó nada, intenta de nuevo"], ["unauthorized", "Clave de Azure inválida"],
  ["quota", "Cuota de Azure agotada por ahora"]] as const)("recognizer %s maps to message", async (code, message) => {
  const r = createRecorder({ assess: () => Promise.reject(new RecognizerError(code)) }, okGum);
  await r.start("Bonjour", null); expect(r.getState()).toEqual({ status: "error", message });
});
test("abort returns to idle and aborts the signal", async () => {
  let sig: AbortSignal | undefined;
  const r = createRecorder({ assess: (_t, s) => { sig = s; return new Promise(() => {}); } }, okGum);
  void r.start("Bonjour", null); await vi.waitFor(() => expect(r.getState().status).toBe("recording"));
  r.abort(); expect(sig?.aborted).toBe(true); expect(r.getState()).toEqual({ status: "idle" });
});
// recognizer.test.ts — vi.mock("microsoft-cognitiveservices-speech-sdk", factory) que cuenta sdkLoads
const creds = { region: "eastus", key: "k", locale: "fr-FR" } as const;
test("loads speech sdk lazily", async () => {
  const rec = createAzureRecognizer(creds); expect(sdkLoads).toBe(0);
  await rec.assess("Bonjour"); expect(sdkLoads).toBe(1);
});
test("configures fr-FR hundred mark phoneme miscue and converts ticks", async () => {
  mockRecognized({ duration: 18_400_000, json: "{}" });
  expect((await createAzureRecognizer(creds).assess("Bonjour")).durationMs).toBe(1840);
  expect(fromSubscription).toHaveBeenCalledWith("k", "eastus"); expect(speechConfig.speechRecognitionLanguage).toBe("fr-FR");
  expect(PronunciationAssessmentConfig).toHaveBeenCalledWith("Bonjour", HundredMark, Phoneme, true);
});
test("canceled and no match map to error codes", async () => {
  for (const [mock, code] of [[() => mockCanceled(401), "unauthorized"], [() => mockCanceled(429), "quota"],
                              [mockNoMatch, "no_match"]] as const) {
    mock(); await expect(createAzureRecognizer(creds).assess("x")).rejects.toMatchObject({ code });
  }
});
test("getRecognizer uses e2e fake only when VITE_E2E is 1", () => {
  const fake = { assess: vi.fn() }; Object.assign(window, { __francesFakeRecognizer: fake });
  vi.stubEnv("VITE_E2E", "1"); expect(getRecognizer(null)).toBe(fake);
  vi.stubEnv("VITE_E2E", "0"); expect(getRecognizer(null)).toBeNull();
});
```

- [ ] **Step 2: Run tests to verify they fail** — Run: `npm --prefix web test -- src/pron/recorder.test.ts src/pron/recognizer.test.ts` → Expected: FAIL with "Failed to resolve import "./recorder""

- [ ] **Step 3: Implement `createAzureRecognizer`, `getRecognizer` in `web/src/pron/recognizer.ts` and `createRecorder` in `web/src/pron/recorder.ts`** — `assess`: `await import("microsoft-cognitiveservices-speech-sdk")`, `SpeechConfig.fromSubscription(key, region)`, `speechRecognitionLanguage = creds.locale`, `AudioConfig.fromDefaultMicrophoneInput()`, `new PronunciationAssessmentConfig(referenceText, HundredMark, Phoneme, true).applyTo(recognizer)`, `recognizeOnceAsync`; `json = JSON.parse(result.properties.getProperty(PropertyId.SpeechServiceResponse_JsonResult))`, `durationMs = result.duration / 10000`. `ResultReason.NoMatch` → `no_match`; cancelación por autenticación (401) → `unauthorized`; `TooManyRequests` (429) → `quota`; resto → `canceled` («No se pudo evaluar, intenta de nuevo»); `signal` abortado → `recognizer.close()`. `createRecorder` toma por defecto `navigator.mediaDevices?.getUserMedia` enlazado (ausente → mensaje de navegador), pide `{ audio: true }`, detiene las pistas, `recording` mientras corre `assess`, `scoring` durante `parseAzureResult(json, ref, cardId, now(), durationMs)`, luego `done`; `PronParseError` → `canceled`.

- [ ] **Step 4: Run tests to verify they pass** — Run: `npm --prefix web test -- src/pron/recorder.test.ts src/pron/recognizer.test.ts` → Expected: PASS (11 tests)

- [ ] **Step 5: Commit** — `git add web/src/pron/recognizer.ts web/src/pron/recognizer.test.ts web/src/pron/recorder.ts web/src/pron/recorder.test.ts && git commit -m "feat(pron): lazy Azure recognizer and recorder state machine [PRN-02]"`

### Task PRN-06: Medidor de cuota F0 (5 h/mes, aviso a 4 h)

Deps: [PRN-04]

**Files:**
- Create: `web/src/pron/quota.ts`
- Test: `web/src/pron/quota.test.ts`

**Interfaces:**
- Consumes: `openFrancesDb()` (WEB-01; store `usage`, keyPath `month`).
- Produces:
  - `export const QUOTA_SECONDS = 18000`, `export const WARN_SECONDS = 14400`; `export function monthOf(now: Date): string` (`"YYYY-MM"` en America/Bogota); `export function secondsOf(durationMs: number): number` (`Math.ceil(durationMs / 1000)`)
  - `export async function addSeconds(month: string, s: number): Promise<number>` (total nuevo; registro `{ month, pron_seconds }`); `export async function getUsage(month: string): Promise<number>` (0 si no existe)
  - `export function quotaState(usageSeconds: number): "ok" | "warn" | "exceeded"`; `export const QUOTA_MESSAGES = { warn: "Llevas 4 h de las 5 h gratis de este mes", exceeded: "Es probable que Azure rechace los intentos hasta el próximo mes" }` (constante exportada de `quota.ts`, R-18)

- [ ] **Step 1: Write the failing tests**

```ts
test("quota state boundaries", () =>
  expect([0, 14399, 14400, 17999, 18000].map(quotaState)).toEqual(["ok", "ok", "warn", "warn", "exceeded"]));
test("month rolls over in Bogota not UTC", () => {
  expect([monthOf(new Date("2026-11-01T04:59:59Z")), monthOf(new Date("2026-11-01T05:00:00Z"))]).toEqual(["2026-10", "2026-11"]);
});
test("seconds round up", () => { expect([secondsOf(1840), secondsOf(2000), secondsOf(2001)]).toEqual([2, 2, 3]); });
test("addSeconds accumulates per month", async () => { // import "fake-indexeddb/auto"
  expect(await getUsage("2026-10")).toBe(0); expect(await addSeconds("2026-10", 14000)).toBe(14000);
  expect(await addSeconds("2026-10", 400)).toBe(14400); expect(await getUsage("2026-11")).toBe(0);
});
```

- [ ] **Step 2: Run test to verify it fails** — Run: `npm --prefix web test -- src/pron/quota.test.ts` → Expected: FAIL with "Failed to resolve import "./quota""

- [ ] **Step 3: Implement the `quota.ts` exports above** — `monthOf` con `Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota", year: "numeric", month: "2-digit" })`; `addSeconds` lee y escribe en una sola transacción `readwrite` del store `usage`.

- [ ] **Step 4: Run test to verify it passes** — Run: `npm --prefix web test -- src/pron/quota.test.ts` → Expected: PASS (4 tests)

- [ ] **Step 5: Commit** — `git add web/src/pron/quota.ts web/src/pron/quota.test.ts && git commit -m "feat(pron): monthly F0 speech quota meter [PRN-06]"`

### Task PRN-03: Pantalla Práctica: escuchar, grabar, puntajes por palabra/fonema

Deps: [PRN-02, PRN-04, PRN-06, WEB-10]

**Files:**
- Create: `web/src/routes/Practice.tsx`, `web/src/ui/pron/score.ts`, `web/src/ui/pron/ScoreSummary.tsx`, `web/src/ui/pron/WordList.tsx`, `web/src/ui/pron/PracticeSession.tsx`
- Test: `web/src/ui/pron/score.test.ts`, `web/src/ui/pron/PracticeSession.test.tsx`, `web/src/routes/Practice.test.tsx`

**Interfaces:**
- Consumes: `useContent()` (WEB-03); `AudioPlayer` (WEB-10); `getRecognizer`, `createRecorder` (PRN-02); `saveAttempt`, `loadStats`, `saveStats`, `updateStats` (PRN-04); `monthOf`, `secondsOf`, `addSeconds`, `getUsage`, `quotaState`, `QUOTA_MESSAGES` (PRN-06, dep por R-10).
- Produces:
  - `score.ts`: `export type ScoreBand = "excelente" | "bien" | "mejorable" | "repetir"`; `export function scoreBand(score: number): ScoreBand`; `SCORE_LABEL: Record<ScoreBand, string>`; `ERROR_LABEL: Record<ErrorType, string | null>` (constantes exportadas de `score.ts`, R-18)
  - `export function PracticeSession(props: { card: CardOut; recognizer: Recognizer | null; onFinished?: (r: PronResult) => void; onNext?: () => void }): JSX.Element`; `export default function Practice(): JSX.Element` (ruta `/practice/:cardId`)
  - Nombres accesibles usados por WEB-13: `button` «Grabar» (mientras graba, «Detener»); `region` «Puntaje global» (contiene el número y la banda de `SCORE_LABEL`); un `button` por palabra con el nombre exacto de la palabra; `list` «Fonemas de <palabra>» con un `listitem` por fonema; `button` «Siguiente»; en PRN-05, `heading` nivel 1 «Taladro /<fonema>/». El enlace «Practicar /<fonema>/» hacia `/drill/:phoneme` es de WEB-05.

- [ ] **Step 1: Write the failing tests**

```ts
// score.test.ts
test("score bands and labels", () => {
  expect([90, 89.5, 75, 74.9, 60, 59.9].map(scoreBand)).toEqual(["excelente", "bien", "bien", "mejorable", "mejorable", "repetir"]);
  expect(SCORE_LABEL).toEqual({ excelente: "Excelente", bien: "Bien", mejorable: "Mejorable", repetir: "A repetir" });
  expect([ERROR_LABEL.Omission, ERROR_LABEL.Mispronunciation, ERROR_LABEL.Insertion, ERROR_LABEL.None])
    .toEqual(["omitida", "mal pronunciada", "insertada", null]);
});
// PracticeSession.test.tsx — fakeRec devuelve el JSON «allez» de PRN-01 + una palabra Omission; fake-indexeddb/auto
test("renders scores words and phoneme chips from result", async () => {
  render(<PracticeSession card={card} recognizer={fakeRec} />);
  await user.click(screen.getByRole("button", { name: "Grabar" }));
  const total = await screen.findByRole("region", { name: "Puntaje global" });
  expect(within(total).getByText("94")).toBeInTheDocument(); expect(within(total).getByText("Excelente")).toBeInTheDocument();
  for (const t of ["Exactitud 92", "Fluidez 97", "Completitud 100", "omitida"]) expect(screen.getByText(t)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "allez" }));
  const chips = within(screen.getByRole("list", { name: "Fonemas de allez" })).getAllByRole("listitem");
  expect(chips.map((c) => c.textContent)).toEqual(["a 98", "l 95", "e 62"]);
  expect(screen.getByRole("button", { name: "Siguiente" })).toBeInTheDocument();
});
test("finishing saves attempt stats and seconds", async () => { // reloj fijado en 2026-10-14T21:04:57Z
  expect(await listAttempts()).toHaveLength(1);
  expect(await loadStats()).toContainEqual(expect.objectContaining({ phoneme: "e", ema: 62, n: 1 }));
  expect(await getUsage("2026-10")).toBe(2);
});
test("space bar starts recording", async () => { await user.keyboard(" "); expect(fakeRec.assess).toHaveBeenCalledOnce(); });
// Practice.test.tsx
test("shows quota warning banner at 4 h and still allows recording", async () => {
  await addSeconds("2026-10", 14400); renderRoute("/practice/c_0123456789abcdef");
  expect(await screen.findByText("Llevas 4 h de las 5 h gratis de este mes")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Grabar" })).toBeEnabled();
});
test("front is french and model audio is present", async () => {
  renderRoute("/practice/c_0123456789abcdef");
  expect((await screen.findByText(card.front_fr)).closest("[lang]")).toHaveAttribute("lang", "fr");
  expect(screen.getByRole("button", { name: /Reproducir/ })).toBeInTheDocument();
});
test("missing speech credentials shows message", async () => expect(await screen.findByText("La evaluación de pronunciación no está disponible en este bundle")).toBeInTheDocument()); // index.speech = null
```

- [ ] **Step 2: Run tests to verify they fail** — Run: `npm --prefix web test -- src/ui/pron src/routes/Practice.test.tsx` → Expected: FAIL with "Failed to resolve import "./score""

- [ ] **Step 3: Implement `scoreBand`, `PracticeSession` and `Practice`** — `ERROR_LABEL` completa los otros tres `ErrorType` con «pausa inesperada», «falta una pausa», «monótona». `PracticeSession` crea un `Recorder` por montaje y se suscribe; botón «Grabar»/«Detener» (`abort`) y barra espaciadora; puntaje en `<section aria-label="Puntaje global">`, cada palabra como `<button lang="fr">` cuyo nombre es solo la palabra, sus fonemas en `<ul aria-label="Fonemas de <palabra>">`; estado anunciado en `aria-live="polite"`, errores en `role="alert"`. En `done`: `saveAttempt(r)`, `saveStats(updateStats(await loadStats(), r))`, `addSeconds(monthOf(new Date()), secondsOf(r.duration_ms))`, `onFinished?.(r)`; botones «Repetir» y «Siguiente». `Practice` toma la tarjeta de `index.cards` por `cardId`, el recognizer de `getRecognizer(index.speech)` y el banner de `quotaState(await getUsage(monthOf(new Date())))`.

- [ ] **Step 4: Run tests to verify they pass** — Run: `npm --prefix web test -- src/ui/pron src/routes/Practice.test.tsx` → Expected: PASS (7 tests)

- [ ] **Step 5: Commit** — `git add web/src/routes/Practice.tsx web/src/routes/Practice.test.tsx web/src/ui/pron/ && git commit -m "feat(pron): practice screen with word and phoneme scores [PRN-03]"`

### Task PRN-07: Pantalla Progreso (mapa de fonemas, historial)

Deps: [PRN-04, PRN-06]

**Files:**
- Create: `web/src/routes/Progress.tsx`
- Test: `web/src/routes/Progress.test.tsx`

**Interfaces:**
- Consumes: `loadStats`, `listAttempts`, `BASELINE` (PRN-04); `getUsage`, `monthOf`, `QUOTA_SECONDS` (PRN-06).
- Produces: `export default function Progress(): JSX.Element` (ruta `/progress`).

- [ ] **Step 1: Write the failing tests**

```ts
// fake-indexeddb: stats ʁ 58/n4, ɑ̃ 71/n3, u 93/n5; 60 intentos; usage 2026-10 = 7200; reloj 2026-10-14
test("phoneme table sorted by ema with bar and number", async () => {
  const rows = (await screen.findAllByRole("row")).slice(1).map((r) => r.textContent);
  expect(rows).toEqual([expect.stringContaining("ʁ58"), expect.stringContaining("ɑ̃71"), expect.stringContaining("u93")]);
  expect(screen.getAllByRole("meter")[0]).toHaveAttribute("aria-valuenow", "58");
});
test("shows baseline 94 with weak phonemes and monthly quota usage", async () => {
  expect(await screen.findByText("Línea base: 94 (14 oct 2026) · débiles /ɑ̃/, /e/, /ʁ/")).toBeInTheDocument();
  expect(screen.getByText("Uso de Azure este mes: 2 h 0 min de 5 h")).toBeInTheDocument();
});
test("trend chart has table alternative", async () => {
  expect(await screen.findByRole("img", { name: "Tendencia del puntaje global" })).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Tendencia del puntaje global (tabla)" })).toBeInTheDocument();
});
test("history limited to 50 attempts", async () =>
  expect(within(await screen.findByRole("list", { name: "Historial" })).getAllByRole("listitem")).toHaveLength(50));
```

- [ ] **Step 2: Run test to verify it fails** — Run: `npm --prefix web test -- src/routes/Progress.test.tsx` → Expected: FAIL with "Failed to resolve import "./Progress""

- [ ] **Step 3: Implement `Progress()` in `web/src/routes/Progress.tsx`** — Fonemas con `<meter min={0} max={100}>` más el número; tendencia como `<svg role="img">` con una polilínea de `scores.pron` de `listAttempts({ limit: 50 })` en orden cronológico, más una `<table>` visualmente oculta; fechas con `Intl.DateTimeFormat("es-CO", { timeZone: "America/Bogota" })`; los textos de referencia del historial van en `lang="fr"`.

- [ ] **Step 4: Run test to verify it passes** — Run: `npm --prefix web test -- src/routes/Progress.test.tsx` → Expected: PASS (4 tests)

- [ ] **Step 5: Commit** — `git add web/src/routes/Progress.tsx web/src/routes/Progress.test.tsx && git commit -m "feat(pron): progress screen with phoneme map and history [PRN-07]"`

### Task PRN-05: Sesión de taladro por fonema débil

Deps: [PRN-03, PRN-04]

**Files:**
- Create: `web/src/pron/drill.ts`, `web/src/routes/Drill.tsx`
- Test: `web/src/pron/drill.test.ts`, `web/src/routes/Drill.test.tsx`

**Interfaces:**
- Consumes: `ContentIndex.drills`, `ContentIndex.cards` vía `useContent()` (WEB-03); `PracticeSession` (PRN-03); `loadStats`, `PhonemeStat` (PRN-04).
- Produces:
  - `export const DRILL_SIZE = 10`; `export function deckFor(phoneme: string, index: ContentIndex): DrillDeck | null` (curado primero, si no el automático)
  - `export function buildSession(deck: DrillDeck, cards: CardOut[], day: string, size = DRILL_SIZE): CardOut[]` (`day` = `"YYYY-MM-DD"` en Bogotá; excluye `stale`)
  - `export function drillSummary(before: PhonemeStat[], after: PhonemeStat[], phoneme: string): { before: number | null; after: number | null }`; `export default function Drill(): JSX.Element` (ruta `/drill/:phoneme`; `heading` nivel 1 «Taladro /<fonema>/», nombre accesible usado por WEB-13)

- [ ] **Step 1: Write the failing tests**

```ts
// drill.test.ts — indexWith(decks) y deckOf(n, stale) construyen datos sintéticos
test("deckFor prefers curated deck", () => {
  const idx = indexWith([{ id: "d_auto", phoneme: "ɑ̃", curated: false }, { id: "d_cur", phoneme: "ɑ̃", curated: true }]);
  expect(deckFor("ɑ̃", idx)?.id).toBe("d_cur"); expect(deckFor("y", idx)).toBeNull();
  expect(deckFor("ʁ", indexWith([{ id: "d_r", phoneme: "ʁ", curated: false }]))?.id).toBe("d_r");
});
test("session is at most 10, excludes stale and is stable per day", () => {
  const { deck, cards } = deckOf(14, 2); const a = buildSession(deck, cards, "2026-10-14");
  expect(a).toHaveLength(10); expect(a.some((c) => c.stale)).toBe(false);
  expect(buildSession(deck, cards, "2026-10-14").map((c) => c.id)).toEqual(a.map((c) => c.id));
  const small = deckOf(4, 0); expect(buildSession(small.deck, small.cards, "2026-10-14")).toHaveLength(4);
});
test("summary before and after ema", () => {
  expect(drillSummary([{ phoneme: "ɑ̃", ema: 70, n: 3, last_at: "" }], [{ phoneme: "ɑ̃", ema: 73, n: 4, last_at: "" }], "ɑ̃"))
    .toEqual({ before: 70, after: 73 });
  expect(drillSummary([], [{ phoneme: "ʁ", ema: 60, n: 1, last_at: "" }], "ʁ")).toEqual({ before: null, after: 60 });
});
// Drill.test.tsx — recognizer falso; deck ɑ̃ de 2 tarjetas; stats previas ɑ̃ 70/n3; cada intento puntúa ɑ̃ 80
test("drill route decodes phoneme and finishes with summary", async () => {
  renderRoute(`/drill/${encodeURIComponent("ɑ̃")}`);
  expect(await screen.findByRole("heading", { level: 1, name: "Taladro /ɑ̃/" })).toBeInTheDocument();
  for (let i = 0; i < 2; i++) { await user.click(await screen.findByRole("button", { name: "Grabar" }));
    await user.click(await screen.findByRole("button", { name: "Siguiente" })); }
  expect(await screen.findByText("/ɑ̃/: 70 → 75,1")).toBeInTheDocument();
});
test("unknown phoneme shows empty message", async () => { renderRoute("/drill/y"); expect(await screen.findByText("No hay taladro para este fonema")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail** — Run: `npm --prefix web test -- src/pron/drill.test.ts src/routes/Drill.test.tsx` → Expected: FAIL with "Failed to resolve import "./drill""

- [ ] **Step 3: Implement `deckFor`, `buildSession`, `drillSummary` in `web/src/pron/drill.ts` and `Drill()` in `web/src/routes/Drill.tsx`**

Fisher–Yates con PRNG determinista sembrado por el día (la firma no lo fija):

```ts
let h = 2166136261; for (const ch of day) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);   // FNV-1a
const rand = () => { h = (h + 0x6d2b79f5) | 0; let t = Math.imul(h ^ (h >>> 15), 1 | h);   // mulberry32
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
```

`Drill` lee `loadStats()` al montar (antes), recorre la sesión con `PracticeSession` (`onNext`), vuelve a leer al final (después) y muestra `/<fonema>/: antes → después` con `Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 })` (70 → 73 → 75,1 con α = 0.3).

- [ ] **Step 4: Run tests to verify they pass** — Run: `npm --prefix web test -- src/pron/drill.test.ts src/routes/Drill.test.tsx` → Expected: PASS (5 tests)

- [ ] **Step 5: Commit** — `git add web/src/pron/drill.ts web/src/pron/drill.test.ts web/src/routes/Drill.tsx web/src/routes/Drill.test.tsx && git commit -m "feat(pron): weak-phoneme drill session [PRN-05]"`


## Preguntas de contrato

Resueltas en el plan maestro:

1. owns de PRN-01 (`phonemeLabels.ts`) → R-10.
2. Deps de PRN-03 (+ PRN-06) → R-10.
3. Vocabulario canónico de fonemas (IPA NFC, tabla única de ADR-004 para CRD-06 y PRN-01) → R-11.
4. Interfaces de P06 fuera de «Web: interfaces entre tareas» (`saveAttempt`, `listAttempts`, `loadStats`/`saveStats`, `SEED_WEAK`, `BASELINE`, `RecognizerError`, `RecorderState`, `createRecorder`, `quota.ts`, `PracticeSession`) → R-17 y R-27: lo declarado en Produces es contrato.
5. `normTs` → R-27: vive en `pron/parse.ts` y los demás lo importan de ahí.
6. Cadenas en español como constantes de cada módulo de P06 → R-18.
7. Nombres de fixtures de Azure → R-22; dependencias npm (`microsoft-cognitiveservices-speech-sdk`, `fake-indexeddb`, `@testing-library/react`) las agrega la tarea que las usa → R-01. Nombres accesibles para WEB-13 → R-21 (fijados en PRN-03 y PRN-05).

Ninguna abierta.

## Autorrevisión

1. Las 7 tareas están, en el orden pedido (PRN-01, PRN-04, PRN-02, PRN-06, PRN-03, PRN-07, PRN-05), cada una con `Deps:` de `tasks.yaml` y Create solo dentro de su `owns` (`phonemeLabels.ts` incluido por R-10).
2. Cada paso fija una sola cosa: tests con nombres y valores exactos (EMA 60 → 66, α 0.3, n ≥ 3, ema < 80, 14 400/18 000 s, mes en Bogotá, bandas 90/75/60, ticks/10 000), firma y archivo; solo se escribe el cuerpo del PRNG, que la firma no determina.
3. Nombres y tipos coinciden con el plan maestro (`parseAzureResult`, `Recognizer`, `createAzureRecognizer`, `getRecognizer`, `PhonemeStat`, `updateStats`, `weakPhonemes`, stores `attempts`/`phoneme_stats`/`usage`) y entre tareas (Consumes ↔ Produces).
4. Review Focus 5: PRN-02 `mic denied moves to error state with message` está en su Step 1.
5. Proporción: los bloques de código son tests y firmas; las implementaciones van en una línea.
