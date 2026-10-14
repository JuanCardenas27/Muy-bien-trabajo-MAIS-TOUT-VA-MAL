# Spikes y fundación -- Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Lee `AGENTS.md` antes de tomar una tarea.

**Goal:** Medir lo que el diseño da por supuesto (voces Edge, voces infantiles, clonación en CPU, JSON de Azure, OAuth UNAL, LLM) y dejar el monorepo, los contratos, el núcleo, el store SQLite, los fixtures sintéticos y el validador del grafo listos para que las olas 2+ trabajen en paralelo.

**Architecture:** Seis spikes que terminan en un ADR cada uno (`docs/decisions/ADR-00N-*.md`) y seis tareas de fundación: scaffold uv + Vite (FND-01), núcleo `frances` (FND-04), contratos pydantic + JSON Schema + tipos TS (FND-02), Store SQLite con dump determinista (FND-03), fixtures sintéticos + mocks respx (FND-05) y herramientas del grafo de tareas (AGT-01).

**Tech Stack:** Python 3.11–3.13, uv, Typer, pydantic v2, pytest + pytest-socket + respx, ruff, mypy strict, reportlab, Pillow, pypdfium2, PyYAML · Node 22, Vite, React, TypeScript strict, vitest, json-schema-to-typescript · edge-tts, Chatterbox Multilingual, coqui-tts (XTTS v2), faster-whisper (solo spikes) · `gh`.

**Spec:** `docs/superpowers/specs/2026-10-14-frances-classroom-design.md`

Plan maestro: docs/superpowers/plans/2026-10-14-00-master-plan.md (Global Constraints y contratos aplican a todas las tareas)

## Restricciones del subsistema

- Los scripts de spike (`scripts/spikes/*.py`) declaran sus dependencias con metadatos PEP 723 (`# /// script`) y versiones exactas; se corren con `uv run <script>` y nunca tocan `pyproject.toml`. No los importa `src/frances` ni corren en CI.
- Un spike humano no inventa resultados: el agente prepara script y ADR con la tabla vacía; el humano la llena con lo medido.
- Audio, modelos y salidas intermedias de spikes van a `.cache/spikes/<spk>/` (ignorado por git). Solo se commitean ADR, scripts y `tests/fixtures/azure/*.json`.
- Versión "exacta" en este plan = la última estable publicada el día de la tarea, fijada con `==` (Python) o `--save-exact` (npm) y anotada en el PR.
- `src/frances` no importa nada de `scripts/`. `scripts/tasks_check.py` y `scripts/sync_issues.py` solo usan stdlib + PyYAML.

## Review Focus

- Ítem 3 del plan maestro (tipografía → una sola tarjeta): FND-02 `test_card_id_typography_invariant`. El revisor verifica que cubre ’, NFD, « » y que cambiar `kind` cambia el id.
- Apoyo al ítem 1 (decimales variables): FND-04 `test_norm_ts_variable_fraction_digits` fija la salida de `norm_ts`; el test oficial sigue siendo SYN-04 `test_watermark_variable_fraction_digits`.
- Apoyo a los ítems 2 y 4: FND-05 debe producir los escenarios que esos tests consumen (`v2` con `version` nueva del PDF, 403 `exportSizeLimitExceeded`, `canDownload=false`, 404). Test: `test_mock_scenarios_cover_review_focus`.

## Plantilla de ADR (todas las tareas SPK)

```markdown
# ADR-00N: <título>
Fecha: YYYY-MM-DD · Estado: aceptado · Tarea: SPK-0N

## Contexto
## Opciones medidas
| Opción | <métrica 1> | <métrica 2> | ... |
## Decisión
## Consecuencias para las tareas <IDs>
## Cómo reproducir
```

### Task SPK-01: Edge-TTS: confirmar las 13 voces, formato y límites

Deps: []

**Files:**
- Create: `scripts/spikes/spk01_edge_voices.py`
- Create: `docs/decisions/ADR-001-edge-tts.md`

**Interfaces:**
- Consumes: nada.
- Produces: ADR-001 con la tabla `id | gender | accent | locale`, la versión exacta de `edge-tts`, el formato real y `concurrency_recommended` (por defecto 2). AUD-01 copia la tabla a `voices_default.yaml`; AUD-03 fija la versión y la concurrencia.

- [ ] **Step 1:** Escribir `scripts/spikes/spk01_edge_voices.py` con metadatos PEP 723 (`edge-tts==<exacta>`). Subcomandos: `list` (llama `edge_tts.list_voices()`, filtra `Locale` que empieza por `fr-`, imprime tabla Markdown `ShortName | Gender | Locale`), `bench --concurrency N --clips 20` (sintetiza "Bonjour, comment allez-vous ?" con `asyncio.Semaphore(N)`, rota entre las voces, guarda en `.cache/spikes/spk01/`, imprime latencia media, p95 y error rate), `probe` (corre `ffprobe -v error -show_streams -of json` sobre un clip e imprime `codec_name`, `sample_rate`, `channels`, `bit_rate`).
- [ ] **Step 2:** Correr `uv run scripts/spikes/spk01_edge_voices.py list`. Criterio: aparecen las 13 voces esperadas (fr-FR-DeniseNeural, fr-FR-EloiseNeural, fr-FR-HenriNeural, fr-FR-RemyMultilingualNeural, fr-FR-VivienneMultilingualNeural, fr-BE-CharlineNeural, fr-BE-GerardNeural, fr-CA-AntoineNeural, fr-CA-JeanNeural, fr-CA-SylvieNeural, fr-CA-ThierryNeural, fr-CH-ArianeNeural, fr-CH-FabriceNeural). Si difiere, el ADR lista la real y marca altas/bajas.
- [ ] **Step 3:** Sintetizar la frase con cada voz y correr `probe`. Criterio: se registra el formato real (esperado `mp3`, 24000 Hz, 1 canal, ~48 kbps).
- [ ] **Step 4:** Correr `bench` con concurrencia 1, 2 y 4. Criterio: tabla con latencia media, p95 y error rate por nivel.
- [ ] **Step 5:** Llenar ADR-001 con la plantilla. Decisión: concurrencia = el mayor nivel con error rate 0 y latencia p95 < 2× la de concurrencia 1 (2 si empatan). Consecuencias para AUD-01, AUD-03, AUD-06.
- [ ] **Step 6:** Commit: `git add scripts/spikes/spk01_edge_voices.py docs/decisions/ADR-001-edge-tts.md && git commit -m "docs(spike): ADR-001 voces y límites de Edge-TTS [SPK-01]"`.

### Task SPK-02: Voces infantiles: escuchar Eloise y decidir la fuente de referencias

Deps: []   (human: true)

**Files:**
- Create: `docs/decisions/ADR-002-child-voices.md`
- Create: `docs/decisions/consent-template.md`

**Interfaces:**
- Consumes: clips de SPK-01 en `.cache/spikes/spk01/` (si no existen, `uv run scripts/spikes/spk01_edge_voices.py bench --concurrency 1 --clips 20`).
- Produces: en ADR-002 (a) `fr-FR-EloiseNeural` → `age: child` sí/no, (b) `reference_source: synthetic | consented_recording`. AUD-01 valida `consent_ref` con prefijo `guardian:` para menores; AUD-10 implementa la ruta `synthetic`.

- [ ] Agente: dejar ADR-002 con la plantilla y la tabla vacía `Voz | ¿suena infantil? (1–5) | naturalidad (1–5) | inteligibilidad (1–5) | notas`, filas Eloise, Denise, Vivienne, con 5 frases de prueba (las de SPK-04).
- [ ] Agente: escribir `consent-template.md` en español: quién graba (nombre, fecha, si es menor: nombre del tutor), para qué (uso personal de estudio del titular), qué se genera (clips sintéticos derivados), revocable en cualquier momento con borrado de referencia y clips, prohibida la redistribución, firma y `consent_ref` asignado (`guardian:<slug>` si es menor, `adult:<slug>` si no).
- [ ] Humano: escuchar las 15 combinaciones y llenar la tabla.
- [ ] Humano: decidir (a) y (b); si (b) es `consented_recording`, guardar el consentimiento firmado fuera del repo público (en `frances-data/voices/consents/`) y anotar solo su `consent_ref`.
- [ ] Criterio de aceptación: ADR-002 con tabla llena, decisión (a) y (b) explícitas y consecuencias para AUD-01 y AUD-10; ningún dato personal en el repo público.
- [ ] Commit: `docs(spike): ADR-002 voces infantiles y plantilla de consentimiento [SPK-02]`.

### Task SPK-03: Benchmark de clonación en CPU: Chatterbox vs XTTS v2

Deps: []

**Files:**
- Create: `scripts/spikes/spk03_clone_bench.py`
- Create: `docs/decisions/ADR-003-clone-engine.md`

**Interfaces:**
- Consumes: nada (la referencia se genera con Edge, fr-FR-EloiseNeural).
- Produces: ADR-003 con `default_engine: chatterbox | xtts`, versiones exactas (`chatterbox-tts`, `coqui-tts`, `torch`, `faster-whisper`) y `clips_per_hour_12c`. AUD-07 fija esas versiones en `clone/pyproject.toml`; AUD-09 usa la estimación para `clone.max_per_run` (hoy 400).

- [ ] **Step 1:** Escribir el script sin dependencias de motor en PEP 723 (chocan entre sí); se corre una vez por motor con `uv run --python 3.11 --with <pins> scripts/spikes/spk03_clone_bench.py --engine chatterbox|xtts`. Subcomandos: `make-ref` (10–15 s con Eloise → `.cache/spikes/spk03/ref.wav`, 24 kHz mono), `run --engine E` (30 frases fijas en el script, 10 de 1–3 palabras; por clip: segundos, RTF = segundos/duración, RAM pico con `psutil` del proceso; transcribe con faster-whisper `small` `compute_type="int8"` `device="cpu"`, `language="fr"`; CER con `jiwer.cer` sobre `norm` minúsculas sin puntuación; escribe `.cache/spikes/spk03/<engine>.json`), `report` (une los JSON en tabla Markdown).
- [ ] **Step 2:** XTTS con `COQUI_TOS_AGREED=1`, modelo `tts_models/multilingual/multi-dataset/xtts_v2`; Chatterbox con `language_id="fr"`. Criterio: ambos JSON con 30 filas.
- [ ] **Step 3:** ADR-003: tabla `motor | s/clip medio | RTF | RAM pico GB | CER medio | % CER>0.15 (todas) | % CER>0.15 (1–3 palabras) | licencia`. Decisión: menor % CER>0.15; desempate por s/clip. `clips_per_hour_12c = 3600 / s_por_clip × (1 / (1 + %fallo))`, recomienda `max_per_run`. Consecuencias para AUD-07, AUD-08, AUD-09. Licencias: Chatterbox MIT; XTTS v2 CPML no comercial, confinado a `clone/`.
- [ ] **Step 4: Commit:** `docs(spike): ADR-003 motor de clonación por benchmark [SPK-03]`.

### Task SPK-04: Capturar fixtures reales de Azure Pronunciation fr-FR

Deps: []   (human: true)

**Files:**
- Create: `scripts/spikes/spk04_make_audio.py`
- Create: `tests/fixtures/azure/{bonjour,beau,enfants,rendezvous,restaurant,vin,miscue_marche}.json` (7 archivos)
- Create: `docs/decisions/ADR-004-azure-phonemes.md`

**Interfaces:**
- Consumes: `~/Escritorio/Azure/azure_pronunciation_test.py` (fuera del repo; lee `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `REFERENCE_TEXT`, `AUDIO_FILE`, `DUMP_JSON`).
- Produces: fixtures `tests/fixtures/azure/{bonjour,beau,enfants,rendezvous,restaurant,vin,miscue_marche}.json` (R-22, en el orden de las frases del primer paso); ADR-004 con la forma del JSON, el alfabeto de fonemas fr-FR, si hay `AccuracyScore` por fonema, y la tabla `espeak-ng IPA | etiqueta Azure`. PRN-01 parsea esos fixtures; CRD-06 implementa la tabla en `phoneme_map.py`.

- [ ] Agente: `spk04_make_audio.py` (PEP 723, `edge-tts==<exacta de ADR-001>`) sintetiza con fr-FR-DeniseNeural y convierte con `ffmpeg -ar 16000 -ac 1 -c:a pcm_s16le` a `.cache/spikes/spk04/<slug>.wav`. Frases: "Bonjour, comment allez-vous ?", "Il fait beau en France.", "Les enfants chantent une chanson.", "J'ai rendez-vous à onze heures.", "Le restaurant est très grand.", "Un bon vin blanc."; miscue: audio de "Nous allons au marché." con referencia "Nous allons au marché demain.". Imprime por slug la línea exacta: `REFERENCE_TEXT='…' AUDIO_FILE=… DUMP_JSON=tests/fixtures/azure/<slug>.json python ~/Escritorio/Azure/azure_pronunciation_test.py`.
- [ ] Agente: dejar ADR-004 con plantilla; para el mapa, correr `espeak-ng -q -v fr-fr --ipa "<frase>"` por frase y prellenar la columna IPA.
- [ ] Humano: confirmar granularidad `Phoneme` y `EnableMiscue=true` en el script; correr las 7 líneas.
- [ ] Humano + agente: verificar que cada JSON tiene `NBest[0].PronunciationAssessment`, `NBest[0].Words[].PronunciationAssessment.ErrorType` y `Words[].Phonemes[]`; el miscue trae `ErrorType: "Omission"` en "demain". Llenar la columna Azure del mapa.
- [ ] Criterio de aceptación: 7 JSON válidos sin la clave ni la región; ADR-004 con forma, alfabeto, puntaje por fonema (sí/no) y mapa completo para los fonemas de las 7 frases (al menos ɑ̃ ɔ̃ ɛ̃ e ɛ ʁ). Consecuencias para CRD-06 y PRN-01.
- [ ] Commit: `test(fixtures): JSON reales de Azure fr-FR y ADR-004 [SPK-04]`.

### Task SPK-05: OAuth de Google en producción + acceso Workspace UNAL

Deps: []   (human: true)

**Files:**
- Create: `docs/decisions/ADR-005-google-oauth.md`

**Interfaces:**
- Consumes: scopes de `frances.sync.auth.SCOPES` (plan maestro).
- Produces: ADR-005: proyecto creado, estado de publicación, resultado por scope, errores vistos y plan B. LIVE-01 lo sigue; SYN-01 usa el flujo probado.

- [ ] Agente: dejar ADR-005 con plantilla y, en «Cómo reproducir», el script de un solo uso (no va al repo como archivo): `uv run --with google-auth-oauthlib==<exacta> --with google-api-python-client==<exacta> python probe.py` con `InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES).run_local_server(port=0)`, luego `courses().list(pageSize=10)`, `courseWork().list(courseId=…, pageSize=1)` y `files().get_media` del primer `driveFile`, escribiendo a `/tmp`. Imprime solo conteos y códigos HTTP, nunca nombres ni contenido.
- [ ] Humano: crear proyecto GCP; habilitar Classroom API y Drive API; pantalla de consentimiento External, estado «In production»; agregar los 6 scopes; crear cliente OAuth «Desktop app»; guardar `client_secret*.json` fuera del repo.
- [ ] Humano: correr el script con la cuenta UNAL. Anotar: advertencia de app no verificada (sí/no), `admin_policy_enforced` / `access_denied` (sí/no), resultado de cada llamada y si `drive.readonly` descarga.
- [ ] Criterio de aceptación: tabla `scope / llamada | resultado | código` llena; decisión «API directa» o «plan B: `frances sync` en el PC con cron local que empuja a `frances-data`». Consecuencias para SYN-01, LIVE-01, OPS-05.
- [ ] Commit: `docs(spike): ADR-005 OAuth Google y acceso UNAL [SPK-05]`.

### Task SPK-06: LLM en Azure AI Foundry con Azure for Students

Deps: []   (human: true)

**Files:**
- Create: `scripts/spikes/spk06_llm_probe.py`
- Create: `docs/decisions/ADR-006-llm.md`

**Interfaces:**
- Consumes: env `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.
- Produces: ADR-006 con disponibilidad, formato de `base_url`, header de auth que funciona (`Authorization: Bearer` o `api-key`), precio por 1M tokens entrada/salida y costo de 30 publicaciones/día × ~4k tokens × 30 días. CRD-04 implementa ese cliente; si no hay disponibilidad, `cards.llm = "off"` en `frances-data`.

- [ ] Agente: `spk06_llm_probe.py` solo stdlib (`urllib.request`), `--auth bearer|api-key`. POST `{LLM_BASE_URL}/chat/completions` con `model`, un mensaje de sistema y uno de usuario (texto francés sintético de 3 líneas) y `response_format = {"type": "json_schema", "json_schema": {"name": "cards", "strict": true, "schema": <CardDraft-like mínimo: {cards: [{front_fr, back_es}]}>}}`. Imprime código HTTP, latencia, `usage` y si el contenido parsea y cumple el esquema. Nunca imprime la clave (enmascara todo menos 4 caracteres).
- [ ] Humano: intentar desplegar un modelo chico en Azure AI Foundry con Azure for Students; anotar región, nombre del modelo y si la cuota lo permite.
- [ ] Humano: correr el probe con ambos `--auth`. Criterio: JSON válido contra el esquema strict, o el error exacto.
- [ ] Criterio de aceptación: ADR-006 con tabla `modelo | región | auth | strict json_schema OK | USD/1M in | USD/1M out | USD/mes estimado`; decisión `llm = auto` u `off`. Consecuencias para CRD-04 y CRD-05.
- [ ] Commit: `docs(spike): ADR-006 LLM en Azure AI Foundry [SPK-06]`.

---
### Task FND-01: Scaffold del monorepo (uv, ruff, mypy, pytest, Vite/React/TS, CI básico)

Deps: []

**Files:**
- Create: `pyproject.toml`, `uv.lock`, `.npmrc`, `.gitignore`, `src/frances/__init__.py`, `tests/conftest.py`
- Create: `web/package.json`, `web/package-lock.json`, `web/tsconfig.json`, `web/index.html`, `web/eslint.config.js`, `web/.npmrc`, `web/src/vite-env.d.ts`, `web/public/.gitkeep`
- Create (placeholder; pasa a WEB-01): `web/src/main.tsx`
- Create (placeholder; pasa a WEB-12): `web/vite.config.ts`
- Create: `.github/workflows/ci.yml`
- Test: `tests/core/test_package.py`, `web/src/main.test.tsx`

**Interfaces:**
- Consumes: nada.
- Produces: paquete `frances` con `__version__ = "0.1.0"`; entry point `frances = "frances.cli:main"` (FND-04 crea `main`); fixture `fixtures_dir() -> Path` (= `tests/fixtures`) en `tests/conftest.py`; marker `heavy`; scripts npm `dev`, `build`, `preview`, `test`, `lint`, `typecheck`, `gen:types`; `web/src/main.tsx` (placeholder) exporta `Root(): JSX.Element`; `web/vite.config.ts` (placeholder) con `base: process.env.VITE_BASE ?? "/"`; workflow `ci` con jobs `python` (matriz 3.11/3.12) y `web`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_package.py
import frances
def test_package_version() -> None:
    assert frances.__version__ == "0.1.0"
```

```tsx
// web/src/main.test.tsx
import { render, screen } from "@testing-library/react";
import { Root } from "./main";
it("renders app title", () => {
  render(<Root />);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Frances");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/core/test_package.py -v` → Expected: FAIL (`ModuleNotFoundError: frances`, o sin proyecto).
Run: `npm --prefix web test` → Expected: FAIL (`Cannot find module './main'`).

- [ ] **Step 3: Implement the scaffold**

`pyproject.toml`: `name = "frances"`, `requires-python = ">=3.11,<3.14"`, src layout (build backend `hatchling`), `[project.scripts] frances = "frances.cli:main"`. Runtime de P01: `pydantic`, `typer`, `tzdata`. Grupo `dev`: `pytest`, `pytest-socket`, `pytest-cov`, `respx`, `mypy`, `ruff`, `reportlab`, `Pillow`, `pypdfium2`, `PyYAML`, `types-PyYAML` (todas `==` exacta, `uv add --group dev …`). Las dependencias de tareas posteriores NO se declaran aquí: cada tarea agrega las suyas (R-01). ruff: `line-length = 100`, `select = ["E","F","I","B","UP","SIM","RUF"]`. mypy: `strict = true`, `packages = ["frances"]`, `mypy_path = "src"`. pytest: `addopts = "--disable-socket --allow-unix-socket -m 'not heavy' --cov=frances --cov-report=term-missing --cov-fail-under=85"`, `markers = ["heavy: red o modelos pesados; no corre en CI"]`, `testpaths = ["tests"]`.

`src/frances/__init__.py`: solo `__version__ = "0.1.0"`. `.npmrc` y `web/.npmrc`: `save-exact=true` (npm con `--prefix web` lee el de `web/`). `.gitignore`: `.cache/`, `*.db`, `.env*`, `node_modules/`, `web/dist/`, `.venv/`, `__pycache__/`, `client_secret*.json`.

`web/`: Vite + React + TS (`npm create vite@<exacta> web -- --template react-ts` y luego recortar a los archivos de owns y placeholders). Dev deps exactas: `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `fake-indexeddb`, `eslint`, `typescript-eslint`, `eslint-plugin-jsx-a11y`, `prettier`, `json-schema-to-typescript`. `vite.config.ts` (placeholder; WEB-12 le agrega `VitePWA(pwaOptions)`) usa `base: process.env.VITE_BASE ?? "/"` e incluye `test: { environment: "jsdom", globals: true }`. `tsconfig.json`: `strict: true`, `module: "ESNext"`, `jsx: "react-jsx"`, `types: ["vitest/globals", "@testing-library/jest-dom"]`. `index.html`: `<html lang="es">`, `<div id="root">` y `<script type="module" src="/src/main.tsx">`. `eslint.config.js`: flat config con `typescript-eslint` (recommended) y `eslint-plugin-jsx-a11y` (recommended), ignora `dist/`. `src/vite-env.d.ts`: `/// <reference types="vite/client" />`. `public/` queda vacío salvo `.gitkeep`. Scripts: `test = "vitest run"`, `typecheck = "tsc --noEmit"`, `lint = "eslint . && prettier --check ."`, `gen:types = "node scripts/gen-types.mjs"`. Config de prettier en la clave `"prettier"` de `package.json`. `main.tsx` (placeholder; WEB-01 lo cambia para montar `<App/>`) exporta `Root` (un `<h1>Frances</h1>` provisional) y monta en `#root` solo si existe el elemento.

`ci.yml` (workflow `ci`, R-24): job `python` (matriz `3.11`, `3.12`; checks `python (3.11)` y `python (3.12)`): checkout, `apt-get install -y tesseract-ocr tesseract-ocr-fra tesseract-ocr-spa espeak-ng ffmpeg fonts-dejavu-core`, `astral-sh/setup-uv`, `uv sync --all-groups`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest`. Job `web` (Node 22): `npm ci`, `lint`, `typecheck`, `test`, `build` con `working-directory: web`. Cada `uses:` fijado por SHA de commit con el tag en comentario (`actions/checkout@<sha> # v4.x.y`).

- [ ] **Step 4: Run to verify they pass**

Run: `uv sync --all-groups && uv run pytest tests/core/test_package.py -v` → Expected: PASS (la cobertura del paquete es 100 %).
Run: `npm --prefix web ci && npm --prefix web test && npm --prefix web run typecheck` → Expected: PASS.
Run: `uv run ruff check . && uv run mypy src` → Expected: sin errores.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .npmrc .gitignore src/frances/__init__.py tests/conftest.py tests/core/test_package.py \
  web/package.json web/package-lock.json web/tsconfig.json web/index.html web/eslint.config.js web/.npmrc \
  web/src/vite-env.d.ts web/public/.gitkeep web/vite.config.ts web/src/main.tsx web/src/main.test.tsx \
  .github/workflows/ci.yml
git commit -m "build: scaffold uv + Vite/React/TS + CI [FND-01]"
```

### Task FND-04: Núcleo: config, paths, log+redact, errors, timeutil, stage, CLI

Deps: [FND-01]

**Files:**
- Create: `src/frances/errors.py`, `src/frances/timeutil.py`, `src/frances/paths.py`, `src/frances/log.py`, `src/frances/config.py`, `src/frances/cli.py`, `frances.example.toml`
- Test: `tests/core/test_errors.py`, `tests/core/test_timeutil.py`, `tests/core/test_paths.py`, `tests/core/test_log.py`, `tests/core/test_config.py`, `tests/core/test_cli.py`

**Interfaces:**
- Consumes: `frances.__version__` (FND-01).
- Produces:
  - `errors.py`: `class FrancesError(Exception)` con atributo de clase `exit_code: int = 1`; `PartialFailure` (2), `AuthError` (3), `ConfigError` (4).
  - `timeutil.py`: `norm_ts(s: str) -> str`, `format_ts(dt: datetime) -> str` (R-06: aware → mismo formato fijo que `norm_ts`; naive → `ValueError`), `parse_ts(s: str) -> datetime` (aware, UTC), `now_utc() -> datetime`, `to_bogota(dt: datetime) -> datetime`; constante `BOGOTA = ZoneInfo("America/Bogota")`.
  - `paths.py`: `@dataclass(frozen=True) class DataPaths(root: Path)` con `config`, `voices_yaml`, `voice_refs`, `state_sql`, `state_db`, `cache` (propiedades `Path`), `blob_path(sha: str) -> Path`, `extraction_path(sha: str, ver: str) -> Path`, `audio_path(key: str) -> Path`, `ensure_dirs() -> None`; rutas exactas de la tabla del plan maestro.
  - `log.py`: `SENSITIVE_ENV: tuple[str, ...]`, `redact(text: str, env: Mapping[str, str] | None = None) -> str` (`env=None` → `os.environ`), `class RedactFilter(logging.Filter)`, `get_logger(name: str) -> logging.Logger`.
  - `config.py`: `Settings` con un atributo anidado por sección del TOML (R-08): `classroom: ClassroomSettings`, `cards: CardsSettings`, `audio: AudioSettings`, `translator: TranslatorSettings`, `clone: CloneSettings`, `bundle: BundleSettings` (modelos pydantic `extra="forbid"`, defaults = TOML del plan maestro; p. ej. `settings.classroom.max_download_mb`, `settings.bundle.salt`), `Settings.secret(name: str) -> str`, `Settings.optional_secret(name: str) -> str | None`, `load_settings(path: Path, env: Mapping[str, str]) -> Settings`.
  - `cli.py`: `app = typer.Typer()`, `COMMAND_MODULES` (tupla del plan maestro, literal), `load_commands(app: typer.Typer) -> None`, `DataOpt = Annotated[Path, typer.Option("--data", help="Raíz del repo de datos")]` (uso: `data: DataOpt = Path(".")`), `exit_with(fn: Callable[[], StageReport | None]) -> NoReturn`, `main() -> None` (R-05; firmas del bloque `cli.py` de «Etapas» del plan maestro).

- [ ] **Step 1: Write the failing tests** (un archivo por módulo; asserts clave)

```python
def test_exit_codes() -> None:
    assert (FrancesError.exit_code, PartialFailure.exit_code, AuthError.exit_code, ConfigError.exit_code) == (1, 2, 3, 4)
    assert issubclass(ConfigError, FrancesError)

@pytest.mark.parametrize(("raw", "expected"), [
    ("2026-10-14T15:20:24Z", "2026-10-14T15:20:24.000000Z"),
    ("2026-10-14T15:20:24.898Z", "2026-10-14T15:20:24.898000Z"),
    ("2026-10-14T15:20:24.045123456Z", "2026-10-14T15:20:24.045123Z"),
    ("2026-10-14T10:20:24-05:00", "2026-10-14T15:20:24.000000Z"),
    ("2026-10-14T15:20:24+00:00", "2026-10-14T15:20:24.000000Z"),
])
def test_norm_ts_variable_fraction_digits(raw: str, expected: str) -> None:
    assert norm_ts(raw) == expected

# test_norm_ts_rejects_naive: norm_ts("2026-10-14T15:20:24") → ValueError
# test_format_ts: format_ts(datetime(2026, 10, 14, 10, 20, 24, 898000, tzinfo=BOGOTA)) == "2026-10-14T15:20:24.898000Z";
#   format_ts(datetime(2026, 10, 14, 15, 20, 24)) (naive) → ValueError
# test_to_bogota: to_bogota(parse_ts("2026-11-01T03:00:00Z")).isoformat() == "2026-10-31T22:00:00-05:00"

def test_data_paths_layout(tmp_path: Path) -> None:
    p = DataPaths(tmp_path)
    assert p.state_sql == tmp_path / "state/state.sql" and p.state_db == tmp_path / ".cache/state.db"
    assert p.blob_path("ab" + "0" * 62) == tmp_path / "blobs/ab" / ("ab" + "0" * 62)
    assert p.extraction_path("f" * 64, "3") == tmp_path / f"extractions/{'f' * 64}.3.json"
    assert p.audio_path("k" * 32) == tmp_path / f"audio/{'k' * 32}.mp3"

def test_redact_env_values_and_patterns() -> None:
    env = {"AZURE_SPEECH_KEY": "s3cretvalue123", "AZURE_SPEECH_REGION": "eastus"}
    hex32, hex64 = "0123456789abcdef" * 2, "ab" * 32
    out = redact("k=s3cretvalue123 r=eastus t=ya29.a0AfH6x Bearer abc.def 1//0gAbCdEfGhIjKlMnOpQrSt "
                 f"c=GOCSPX-abc123def456 h={hex32} s={hex64}", env)
    assert "s3cretvalue123" not in out and "ya29." not in out and "abc.def" not in out
    assert "1//0g" not in out and "GOCSPX-abc123def456" not in out
    assert hex32 in out and hex64 in out   # claves de caché, sha256 e ids de archivo no se redactan (R-07)
    assert "eastus" in out          # valores de < 8 caracteres no se tocan
    assert out.count("[REDACTED]") == 5

# test_logger_filter_redacts: con FRANCES_PASSPHRASE="demo demo demo demo demo demo" en env,
#   get_logger("t").warning("pass=%s", <passphrase>) → caplog sin "demo demo" y con "[REDACTED]"

def test_settings_defaults(tmp_path: Path) -> None:
    s = load_settings(tmp_path / "missing.toml", {})
    assert s.audio.fixed_voices == ["fr-FR-DeniseNeural", "fr-FR-HenriNeural"]
    assert (s.classroom.max_download_mb, s.clone.max_per_run, s.bundle.iterations) == (50, 400, 600000)
    assert s.cards.llm == "auto" and s.translator.monthly_char_cap == 1800000
# test_settings_unknown_key_is_config_error: "[audio]\nrotatin = 2\n" → ConfigError
# test_settings_invalid_toml_is_config_error: "[audio" → ConfigError
# test_secret_missing_raises_config_error / test_optional_secret_none: env {} → ConfigError / None
# test_example_toml_matches_defaults: load_settings(Path("frances.example.toml"), {}) == defaults

def test_exit_with_maps_report_and_errors(capsys: pytest.CaptureFixture[str]) -> None:
    @dataclass
    class FakeReport:                       # estructuralmente igual a StageReport.exit_code (FND-03)
        code: int
        def exit_code(self) -> int: return self.code
    def boom() -> None: raise ConfigError("token ya29.xyz inválido")
    for fn, code in ((lambda: None, 0), (lambda: FakeReport(2), 2), (lambda: FakeReport(1), 1), (boom, 4)):
        with pytest.raises(typer.Exit) as e:
            cli.exit_with(fn)
        assert e.value.exit_code == code
    err = capsys.readouterr().err
    assert "ya29.xyz" not in err and "[REDACTED]" in err

def test_broken_import_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "broken_cmd.py").write_text("import paquete_inexistente_xyz\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(cli, "COMMAND_MODULES", ("broken_cmd",))
    with pytest.raises(ModuleNotFoundError):
        cli.load_commands(typer.Typer())
# test_missing_module_is_skipped: COMMAND_MODULES = ("frances.nope_missing",) → load_commands no lanza
# test_frances_error_maps_exit_code: módulo falso cuyo register() agrega `boom(data: DataOpt = Path("."))`, que termina con
#   exit_with(fn) y fn lanza AuthError("token ya29.xyz inválido"); argv ["frances", "boom", "--data", tmp] vía main()
#   → SystemExit 3, stderr sin "ya29.xyz"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/core -v` → Expected: FAIL (`ModuleNotFoundError: frances.errors`, etc.).

- [ ] **Step 3: Implement**

- `norm_ts`: regex `^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$`; fracción → truncar/rellenar a 6; `datetime.fromisoformat` con la zona; `astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")`. Sin zona → `ValueError`. `format_ts`: `dt.tzinfo is None` → `ValueError`; si no, el mismo `astimezone(UTC).strftime(...)`.
- `SENSITIVE_ENV = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "AZURE_SPEECH_KEY", "AZURE_TRANSLATOR_KEY", "FRANCES_PASSPHRASE", "LLM_BASE_URL", "LLM_API_KEY")`. `redact` reemplaza primero los valores de esas variables de longitud ≥ 8 (más largos primero) y luego los patrones `ya29\.[\w-]+`, `1//[\w-]{20,}`, `Bearer\s+\S+`, `GOCSPX-[\w-]+` (sin patrón genérico de hex, R-07). `RedactFilter.filter` sustituye `record.msg` por `redact(record.getMessage())` y vacía `record.args`. `get_logger` usa formato `%(asctime)s %(levelname)s %(name)s: %(message)s` y agrega el filtro una sola vez.
- `load_settings`: archivo inexistente → defaults; `tomllib.TOMLDecodeError` o `ValidationError` → `ConfigError` (mensaje con la clave, sin valores). `env` se guarda en un `PrivateAttr`; `secret` lanza `ConfigError(f"falta la variable {name}")`.
- `cli.py`: sin callback global ni `data_dir(ctx)`; cada comando declara `data: DataOpt = Path(".")` (R-05). `exit_with(fn)`: llama `fn()`; `FrancesError` → `typer.echo(redact(str(e)), err=True)` y `raise typer.Exit(e.exit_code)`; `None` → `typer.Exit(0)`; reporte → `typer.Exit(r.exit_code())`. `StageReport` vive en `stage.py` (FND-03, que depende de esta tarea), así que `cli.py` no lo importa: el tipo de retorno de `fn` es un `Protocol` local con `exit_code(self) -> int`, que `StageReport` cumple estructuralmente. `load_commands`: por cada nombre, `importlib.import_module`; si `ModuleNotFoundError` y `e.name == nombre` → saltar; si no, relanzar; luego `module.register(app)`. `main()`: `load_commands(app)` y luego `app()`.
- `frances.example.toml`: copia del TOML del plan maestro con un comentario en español por clave.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/core -v && uv run mypy src && uv run ruff check .` → Expected: PASS, sin errores.

- [ ] **Step 5: Commit**

```bash
git add src/frances/{errors,timeutil,paths,log,config,cli}.py frances.example.toml tests/core/
git commit -m "feat(core): config, paths, redact, errores, timeutil y CLI [FND-04]"
```

### Task FND-02: Contratos: modelos, IDs, textnorm, export de JSON Schema y tipos TS

Deps: [FND-01]

**Files:**
- Create: `src/frances/textnorm.py`
- Create: `src/frances/models/__init__.py`, `ids.py`, `classroom.py`, `content.py`, `audio.py`, `pron.py`, `bundle.py`, `schema_cli.py`
- Create: `contracts/content-index.schema.json`, `contracts/bundle-manifest.schema.json`, `contracts/pron-result.schema.json` (generados)
- Create: `web/scripts/gen-types.mjs`, `web/src/contracts/generated.ts` (generado)
- Test: `tests/models/test_textnorm.py`, `tests/models/test_ids.py`, `tests/models/test_models.py`, `tests/models/test_schema_cli.py`, `web/src/contracts/generated.test.ts`

**Interfaces:**
- Consumes: scaffold de FND-01 (`typer`, `pydantic`, `json-schema-to-typescript`).
- Produces: todo lo de «Reglas de IDs», `frances.textnorm` y «Modelos Python» del plan maestro, con esos nombres, campos y tipos exactos (`ConfigDict(extra="forbid", frozen=True)` en todos); `register(app: typer.Typer) -> None` en `frances.models.schema_cli` (comando `frances schema export DIR`); `export_schemas(out_dir: Path) -> list[Path]`; `web/src/contracts/generated.ts` con los tipos TS `ContentIndex`, `BundleManifest`, `PronResult` y todos sus `$defs` (`FileRef`, `KdfParams`, `CardOut`, `SpeechCredentials`, ...).

- [ ] **Step 1: Write the failing tests**

```python
def test_card_id_typography_invariant() -> None:
    base = card_id("l'école", "vocab")
    assert card_id("l’école", "vocab") == base
    assert card_id(unicodedata.normalize("NFD", "l'école"), "vocab") == base
    assert card_id("« l'école »", "vocab") == base
    assert card_id("l'école", "phrase") != base
    assert re.fullmatch(r"c_[0-9a-f]{16}", base)

def test_tts_norm_keeps_case_and_punct() -> None:
    assert tts_norm("Allez\u202f!") == "Allez !"
    assert tts_norm("Allez !") != tts_norm("allez")
    assert tts_norm("l’école") == "l'école"

# test_display_clean_keeps_typography: display_clean("  « l’école »\u202f?  ") == "« l’école »\u202f?"; display_clean("a   b") == "a b"
# test_norm_key: norm_key("« Bonjour ! »") == "bonjour"; norm_key("L’École") == "l'école"

def test_item_id_prefixes() -> None:
    assert [item_id(k, "123") for k in ("coursework", "material", "announcement")] == ["cw_123", "mt_123", "an_123"]

def test_attachment_id_stable_and_16_hex() -> None:
    a = attachment_id("cw_1", "drive_file", "abc")
    assert a == attachment_id("cw_1", "drive_file", "abc") and re.fullmatch(r"at_[0-9a-f]{16}", a)
    assert a == "at_" + hashlib.sha256("cw_1\x1fdrive_file\x1fabc".encode()).hexdigest()[:16]
    assert a != attachment_id("cw_1", "link", "abc")
# test_content_hash: content_hash("a", "b") == hashlib.sha256(b"a\x1fb").hexdigest()

def test_models_forbid_extra() -> None:
    with pytest.raises(ValidationError):
        Example(fr="a", es="b", extra=1)
    with pytest.raises(ValidationError):
        Example(fr="a", es="b").fr = "c"         # frozen
# test_content_index_roundtrip: ContentIndex vacío (schema_version=1, speech=None) sobrevive model_dump_json → model_validate_json

def test_schema_export_is_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    export_schemas(a); export_schemas(b)
    names = sorted(p.name for p in a.iterdir())
    assert names == ["bundle-manifest.schema.json", "content-index.schema.json", "pron-result.schema.json"]
    assert all((a / n).read_bytes() == (b / n).read_bytes() for n in names)
    assert (a / names[0]).read_bytes().endswith(b"}\n")

def test_committed_contracts_up_to_date(tmp_path: Path) -> None:
    export_schemas(tmp_path)
    for p in tmp_path.iterdir():
        assert (Path("contracts") / p.name).read_bytes() == p.read_bytes()
```

```ts
// web/src/contracts/generated.test.ts
import type { ContentIndex, BundleManifest } from "./generated";
it("ContentIndex accepts a minimal demo index", () => {
  const idx: ContentIndex = { schema_version: 1, generated_at: "2026-10-14T15:20:24.000000Z", courses: [], topics: [],
    items: [], attachments: [], cards: [], sheets: [], voices: [], drills: [], speech: null };
  const m: Pick<BundleManifest, "format"> = { format: "FRB1" };
  expect(idx.cards).toEqual([]); expect(m.format).toBe("FRB1");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/models -v` → Expected: FAIL (`ModuleNotFoundError: frances.textnorm`).
Run: `npm --prefix web run typecheck` → Expected: FAIL (`Cannot find module './generated'`).

- [ ] **Step 3: Implement**

- `textnorm.py`: `display_clean` = `unicodedata.normalize("NFC")` + `re.sub(r"[ \t]{2,}", " ")` (solo espacio y tab; los finos `\u202f`/`\u00a0` se conservan) + `strip()`. `tts_norm` = `display_clean` + `’`→`'` + `[\u00a0\u202f\u2009]` → `" "` + colapso de espacios. `norm_key` = `tts_norm(...).casefold()` + `strip` repetido de `«»"“”` , espacios y `string.punctuation` menos `'` en los extremos.
- `models/*.py`: transcribir los modelos del plan maestro, un archivo por bloque; `ids.py` con `ITEM_PREFIX` y las cuatro funciones; `models/__init__.py` reexporta todos los nombres.
- `export_schemas(out_dir)`: para `{"content-index": ContentIndex, "bundle-manifest": BundleManifest, "pron-result": PronResult}`, `json.dumps(M.model_json_schema(mode="serialization"), indent=2, sort_keys=True, ensure_ascii=False) + "\n"`; crea `out_dir`. `register(app)` agrega un sub-Typer `schema` con `export DIR`.
- `gen-types.mjs`: lee los tres schemas de `../contracts/`, une sus `$defs` en un esquema envoltorio `{title: "FrancesContracts", type: "object", properties: {content_index: {$ref: "#/$defs/ContentIndex"}, bundle_manifest: {...}, pron_result: {...}}, $defs}` (cada raíz entra a `$defs` con su `title`; si dos `$defs` con el mismo nombre difieren, termina con código 1) y llama `compile(wrapper, "FrancesContracts", { bannerComment: "/* GENERADO — no editar. Fuente: contracts/*.schema.json (npm run gen:types) */", additionalProperties: false, unreachableDefinitions: true })`. Escribe `src/contracts/generated.ts`.
- Generar: `uv run frances schema export contracts/ && npm --prefix web run gen:types`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/models -v && uv run mypy src` → Expected: PASS.
Run: `npm --prefix web run typecheck && npm --prefix web test` → Expected: PASS.
Run: `uv run frances schema export contracts/ && npm --prefix web run gen:types && git diff --exit-code contracts web/src/contracts` → Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add src/frances/textnorm.py src/frances/models/ contracts/ web/scripts/gen-types.mjs web/src/contracts/ tests/models/
git commit -m "feat(models): contratos pydantic, IDs, textnorm y tipos TS generados [FND-02]"
```

### Task FND-03: SQLite: migración 0001, Store, dump/restore deterministas, medidores de uso

Deps: [FND-02, FND-04]

**Files:**
- Create: `src/frances/db/__init__.py`, `src/frances/db/migrations/0001_init.sql`, `src/frances/db/store.py`, `src/frances/db/dump.py`, `src/frances/db/usage.py`, `src/frances/db/cli.py`, `src/frances/stage.py`
- Test: `tests/db/test_store.py`, `tests/db/test_dump.py`, `tests/db/test_usage.py`, `tests/db/test_cli.py`, `tests/db/test_stage.py`

**Interfaces:**
- Consumes: `DataPaths` (`state_db`, `state_sql`, `config`, `ensure_dirs`), `load_settings`, `Settings`, `now_utc`, `timeutil.to_bogota`, `frances.cli.DataOpt`, `frances.cli.exit_with` (FND-04).
- Produces: `stage.py` (R-04): `StageContext`, `StageReport` exactamente como el plan maestro y `make_context(data_dir: Path, env: Mapping[str, str] | None = None) -> StageContext`; `Store`, `dump_sql`, `restore_sql`, `usage_get`, `usage_add`, `current_month`, `record_run` con las firmas exactas del plan maestro (`Store` en `db/store.py`, `dump_sql`/`restore_sql` en `db/dump.py`); `register(app)` en `frances.db.cli` con `frances restore --data DIR` y `frances dump --data DIR`. DDL exacto del plan maestro en `0001_init.sql`.

- [ ] **Step 1: Write the failing tests**

```python
def test_open_applies_migration_and_fk_on(tmp_path: Path) -> None:
    s = Store.open(tmp_path / "s.db")
    assert s.conn.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
    assert s.conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert s.conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    s.close(); s = Store.open(tmp_path / "s.db")            # reabrir no re-migra
    assert s.conn.execute("SELECT count(*) FROM schema_version").fetchone() == (1,)

def test_tx_rollback_on_exception(store: Store) -> None:
    with pytest.raises(RuntimeError), store.tx() as c:
        c.execute("INSERT INTO usage VALUES ('2026-10','llm_items',1)"); raise RuntimeError
    assert store.conn.execute("SELECT count(*) FROM usage").fetchone() == (0,)
# test_fk_violation_rejected: INSERT en topics con course_id inexistente → sqlite3.IntegrityError

def test_dump_is_order_independent(tmp_path: Path) -> None:
    rows = [("2026-10", "llm_items", 3), ("2026-09", "azure_tts_chars", 10), ("2026-10", "azure_tts_chars", 5)]
    a, b = Store.open(tmp_path / "a.db"), Store.open(tmp_path / "b.db")
    for s, rs in ((a, rows), (b, list(reversed(rows)))):
        with s.tx() as c: c.executemany("INSERT INTO usage VALUES (?,?,?)", rs)
    assert dump_sql(a) == dump_sql(b) and dump_sql(a).endswith("\n")
# test_dump_literals: audio con error=NULL, qa_cer=0.1, text="l'été" → el dump contiene "NULL", "0.1" y "'l''été'"

def test_restore_roundtrip(tmp_path: Path, populated_store: Store) -> None:
    sql = dump_sql(populated_store)
    assert dump_sql(restore_sql(sql, tmp_path / "r.db")) == sql

def test_usage_add_accumulates(store: Store) -> None:
    assert usage_get(store.conn, "2026-10", "azure_tts_chars") == 0
    assert usage_add(store.conn, "2026-10", "azure_tts_chars", 100) == 100
    assert usage_add(store.conn, "2026-10", "azure_tts_chars", 50) == 150

def test_current_month_bogota_boundary() -> None:
    assert current_month(parse_ts("2026-11-01T03:00:00Z")) == "2026-10"
    assert current_month(parse_ts("2026-11-01T05:00:00Z")) == "2026-11"
# test_record_run: StageReport("sync","partial",{"items":3},["x"]) → fila runs ("sync","partial",'{"counts":{"items":3},"errors":["x"]}')

def test_stage_report_exit_code() -> None:
    assert [StageReport("x", s).exit_code() for s in ("ok", "partial", "failed")] == [0, 2, 1]
# test_make_context_opens_state_db: make_context(tmp, {}) crea .cache/state.db, settings.cards.llm == "auto" y ctx.env == {}
# test_restore_cli_without_state_sql_creates_empty_db: `frances restore --data tmp` sin state.sql → .cache/state.db con schema_version 1
# test_dump_cli_writes_only_on_change: restore; dump; mtime m1; dump → mtime == m1; insertar fila; dump → mtime cambia
```

`store` y `populated_store` son fixtures locales de cada archivo de test (`populated_store` inserta un curso, un tema, un ítem, un blob, un adjunto, una tarjeta y un `runs`).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/db -v` → Expected: FAIL (`ModuleNotFoundError: frances.db`).

- [ ] **Step 3: Implement**

- `0001_init.sql`: el DDL del plan maestro, byte a byte.
- `Store.open`: `sqlite3.connect(path, isolation_level=None)`; `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=DELETE`; versión actual = `MAX(version)` de `schema_version` o 0 si la tabla no existe; aplica en orden numérico cada `migrations/NNNN_*.sql` con `NNNN > versión` (`importlib.resources`) dentro de `BEGIN IMMEDIATE`/`COMMIT`. `tx()`: `BEGIN IMMEDIATE`, `yield conn`, `COMMIT`; ante excepción `ROLLBACK` y relanza.
- `dump_sql`: línea 1 `-- frances state dump v1`; luego `sql` de `sqlite_master` con `type='table' AND name NOT LIKE 'sqlite_%'` ordenado por nombre, cada uno terminado en `;`; luego por tabla en orden alfabético `INSERT INTO <t> VALUES (...);`, filas ordenadas por las columnas PK (`PRAGMA table_info`, `pk > 0` en orden de `pk`; `runs` por `rowid`; sin PK → todas las columnas). Literales: `None`→`NULL`, `int`→`str`, `float`→`repr`, `str`→`'…'` con `'` duplicada; `bytes` → `TypeError`. Termina en `\n`.
- `restore_sql`: escribe a `db_path.with_suffix(".tmp")` con una conexión nueva (FK desactivadas), `executescript`, exige `PRAGMA foreign_key_check` vacío (si no, `ValueError`), cierra, `os.replace` sobre `db_path` y devuelve `Store.open(db_path)`.
- `usage_add`: `INSERT … ON CONFLICT(month, meter) DO UPDATE SET amount = amount + excluded.amount RETURNING amount`. `current_month(now)` = `to_bogota(now).strftime("%Y-%m")`. `record_run`: `stats = json.dumps({"counts": …, "errors": …}, separators=(",", ":"), sort_keys=True)`.
- `stage.py`: `StageContext`/`StageReport` transcritos del plan maestro. `make_context`: `env = os.environ if env is None else env`, `paths = DataPaths(data_dir)`, `paths.ensure_dirs()`, `settings = load_settings(paths.config, env)`, `store = Store.open(paths.state_db)`, `now = now_utc`.
- `db/cli.py`: cada comando recibe `data: DataOpt = Path(".")` y termina con `exit_with(...)`. `restore` → si existe `state_sql`, `restore_sql`; si no, `Store.open(state_db)`. `dump` → `Store.open(state_db)`, `dump_sql`, escribe `state_sql` solo si el texto difiere del actual (crea `state/`).

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/db tests/core -v && uv run mypy src` → Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/frances/db/ src/frances/stage.py tests/db/
git commit -m "feat(db): migración 0001, Store, dump/restore deterministas, usage y stage [FND-03]"
```

### Task FND-05: Generador de fixtures sintéticos (Classroom, Drive, PDF, imágenes) + mocks respx

Deps: [FND-01]

**Files:**
- Create: `tests/fixtures/make_fixtures.py`, `tests/fixtures/google_mock.py`
- Create (generados): `tests/fixtures/classroom/`, `tests/fixtures/drive/`, `tests/fixtures/pdf/`, `tests/fixtures/images/`
- Test: `tests/testkit/test_make_fixtures.py`, `tests/testkit/test_google_mock.py`

**Interfaces:**
- Consumes: `fixtures_dir` (FND-01); dev deps `reportlab`, `Pillow`, `pypdfium2`, `respx`.
- Produces: `generate(out_dir: Path) -> list[Path]` en `make_fixtures.py` (también `python tests/fixtures/make_fixtures.py [OUT]`); `install_google_mocks(router: respx.Router, scenario: str = "v1") -> None`, `FRENCH_COURSE_ID: str`, `CW_URL: str` y `ts_sort_key(ts: str) -> str` en `google_mock.py`, con escenarios `"v1"`, `"v2"`, `"deleted"`. SYN-03/05, FET-01/03 y EXT-01/02 consumen los archivos y los mocks.

- [ ] **Step 1: Write the failing tests**

```python
def test_fixtures_up_to_date(tmp_path: Path, fixtures_dir: Path) -> None:
    generate(tmp_path)
    for p in tmp_path.rglob("*"):
        if p.suffix in {".json", ".txt"}:
            assert p.read_bytes() == (fixtures_dir / p.relative_to(tmp_path)).read_bytes()
        elif p.suffix == ".pdf":
            assert pdf_text(p) == pdf_text(fixtures_dir / p.relative_to(tmp_path))   # pypdfium2, todas las páginas

def test_scenario_shape(fixtures_dir: Path) -> None:
    courses = json.loads((fixtures_dir / "classroom/v1/courses.json").read_text())["courses"]
    assert [(c["name"], c["courseState"]) for c in courses] == [
        ("Français A2 – Groupe 3", "ACTIVE"), ("Cálculo Diferencial", "ACTIVE"), ("Français A1 – 2025", "ARCHIVED")]
    # + 3 temas en el curso de francés; 8 materials; 6 announcements; updateTime con 0, 3 y 9 decimales
# test_scanned_pdf_has_no_text_layer: pdf_text("pdf/lesson-scanned.pdf").strip() == ""; "l’école" in pdf_text("pdf/lesson-text.pdf")

def test_coursework_pagination_and_order() -> None:
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "v1")
        p1 = httpx.get(f"{CW_URL}?orderBy=updateTime%20desc&pageSize=100").json()
        p2 = httpx.get(f"{CW_URL}?orderBy=updateTime%20desc&pageSize=100&pageToken={p1['nextPageToken']}").json()
    items = p1["courseWork"] + p2["courseWork"]
    assert len(items) == 120 and "nextPageToken" not in p2
    keys = [ts_sort_key(i["updateTime"]) for i in items]
    assert keys == sorted(keys, reverse=True)
# test_mock_scenarios_cover_review_focus: v1→v2 mismo fileId del PDF con "version" mayor; export de Slides → 403
#   reason "exportSizeLimitExceeded"; un archivo con capabilities.canDownload=false; un id → 404; "deleted": falta un material de v1
# test_token_endpoint_mocked: POST https://oauth2.googleapis.com/token → {"access_token": "ya29.fixture", ...}
```

`google_mock.py` exporta `FRENCH_COURSE_ID`, `CW_URL = f"https://classroom.googleapis.com/v1/courses/{FRENCH_COURSE_ID}/courseWork"` y `ts_sort_key(ts: str) -> str` (rellena la fracción a 9 dígitos; FND-05 no depende de `frances.timeutil`).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/testkit -v` → Expected: FAIL (`ModuleNotFoundError: make_fixtures`).

- [ ] **Step 3: Implement**

- `make_fixtures.py`: `random.Random(20261014)` para todo; ids y fechas derivados de la semilla (base `2026-08-03T13:00:00Z`, paso de horas). Escribe `classroom/{v1,v2,deleted}/` (`courses.json`, `topics.json`, `courseWork.page1.json`, `courseWork.page2.json`, `courseWorkMaterials.json`, `announcements.json`) con `json.dumps(indent=2, sort_keys=True, ensure_ascii=False) + "\n"`; `drive/` (`files/<id>.json` metadatos con `version`, `mimeType`, `capabilities`, `exportLinks`; `export/<id>.txt` del Doc). PDFs con reportlab y `invariant=1` (sin fecha de creación): `lesson-text.pdf` (vocabulario con ’, « », `\u202f` antes de ? y !), `lesson-scanned.pdf` (páginas de `lesson-text` rasterizadas con pypdfium2 a 150 dpi y metidas como imagen), `mixed-es-fr.pdf`; `lesson-text.v2.pdf` (una palabra más). `images/phrase.png`: "Les enfants chantent une chanson." en DejaVuSans 32 px con Pillow. Todo texto es inventado: ningún nombre real.
- Garantías del escenario (plan maestro R-29): todos los streams de `classroom/<scenario>/` son del curso `FRENCH_COURSE_ID`; cada archivo de `drive/` (`slides`, `locked`, `pdf_v2`…) está adjunto a al menos una publicación. Test: `test_every_drive_file_is_attached`.
- `google_mock.py`: rutas `GET https://classroom.googleapis.com/v1/courses`, `…/courses/{id}/topics`, `…/courseWork`, `…/courseWorkMaterials`, `…/announcements`, `GET https://www.googleapis.com/drive/v3/files/{id}` (metadatos o `alt=media` → bytes del PDF/PNG; 404 para el id faltante), `…/files/{id}/export` (`mimeType=text/plain` → TXT; Slides con `application/pdf` → 403 con `error.errors[0].reason = "exportSizeLimitExceeded"`), `POST https://oauth2.googleapis.com/token`. Lee los archivos de `classroom/<scenario>/`; `pageToken` elige la página; `orderBy="updateTime desc"` ordena por `ts_sort_key`.
- Correr `uv run python tests/fixtures/make_fixtures.py` y commitear la salida.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/testkit -v` → Expected: PASS. `uv run python tests/fixtures/make_fixtures.py && git status --porcelain tests/fixtures` → Expected: salida vacía.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/make_fixtures.py tests/fixtures/google_mock.py tests/fixtures/{classroom,drive,pdf,images}/ tests/testkit/
git commit -m "test(fixtures): escenario Classroom/Drive sintético y mocks respx [FND-05]"
```

### Task AGT-01: Validador de tasks.yaml y sincronización con GitHub Issues

Deps: [FND-01]

**Files:**
- Create: `scripts/tasks_check.py`, `scripts/sync_issues.py`
- Test: `tests/agents/test_tasks_check.py`, `tests/agents/test_sync_issues.py`

**Interfaces:**
- Consumes: `docs/superpowers/plans/tasks.yaml` (claves `plans`, `tasks[].{id,plan,human,deps,title,owns}`).
- Produces: `tasks_check.py`: `@dataclass(frozen=True) Task(id, plan, human, deps, title, owns, placeholders=())` (un placeholder de A solo puede estar en `owns` de una tarea que depende, transitivamente, de A; si no, error), `load_graph(path: Path) -> tuple[dict[str, str], list[Task]]`, `validate(plans: dict[str, str], tasks: list[Task], repo_root: Path, check_plans: bool = True) -> list[str]`, `waves(tasks: list[Task]) -> list[list[str]]`, `merged_ids(log_subjects: list[str]) -> set[str]`, `ready(tasks: list[Task], merged: set[str]) -> list[str]`, `main(argv: list[str] | None = None) -> int`. `sync_issues.py`: `issue_title(t: Task) -> str`, `issue_labels(t: Task, wave: int) -> list[str]`, `issue_body(t: Task, plans: dict[str, str]) -> str`, `plan_commands(tasks, plans, existing: dict[str, int]) -> list[list[str]]`, `main(argv: list[str] | None = None) -> int`. OPS-01 corre `tasks_check.py` en CI.

- [ ] **Step 1: Write the failing tests** (los scripts se cargan con `importlib.util.spec_from_file_location`; YAML sintéticos en `tmp_path`)

```python
def test_cycle_detected(tmp_path: Path) -> None:      # A→B→A
    assert any("ciclo" in e for e in validate(*load_graph(write_yaml(tmp_path, CYCLE)), tmp_path, False))
# test_missing_dep_detected: el error menciona "dep inexistente: X-99"; test_duplicate_id_detected: "id duplicado: A-01"
# test_owns_overlap_prefix: "src/a/" vs "src/a/b.py" → error; "web/App.tsx" vs "web/App.test.tsx" → sin error
# test_missing_plan_file: plan inexistente → error solo con check_plans=True

def test_real_graph_waves_match_master_plan() -> None:
    plans, tasks = load_graph(Path("docs/superpowers/plans/tasks.yaml"))
    assert validate(plans, tasks, Path("."), check_plans=False) == []
    assert [len(w) for w in waves(tasks)] == [7, 6, 16, 14, 14, 8, 5, 2, 2, 2, 1, 1, 1]

def test_ready_from_git_subjects() -> None:
    merged = merged_ids(["build: scaffold [FND-01]", "feat(core): núcleo [FND-04]", "chore: x"])
    assert merged == {"FND-01", "FND-04"}
    assert "FND-02" in ready(TASKS, merged) and "FND-03" not in ready(TASKS, merged)   # FND-03 espera FND-02

def test_issue_title_and_labels() -> None:
    assert issue_title(SPK02) == "[SPK-02] Voces infantiles: escuchar Eloise y decidir la fuente de referencias"
    assert issue_labels(SPK02, 0) == ["task", "wave:0", "plan:P01", "human"]
# test_dry_run_does_not_call_gh: main(["--repo", "o/r"]) == 0 y fake_gh solo registró ["issue", "list", ...]
# test_apply_creates_then_edits_idempotently: 1ª corrida `issue create --repo o/r --title "[FND-01] …" --body … --label task
#   --label wave:0 --label plan:P01`; 2ª con el issue #7 existente `issue edit 7 --repo o/r --body … --add-label …`; nunca "close"
```

`fake_gh`: fixture que escribe en `tmp_path/bin/gh` un script Python ejecutable que agrega `sys.argv[1:]` como línea JSON a `calls.jsonl` y, para `issue list`, imprime el JSON de `existing.json`; antepone `tmp_path/bin` a `PATH` con `monkeypatch.setenv`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/agents -v` → Expected: FAIL (`FileNotFoundError: scripts/tasks_check.py`).

- [ ] **Step 3: Implement**

- `validate`: ids únicos; cada dep existe; ciclos por DFS con colores (el error lista el ciclo `A -> B -> A`); solape de `owns` entre tareas distintas si son iguales o si una termina en `/` y la otra empieza por ella; con `check_plans`, `repo_root / plans[t.plan]` existe. `waves`: ola = 0 sin deps, si no 1 + máx de deps; cada ola ordenada por id. `merged_ids`: regex `\[([A-Z]+-\d+)\]`. `ready`: no fusionadas cuyas deps están todas en `merged`. `main`: sin flags imprime errores y sale 1 si hay; `--waves` imprime `Ola N (k): IDs`; `--ready` corre `git log origin/main --format=%s` (lista de argv) e imprime las listas.
- `sync_issues.py`: `existing` = `gh issue list --repo R --state all --limit 500 --search "in:title [" --json number,title`, mapeado por prefijo `[ID]` del título. Cuerpo: enlace al plan, `Deps:` y `Owns:` en listas. Por tarea: `issue create` si no existe, si no `issue edit N`; antes, `gh label create <l> --repo R --force` por label distinto. `--apply` ejecuta con `subprocess.run(argv, check=True)` (nunca `shell=True`); sin `--apply` imprime cada argv con `shlex.join`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/agents -v && uv run python scripts/tasks_check.py --waves` → Expected: PASS; 13 olas, la 0 con 7 tareas. (Sin `--waves`, sale 1 mientras falten los planes P02–P07: es el comportamiento esperado.)

- [ ] **Step 5: Commit**

```bash
git add scripts/tasks_check.py scripts/sync_issues.py tests/agents/
git commit -m "feat(agents): validador del grafo y sync de issues con gh [AGT-01]"
```

## Preguntas de contrato

Resueltas en el plan maestro:
- Q1 (archivos web fuera de `owns` de FND-01) → R-03, R-24.
- Q2 (`stage.py` y el ciclo FND-03↔FND-04) → R-04.
- Q3 (dependencias de tareas posteriores en los manifiestos) → R-01.
- Q4 (`main.tsx` de FND-01 frente a `App.tsx` de WEB-01) → R-03, R-10.
- Q5 (entry point `frances.cli:main`) → R-05 (bloque `cli.py` de «Etapas»).
- Q6 (posición de `--data`) → R-05.
- Q7 (`make_context` y `data_dir` fuera de los contratos) → R-04, R-05 (`make_context` queda en el bloque `stage.py` de «Etapas»; `data_dir` se elimina).

- Tipado de `exit_with` → R-05: el plan maestro fija `SupportsExitCode` (Protocol con `exit_code() -> int`) en `cli.py`; `StageReport` lo cumple estructuralmente.

Ninguna abierta.

## Autorrevisión

1. Están las 12 tareas en el orden pedido (SPK-01…06, FND-01, FND-04, FND-02, FND-03, FND-05, AGT-01), cada una con `Deps:` copiado de `tasks.yaml` y Files dentro de su `owns` (los tests aparecen solo en `Test:`).
2. Cada paso fija un archivo, una firma o un comando con su salida esperada; los spikes y tareas humanas tienen checklist, criterio de aceptación y ADR con la plantilla común.
3. Los nombres y tipos son los del plan maestro (`Store`, `dump_sql`, `card_id`, `StageReport.exit_code`, `COMMAND_MODULES`, `DataPaths`). Lo que el plan maestro no define (`export_schemas`, `generate`, `install_google_mocks`) está declarado en el bloque Produces de su tarea.
4. Review Focus: `test_card_id_typography_invariant` está en FND-02, y los tests de apoyo están en FND-04 y FND-05.
5. Proporción: los bloques de código son tests y asserts. Solo se escribe el algoritmo cuando la firma no lo determina (dump, `norm_ts`, unión de `$defs`, olas).
