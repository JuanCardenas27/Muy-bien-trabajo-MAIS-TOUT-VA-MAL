# Sync, fetch y extracción -- Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Lee `AGENTS.md` antes de tomar una tarea.

**Goal:** Traer de Google Classroom y Drive, en solo lectura, las publicaciones, temas y adjuntos de los cursos de francés; descargar o exportar sus archivos a un almacén content-addressed y extraer su texto etiquetado por idioma, todo idempotente y sin perder actualizaciones.

**Architecture:** `frances.sync` (OAuth, cliente HTTP con reintentos, `ClassroomClient`, sync incremental por stream con watermark normalizado y reconciliación semanal), `frances.fetch` (`DriveClient`, `BlobStore` por sha256, etapa con re-fetch por `version`) y `frances.extract` (pypdfium2 + OCR Tesseract por página, lingua por bloque, etapa por `(blob, EXTRACTOR_VERSION)`). Toda la red ocurre fuera de las transacciones (salvo SYN-04, R-26); cada etapa escribe en `Store.tx()` y devuelve `StageReport`.

**Tech Stack:** Python 3.11–3.13, httpx, google-auth, google-auth-oauthlib, Typer, pydantic v2, pypdfium2, Pillow, pytesseract (Tesseract `fra+spa`), lingua-language-detector · pytest, respx, pytest-socket.

**Spec:** `docs/superpowers/specs/2026-10-14-frances-classroom-design.md` (§6.1, §6.2, §6.3, §6.9)

Plan maestro: docs/superpowers/plans/2026-10-14-00-master-plan.md (Global Constraints y contratos aplican a todas las tareas)

## Restricciones del subsistema

- Todo test HTTP usa respx con `tests/fixtures/google_mock.py::install_google_mocks(router, scenario)` (FND-05), escenarios `"v1"`, `"v2"`, `"deleted"`; un test solo agrega o sobreescribe rutas puntuales. De `google_mock` solo se importa lo que FND-05 exporta: `install_google_mocks`, `FRENCH_COURSE_ID`, `CW_URL` y `ts_sort_key`. Como el mock instala más rutas de las que un test usa, todo router va con `assert_all_called=False` (`respx.mock(assert_all_called=False)`, o `pytestmark = pytest.mark.respx(assert_all_called=False)` para el fixture `respx_mock`).
- Del escenario solo se da por hecho lo que FND-05 declara: `classroom/<scenario>/` con `courses.json` (`courses`), `topics.json`, `courseWork.page1.json` + `courseWork.page2.json` (`courseWork`), `courseWorkMaterials.json` (`courseWorkMaterial`) y `announcements.json` (`announcements`), con los streams del curso `FRENCH_COURSE_ID`; un curso «Cálculo Diferencial» que no pasa `(?i)fran` y uno `ARCHIVED`; en `v2` un PDF con el mismo fileId y `version` mayor; el export de un Slides a `application/pdf` → 403 `exportSizeLimitExceeded`; un archivo con `capabilities.canDownload=false`; un id → 404; `deleted` = `v1` sin un material. Fixtures binarios: `pdf/lesson-text.pdf` (contiene «l’école»), `pdf/lesson-scanned.pdf` (las páginas de `lesson-text` rasterizadas, sin capa de texto) e `images/phrase.png` («Les enfants chantent une chanson.»).
- Todo id y todo conteo esperado se DERIVA en el test, nunca es un literal: helpers locales de cada archivo de test (R-02) `raws(scenario, kind) -> list[dict]` y `courses(scenario) -> list[dict]` (leen esos JSON), `drive_ids(scenario) -> list[str]` (los `driveFile.driveFile.id` distintos de los materials, en orden) y `drive_meta(scenario) -> dict[str, dict | None]` (dentro de un `respx.mock` con `install_google_mocks`, `httpx.get(f"https://www.googleapis.com/drive/v3/files/{id}")` por cada id; `None` si responde 404). Los ids de interés salen de ahí por propiedad: `pdf_v2` = PDF cuya `version` difiere entre `v1` y `v2`; `slides` = `mimeType` `application/vnd.google-apps.presentation`; `locked` = `canDownload` falso; `missing` = `None`; `gone` = ids de materials de `v1` ausentes en `deleted`. Los conteos se escriben como `len(...)` sobre esos datos.
- Los tests de etapa construyen el contexto con `ctx = dataclasses.replace(make_context(tmp_path, FAKE_ENV), now=lambda: FIXED)` (`make_context` de FND-03; sin `frances.toml` rigen los defaults de `Settings`), con `FAKE_ENV = {"GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "csecret", "GOOGLE_REFRESH_TOKEN": "rt"}`, `FIXED = datetime(2026, 10, 14, 10, 17, tzinfo=UTC)` y `NOW = format_ts(FIXED) == "2026-10-14T10:17:00.000000Z"`.
- Toda marca de tiempo en texto pasa por `norm_ts(s: str)`; todo `datetime` se convierte con `format_ts(dt)` (R-06). Los watermarks se comparan solo entre valores normalizados.
- `Settings` se lee por sección (R-08): `settings.classroom.include_course_ids`, `.include_name_regex`, `.max_download_mb`.
- Ningún mensaje de error ni log incluye tokens, rutas absolutas o texto del curso: todo pasa por `frances.log.redact()`.
- SQL solo en `sync/repo.py`, `fetch/repo.py`, `extract/repo.py`. Ninguna llamada de red dentro de `store.tx()`, salvo la excepción aceptada de SYN-04 (R-26).
- CLI (R-05): cada comando declara `data: DataOpt = Path(".")` (salvo `auth check`, que no lo usa), construye el contexto con `make_context(data)` y termina con `exit_with(lambda: ...)` de `frances.cli`; nada convierte a `typer.Exit` a mano. `exit_with` mapea `FrancesError` a su `exit_code` (`AuthError` → 3, `ConfigError` → 4) y `StageReport` a `exit_code()`.
- Claves de `StageReport.counts` (R-09): prefijadas por etapa; las que marcan cambio son exactamente `sync.items_upserted`, `sync.attachments_new`, `fetch.downloaded` y `extract.extracted`.

## Review Focus

1. Timestamps de Classroom con decimales variables (`…:23Z` frente a `…:23.045123456Z`) comparados como texto → actualizaciones perdidas. Test: SYN-04 `test_watermark_variable_fraction_digits` (en `tests/sync/test_streams.py`).
2. La profesora reemplaza el PDF en Drive sin editar la publicación → re-descarga por `version`. Test: FET-03 `test_refetch_when_drive_version_changes` (en `tests/fetch/test_run.py`).
4. Descarga restringida, export > 10 MB o archivo > 50 MB → la publicación sigue visible con enlace y la CLI sale con 2, no con 1. Tests: FET-03 `test_forbidden_download_is_partial`, `test_export_too_large_falls_back_to_text` y `test_too_large_skipped_with_link` (en `tests/fetch/test_run.py`).

---

### Task SYN-01: OAuth: credenciales desde el entorno + frances auth check

Deps: [FND-04, SYN-02]

**Files:**
- Create: `src/frances/sync/auth.py`
- Create: `.github/workflows/auth-check.yml`
- Test: `tests/sync/test_auth.py`

**Interfaces:**
- Consumes: `frances.errors.ConfigError`, `frances.errors.AuthError`, `exit_with` (FND-04); `GoogleApi`, `HttpxAuthRequest` (SYN-02, R-10).
- Produces:
  - `SCOPES: tuple[str, ...]` (los 6 scopes del plan maestro, en ese orden)
  - `TOKEN_URI = "https://oauth2.googleapis.com/token"`
  - `build_credentials(env: Mapping[str, str]) -> google.oauth2.credentials.Credentials` (sin `token`; `refresh_token`, `client_id`, `client_secret` de `GOOGLE_REFRESH_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`; `token_uri=TOKEN_URI`, `scopes=SCOPES`). Falta una variable → `ConfigError` que la nombra (R-23).
  - `register(app: typer.Typer) -> None` → `frances auth check`
  - `REAUTH_MESSAGE = "Re-autoriza: genera un refresh token nuevo en OAuth Playground (LIVE-01) y reemplaza el secreto GOOGLE_REFRESH_TOKEN"`

- [ ] **Step 1: Write the failing test**

```python
FAKE_ENV = {"GOOGLE_REFRESH_TOKEN": "rt", "GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "csecret"}
def test_build_credentials_uses_scopes_and_token_uri():
    c = build_credentials(FAKE_ENV)
    assert (c.refresh_token, c.client_id, c.token_uri) == ("rt", "cid", TOKEN_URI) and tuple(c.scopes) == SCOPES and len(SCOPES) == 6
@pytest.mark.parametrize("missing", sorted(FAKE_ENV))
def test_missing_variable_raises_config_error_naming_it(missing):
    with pytest.raises(ConfigError, match=missing): build_credentials({k: v for k, v in FAKE_ENV.items() if k != missing})
def test_check_ok_lists_one_course(respx_mock):
    install_google_mocks(respx_mock, "v1")
    res = CliRunner(env=FAKE_ENV).invoke(make_app(), ["auth", "check"])
    assert res.exit_code == 0 and respx_mock.calls.last.request.url.params["pageSize"] == "1"
def test_check_invalid_grant_exits_3(respx_mock):
    install_google_mocks(respx_mock, "v1")
    respx_mock.post("https://oauth2.googleapis.com/token").respond(400, json={"error": "invalid_grant"})
    res = CliRunner(env=FAKE_ENV).invoke(make_app(), ["auth", "check"])
    assert res.exit_code == 3 and "OAuth Playground" in res.output and "rt" not in res.output.split()
```

`make_app()` = `typer.Typer()` + `register(app)`.

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/sync/test_auth.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.sync.auth'"
- [ ] **Step 3: Implement `build_credentials(env: Mapping[str, str]) -> Credentials` y `register(app: typer.Typer) -> None` in `src/frances/sync/auth.py`**
`check`: `api = GoogleApi(build_credentials(os.environ), "https://classroom.googleapis.com/v1")` (literal: SYN-03 no es dep); `api.refresh()`; `api.get_json("courses", {"pageSize": 1})`; un `AuthError` se re-lanza con `REAUTH_MESSAGE`. Termina con `exit_with(...)`. No hay `auth init`: el refresh token se obtiene en el navegador (LIVE-01) y nunca se escribe en disco. `auth-check.yml`: `on: workflow_dispatch`, job con `if: vars.FRANCES_PROD == 'true'`, `environment: {name: production}`, `permissions: {contents: read}`; checkout, setup-uv, `uv sync --frozen` y `uv run frances auth check` con los tres `GOOGLE_*` en el `env:` del step.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/sync/test_auth.py -v` · Expected: PASS (6 passed)
- [ ] **Step 5: Commit** — `git add src/frances/sync/auth.py .github/workflows/auth-check.yml tests/sync/test_auth.py` y `git commit -m "feat(sync): credentials from env and frances auth check [SYN-01]"`

### Task SYN-02: Cliente HTTP de Google: refresh, reintentos, paginación, errores

Deps: [FND-04]

**Files:**
- Create: `src/frances/sync/google_http.py`
- Test: `tests/sync/test_google_http.py`

**Interfaces:**
- Consumes: `frances.errors.FrancesError`, `frances.errors.AuthError` (FND-04).
- Produces:
  - `class HttpxAuthRequest(google.auth.transport.Request)`: `__init__(self, client: httpx.Client)`; `__call__(url, method="GET", body=None, headers=None, timeout=None, **kw) -> google.auth.transport.Response` (el refresh pasa por el mismo `httpx.Client`, así respx lo intercepta)
  - `class ForbiddenError(FrancesError)`: `reason: str` · `class NotFoundError(FrancesError)` · `class RetryExhaustedError(FrancesError)`: `status: int`
  - `RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})`, `MAX_ATTEMPTS = 5`
  - `class GoogleApi`: `__init__(self, credentials, base_url: str, client: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep)`; `refresh(self) -> None`; `get_json(self, path: str, params: Mapping[str, object]) -> dict`; `paginate(self, path: str, params: Mapping[str, object], items_key: str) -> Iterator[dict]`; `stream(self, path: str, params: Mapping[str, object]) -> ContextManager[httpx.Response]`

- [ ] **Step 1: Write the failing test**

```python
def test_retries_429_then_ok(respx_mock):
    sleeps = []
    route = respx_mock.get(f"{BASE}/x").mock(side_effect=[httpx.Response(429), httpx.Response(429),
                                                         httpx.Response(200, json={"ok": 1})])
    assert make_api(sleeps).get_json("x", {}) == {"ok": 1}
    assert route.call_count == 3 and len(sleeps) == 2
    assert 0.8 <= sleeps[0] <= 1.2 and 1.6 <= sleeps[1] <= 2.4
def test_gives_up_after_5_attempts(respx_mock):
    sleeps = []
    route = respx_mock.get(f"{BASE}/x").respond(503)
    with pytest.raises(RetryExhaustedError) as e:
        make_api(sleeps).get_json("x", {})
    assert route.call_count == 5 and len(sleeps) == 4 and e.value.status == 503
def test_401_refreshes_once(respx_mock):
    creds = FakeCreds(token="t0")
    route = respx_mock.get(f"{BASE}/x").mock(side_effect=[httpx.Response(401), httpx.Response(200, json={})])
    GoogleApi(creds, BASE, sleep=lambda s: None).get_json("x", {})
    assert creds.refresh_calls == 1
    assert route.calls[1].request.headers["Authorization"] == "Bearer t1"
def test_paginate_follows_tokens(respx_mock):
    route = respx_mock.get(f"{BASE}/list").mock(side_effect=[
        httpx.Response(200, json={"things": [{"id": "a"}, {"id": "b"}], "nextPageToken": "p2"}),
        httpx.Response(200, json={"things": [{"id": "c"}]})])
    assert [t["id"] for t in make_api([]).paginate("list", {"pageSize": 2}, "things")] == ["a", "b", "c"]
    assert route.calls[1].request.url.params["pageToken"] == "p2"
    assert route.calls[1].request.url.params["pageSize"] == "2"
```

Además: `test_403_reason_parsed` (403 con `errors[0].reason == "exportSizeLimitExceeded"` → `ForbiddenError` con esa `reason`) · `test_retry_after_header_respected` (503 con `Retry-After: 7` y luego 200 → `sleeps == [7.0]`) · `test_401_twice_raises_auth_error` (401 siempre → `AuthError`) · `test_invalid_grant_on_refresh_raises_auth_error` (`RefreshError("invalid_grant: …")` en `refresh()` → `AuthError`) · `test_404_raises_not_found`. `BASE = "https://classroom.googleapis.com/v1"`; `make_api(sleeps)` = `GoogleApi(FakeCreds(token="t0"), BASE, sleep=sleeps.append)`; `FakeCreds` es un doble local con `token`, `valid`, `refresh(request)` que cuenta llamadas y pasa a `"t1"`, `"t2"`…

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/sync/test_google_http.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.sync.google_http'"
- [ ] **Step 3: Implement `GoogleApi`, `HttpxAuthRequest` y las excepciones in `src/frances/sync/google_http.py`**
Un único bucle `_send(method, path, params, stream)` usado por los tres métodos: refresca si `not credentials.valid`; en `RETRY_STATUSES` duerme `float(Retry-After)` si viene, o `2**n * random.uniform(0.8, 1.2)` (n = 0, 1, 2, 3); en 401 refresca una sola vez por llamada. `RefreshError` → `AuthError`. `stream()` verifica el status antes de ceder la respuesta y la cierra al salir. `paginate` mantiene `params` y agrega `pageToken` mientras exista `nextPageToken`; `items_key` ausente = página vacía.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/sync/test_google_http.py -v` · Expected: PASS (9 passed)
- [ ] **Step 5: Commit** — `git add src/frances/sync/google_http.py tests/sync/test_google_http.py` y `git commit -m "feat(sync): cliente HTTP de Google con reintentos y paginación [SYN-02]"`

### Task SYN-03: ClassroomClient: cursos, temas y streams por updateTime desc

Deps: [SYN-02, FND-02, FND-05]

**Files:**
- Create: `src/frances/sync/classroom.py`
- Test: `tests/sync/test_classroom.py`

**Interfaces:**
- Consumes: `GoogleApi.paginate` (SYN-02); `Course`, `Topic`, `Item`, `ItemKind`, `item_id`, `content_hash` (FND-02); `norm_ts`, `format_ts` (FND-04).
- Produces:
  - `CLASSROOM_BASE_URL = "https://classroom.googleapis.com/v1"`
  - `STREAM_PATHS: dict[ItemKind, tuple[str, str]]` = `{"coursework": ("courseWork", "courseWork"), "material": ("courseWorkMaterials", "courseWorkMaterial"), "announcement": ("announcements", "announcements")}` (sufijo de ruta bajo `courses/{id}/`, clave de ítems)
  - `class ClassroomClient`: `__init__(self, api: GoogleApi)`; `list_courses(self) -> list[Course]`; `list_topics(self, course_id: str) -> list[Topic]`; `iter_stream(self, course_id: str, stream: ItemKind) -> Iterator[dict]`
  - `parse_course(raw: dict) -> Course`; `parse_item(raw: dict, kind: ItemKind, course_id: str) -> Item`

- [ ] **Step 1: Write the failing test**

```python
def test_iter_stream_params(respx_mock):
    install_google_mocks(respx_mock, "v1")
    list(client().iter_stream(FR, "coursework"))
    p = respx_mock.calls.last.request.url.params
    assert p["orderBy"] == "updateTime desc" and p["pageSize"] == "100" and p["courseWorkStates"] == "PUBLISHED"
    list(client().iter_stream(FR, "material"))
    assert respx_mock.calls.last.request.url.params["courseWorkMaterialStates"] == "PUBLISHED"
def test_parse_three_kinds():
    cw_raw, mt_raw, an_raw = (raws("v1", k)[0] for k in ("coursework", "material", "announcement"))
    cw = parse_item(cw_raw, "coursework", FR)
    an = parse_item(an_raw, "announcement", FR)
    assert cw.id == item_id("coursework", cw_raw["id"]) and cw.text == cw_raw.get("description", "")
    assert an.id == item_id("announcement", an_raw["id"]) and an.title is None and an.text == an_raw["text"]
    assert parse_item(mt_raw, "material", FR).id == item_id("material", mt_raw["id"])
def test_due_at_with_time_and_default_bogota():
    raw = {**BASE_RAW, "dueDate": {"year": 2026, "month": 10, "day": 20}, "dueTime": {"hours": 15, "minutes": 30}}
    assert parse_item(raw, "coursework", FR).due_at == "2026-10-20T15:30:00.000000Z"
    raw = {**BASE_RAW, "dueDate": {"year": 2026, "month": 10, "day": 20}}
    assert parse_item(raw, "coursework", FR).due_at == "2026-10-21T04:59:00.000000Z"
    raw = {**BASE_RAW, "dueDate": {"year": 2026, "month": 10, "day": 20}, "dueTime": {"hours": 9}}
    assert parse_item(raw, "coursework", FR).due_at == "2026-10-20T09:00:00.000000Z"
def test_content_hash_stable_under_materials_order():
    a = parse_item({**BASE_RAW, "materials": [M_PDF, M_LINK]}, "coursework", FR)
    b = parse_item({**BASE_RAW, "materials": [M_LINK, M_PDF]}, "coursework", FR)
    c = parse_item({**BASE_RAW, "title": "Autre", "materials": [M_PDF, M_LINK]}, "coursework", FR)
    assert a.content_hash == b.content_hash != c.content_hash
```

Además: `test_list_courses_active_student_me` (v1 → `FR` está en los ids devueltos, todos están en `courses("v1")`, y params `studentId == "me"`, `courseStates == "ACTIVE"`) · `test_timestamps_normalized_and_raw_json_canonical` (sobre `BASE_RAW`: `updateTime` `…:23.045123456Z` → `…:23.045123Z`, `creationTime` `…:23Z` → `…:23.000000Z` y `raw_json == json.dumps(raw, sort_keys=True, ensure_ascii=False)`). `FR = FRENCH_COURSE_ID`; `raws`/`courses` son los helpers de «Restricciones»; `BASE_RAW`, `M_PDF`, `M_LINK` son dicts sintéticos locales del test.

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/sync/test_classroom.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.sync.classroom'"
- [ ] **Step 3: Implement `ClassroomClient` y `parse_item(raw: dict, kind: ItemKind, course_id: str) -> Item` in `src/frances/sync/classroom.py`**
`dueDate`/`dueTime` son UTC en la API; sin `dueTime` se arma `23:59` en `ZoneInfo("America/Bogota")`, se convierte a UTC y se formatea con `format_ts`; horas o minutos ausentes valen 0. `content_hash(title or "", text, *sorted(material_keys))`, con la clave de material = `driveFile.driveFile.id` | `youtubeVideo.id` | `link.url` | `form.formUrl` (función privada `_material_key`, sin depender de SYN-05). Marcas de la API (texto) con `norm_ts`.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/sync/test_classroom.py -v` · Expected: PASS (6 passed)
- [ ] **Step 5: Commit** — `git add src/frances/sync/classroom.py tests/sync/test_classroom.py` y `git commit -m "feat(sync): ClassroomClient y parseo de publicaciones [SYN-03]"`

### Task SYN-05: Normalización de adjuntos (materials → Attachment)

Deps: [FND-02, FND-05]

**Files:**
- Create: `src/frances/sync/attachments.py`
- Test: `tests/sync/test_attachments.py`

**Interfaces:**
- Consumes: `Attachment`, `attachment_id` (FND-02).
- Produces: `extract_attachments(raw: dict, item_id: str) -> list[Attachment]`

- [ ] **Step 1: Write the failing test**

```python
def test_each_material_kind():
    raw = {"materials": [
        {"driveFile": {"driveFile": {"id": "f_pdf", "title": "Leçon 1", "alternateLink": "https://drive.google.com/f_pdf"}}},
        {"youtubeVideo": {"id": "yt_abc", "title": "Vidéo", "alternateLink": "https://youtu.be/yt_abc"}},
        {"link": {"url": "https://example.org/conjugaison", "title": "Conjugaison"}},
        {"form": {"formUrl": "https://docs.google.com/forms/d/e/FORM1/viewform", "title": "Quiz"}}]}
    atts = extract_attachments(raw, "cw_1002")
    assert [(a.kind, a.external_id) for a in atts] == [
        ("drive_file", "f_pdf"), ("youtube", "yt_abc"),
        ("link", "https://example.org/conjugaison"), ("form", "https://docs.google.com/forms/d/e/FORM1/viewform")]
    assert atts[0].id == attachment_id("cw_1002", "drive_file", "f_pdf")
    assert atts[0].url == "https://drive.google.com/f_pdf" and atts[0].title == "Leçon 1"
    assert all(a.mime_type is None for a in atts)
```

Además: `test_dedupes_by_kind_and_external_id_keeping_order` (`[LINK_A, DRIVE_X, LINK_A]` → external_ids `[url de LINK_A, "f_x"]`) · `test_unknown_material_ignored_with_warning` (`{"hologram": …}` → `[]` y un registro `WARNING`) · `test_no_materials_returns_empty` (`{}` → `[]`).

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/sync/test_attachments.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.sync.attachments'"
- [ ] **Step 3: Implement `extract_attachments(raw: dict, item_id: str) -> list[Attachment]` in `src/frances/sync/attachments.py`**
Tabla de mapeo kind → (ruta al dict, campo id, campo url). El warning nombra solo las claves del material desconocido, nunca su contenido.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/sync/test_attachments.py -v` · Expected: PASS (4 passed)
- [ ] **Step 5: Commit** — `git add src/frances/sync/attachments.py tests/sync/test_attachments.py` y `git commit -m "feat(sync): normalización de adjuntos [SYN-05]"`

### Task SYN-04: Sync incremental por stream con watermark

Deps: [SYN-03, SYN-05, FND-03]

**Files:**
- Create: `src/frances/sync/streams.py`, `src/frances/sync/repo.py`
- Test: `tests/sync/test_streams.py`, `tests/sync/test_repo.py`

**Interfaces:**
- Consumes: `ClassroomClient.iter_stream`, `parse_item` (SYN-03); `extract_attachments` (SYN-05); `Store`, `dump_sql` (FND-03); `Settings`, `norm_ts`, `parse_ts`, `format_ts` (FND-04).
- Produces (`streams.py`):
  - `@dataclass class StreamResult: seen: int; upserted: int; stopped_at_watermark: bool; max_update_time: str | None`
  - `sync_stream(store: Store, client: ClassroomClient, course_id: str, stream: ItemKind, now: str, overlap: timedelta = timedelta(minutes=10), full: bool = False) -> StreamResult`
  - `select_courses(courses: list[Course], settings: Settings) -> list[Course]`
- Produces (`repo.py`, todas reciben `conn: sqlite3.Connection` dentro de una tx abierta por el llamador):
  - `get_watermark(conn, course_id: str, stream: str) -> str | None`; `set_watermark(conn, course_id: str, stream: str, last_update_time: str, now: str) -> None` (guarda `max(actual, nuevo)`)
  - `upsert_item(conn, item: Item, now: str) -> bool` (True si es nuevo o cambió `update_time`/`content_hash`; conserva `first_seen_at`, pone `last_seen_at=now`, `deleted_at=NULL`)
  - `sync_attachments(conn, item_id: str, atts: list[Attachment], now: str) -> int` (nuevos insertados; `pending` si `drive_file`, si no `reference`; `removed_at=now` a los ausentes; `removed_at=NULL` a los que reaparecen)
  - `upsert_course(conn, course: Course, included: bool, raw_json: str) -> None`; `upsert_topic(conn, topic: Topic) -> None`; `count_attachments(conn) -> int`
  - `live_item_ids(conn, course_id: str, kind: ItemKind) -> set[str]`; `deleted_item_ids(conn, course_id: str, kind: ItemKind) -> set[str]`
  - `tombstone_items(conn, item_ids: Iterable[str], now: str) -> int` (pone `deleted_at=now` y `removed_at=now` a sus adjuntos vivos); `restore_items(conn, item_ids: Iterable[str]) -> int` (`deleted_at=NULL` y `removed_at=NULL` en los adjuntos cuyo `removed_at` era igual al `deleted_at` del ítem)
  - `included_course_ids(conn) -> set[str]`; `set_course_included(conn, course_id: str, included: bool) -> None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/sync/test_streams.py
def test_watermark_variable_fraction_digits(tmp_path, respx_mock):   # REVIEW FOCUS 1
    store = seeded_store(tmp_path, watermark="2026-10-01T10:00:23.000000Z")
    route_coursework(respx_mock, [raw("1001", "2026-10-01T10:00:23.5Z"),
                                 raw("1003", "2026-10-01T10:00:23.045123456Z"),
                                 raw("1002", "2026-10-01T10:00:22.9Z")])
    r = sync_stream(store, client(), FR, "coursework", NOW, overlap=timedelta(0))
    assert (r.seen, r.upserted, r.stopped_at_watermark) == (2, 2, True)
    assert item_ids(store) == {cw("1001"), cw("1003")}
    assert update_time(store, cw("1003")) == "2026-10-01T10:00:23.045123Z"
    assert watermark(store) == "2026-10-01T10:00:23.500000Z" == r.max_update_time
def test_stops_paging_at_watermark(tmp_path, respx_mock):
    store = seeded_store(tmp_path, watermark="2026-10-01T12:25:00.000000Z")
    p1, p2 = route_two_pages(respx_mock, page1=[raw("1001", "2026-10-01T12:30:00Z"),
                                                raw("1002", "2026-10-01T12:00:00Z")])
    sync_stream(store, client(), FR, "coursework", NOW, overlap=timedelta(0))
    assert p1.call_count == 1 and p2.call_count == 0
def test_failure_mid_stream_keeps_watermark(tmp_path, respx_mock):
    store = seeded_store(tmp_path, watermark="2026-09-01T00:00:00.000000Z")
    p1, p2 = route_two_pages(respx_mock, page1=[raw("1001", "2026-10-01T12:30:00Z")], page2_status=500)
    with pytest.raises(RetryExhaustedError):
        sync_stream(store, client(sleep=lambda s: None), FR, "coursework", NOW)
    assert watermark(store) == "2026-09-01T00:00:00.000000Z" and item_ids(store) == set()
    assert p2.call_count == 5
def test_overlap_reprocessing_is_idempotent(tmp_path, respx_mock):
    install_google_mocks(respx_mock, "v1")
    store = seeded_store(tmp_path, watermark=None)
    sync_stream(store, client(), FR, "coursework", NOW)
    first = dump_sql(store)
    assert sync_stream(store, client(), FR, "coursework", NOW).upserted == 0
    assert dump_sql(store) == first
def test_edited_item_updates_and_marks_removed_attachment(tmp_path, respx_mock):
    store = seeded_store(tmp_path, watermark=None)
    route_coursework(respx_mock, [raw("1002", "2026-10-01T12:00:00Z", materials=[M_PDF, M_LINK])])
    sync_stream(store, client(), FR, "coursework", NOW)
    route_coursework(respx_mock, [raw("1002", "2026-10-08T15:00:00.123Z", title="Nouveau", materials=[M_PDF])])
    res = sync_stream(store, client(), FR, "coursework", NOW2)
    assert res.upserted == 1
    row = item_row(store, cw("1002"))
    assert row["first_seen_at"] == NOW and row["last_seen_at"] == NOW2 and row["title"] == "Nouveau"
    assert attachment(store, cw("1002"), "link")["removed_at"] == NOW2
    assert attachment(store, cw("1002"), "drive_file")["removed_at"] is None
# tests/sync/test_repo.py
def test_sync_attachments_insert_remove_restore(conn):
    assert sync_attachments(conn, "cw_1002", [PDF, LINK], NOW) == 2
    assert status_of(conn, PDF.id) == "pending" and status_of(conn, LINK.id) == "reference"
    assert sync_attachments(conn, "cw_1002", [PDF], NOW2) == 0 and removed_at(conn, LINK.id) == NOW2
    assert sync_attachments(conn, "cw_1002", [PDF, LINK], NOW3) == 0 and removed_at(conn, LINK.id) is None
```

Además: `test_full_ignores_watermark` (mismo setup que `test_stops_paging_at_watermark` con `full=True` → `seen == 3`, `p2.call_count == 1`) · `test_select_courses_ids_override_regex` (sobre `parse_course` de `courses("v1")`: `include_course_ids=[<id de «Cálculo Diferencial»>]` → solo ese; por defecto → `[FR]`, que excluye el `ARCHIVED` aunque su nombre pase el regex) · en `test_repo.py`: `test_set_watermark_never_moves_back` (guardar `2026-10-02T00:00:00.000000Z` y luego `2026-10-01T…` → queda el primero) y `test_tombstone_and_restore_items` (`tombstone_items([an("3001")], NOW) == 1` pone `removed_at == NOW` en sus adjuntos; `restore_items == 1` los vuelve `None`). `NOW2 = "2026-10-15T10:17:00.000000Z"`, `NOW3 = "2026-10-16T10:17:00.000000Z"`. Helpers locales: `FR = FRENCH_COURSE_ID`; `cw(x)`/`an(x)` = `item_id("coursework"|"announcement", x)`; `seeded_store` (Store con `FR` insertado y watermark opcional); `raw(id, update_time, title="T", materials=())` sintético; `route_coursework(router, raws)` (define la ruta `CW_URL` con `name="cw"`, así una segunda llamada la reemplaza); `route_two_pages` (sobre `CW_URL`: página 1 con `nextPageToken` `"p2"`; página 2 con 1 ítem o `page2_status`); `M_PDF`, `M_LINK` sintéticos; `conn` (fixture: Store en `tmp_path` con curso e ítems sintéticos sembrados).

- [ ] **Step 2: Run tests to verify they fail** — Run: `uv run pytest tests/sync/test_streams.py tests/sync/test_repo.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.sync.streams'"
- [ ] **Step 3: Implement `sync/repo.py` y `sync_stream(...) -> StreamResult` in `src/frances/sync/streams.py`**
Todo en un único `with store.tx() as conn:` que envuelve la iteración (la red pagina dentro de la tx BEGIN IMMEDIATE de un único proceso: es la regla del spec §6.1 de «misma transacción»; excepción aceptada por R-26). Umbral = `format_ts(parse_ts(watermark) - overlap)`; por cada raw, `ut = norm_ts(raw["updateTime"])`; si `not full and threshold is not None and ut < threshold`: `stopped_at_watermark=True` y `break` (no se pide la página siguiente). `seen` cuenta los ítems procesados; `set_watermark` va al final, solo si `max_update_time` no es `None`. `select_courses`: `c.state == "ACTIVE"` y (`c.id in settings.classroom.include_course_ids` si la lista no está vacía; si no, `re.search(settings.classroom.include_name_regex, c.name)`).
- [ ] **Step 4: Run tests to verify they pass** — Run: `uv run pytest tests/sync/test_streams.py tests/sync/test_repo.py -v` · Expected: PASS (10 passed)
- [ ] **Step 5: Commit** — `git add src/frances/sync/streams.py src/frances/sync/repo.py tests/sync/test_streams.py tests/sync/test_repo.py` y `git commit -m "feat(sync): sync incremental por stream con watermark normalizado [SYN-04]"`

### Task SYN-06: Reconciliación completa: tombstones de publicaciones y adjuntos

Deps: [SYN-04]

**Files:**
- Create: `src/frances/sync/reconcile.py`
- Test: `tests/sync/test_reconcile.py`

**Interfaces:**
- Consumes: `ClassroomClient.iter_stream` (SYN-03); `live_item_ids`, `deleted_item_ids`, `tombstone_items`, `restore_items`, `included_course_ids`, `set_course_included` (SYN-04 `repo.py`); `item_id` (FND-02).
- Produces: `@dataclass class ReconcileResult: deleted: int; restored: int; anomalies: list[str]` · `reconcile(store: Store, client: ClassroomClient, courses: list[Course], now: str) -> ReconcileResult`

- [ ] **Step 1: Write the failing test**

```python
def test_deleted_scenario_tombstones_gone_materials(tmp_path):
    store = synced_store(tmp_path, "v1")
    gone = {mt(x["id"]) for x in raws("v1", "material")} - {mt(x["id"]) for x in raws("deleted", "material")}
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "deleted")
        res = reconcile(store, client(), [FR_COURSE], NOW2)
    assert (res.deleted, res.restored, res.anomalies) == (len(gone), 0, []) and gone
    assert all(item_row(store, i)["deleted_at"] == NOW2 for i in gone)
    assert all(a["removed_at"] == NOW2 for i in gone for a in attachments_of(store, i))
def test_empty_stream_is_anomaly_and_marks_nothing(tmp_path):
    store = synced_store(tmp_path, "v1")
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "v1")
        r.get(f"{BASE}/courses/{FR}/announcements").respond(200, json={})
        res = reconcile(store, client(), [FR_COURSE], NOW2)
    assert res.deleted == 0 and len(res.anomalies) == 1 and f"{FR}/announcement" in res.anomalies[0]
    assert all(item_row(store, an(x["id"]))["deleted_at"] is None for x in raws("v1", "announcement"))
def test_reappearing_item_is_restored(tmp_path):
    store = synced_store(tmp_path, "v1")
    gone = {mt(x["id"]) for x in raws("v1", "material")} - {mt(x["id"]) for x in raws("deleted", "material")}
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "deleted"); reconcile(store, client(), [FR_COURSE], NOW2)
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "v1"); res = reconcile(store, client(), [FR_COURSE], NOW3)
    assert (res.deleted, res.restored) == (0, len(gone))
    assert all(item_row(store, i)["deleted_at"] is None for i in gone)
```

Además: `test_course_not_listed_is_excluded` (`reconcile(..., courses=[], ...)` → `FR` queda con `included == 0`). `FR_COURSE` = `parse_course` del curso `FR` en `courses("v1")`; `mt`/`an` = `item_id("material"|"announcement", x)`; `synced_store` corre `sync_stream` de los tres streams de `FR` con el escenario dado.

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/sync/test_reconcile.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.sync.reconcile'"
- [ ] **Step 3: Implement `reconcile(...) -> ReconcileResult` in `src/frances/sync/reconcile.py`**
Por curso y stream: listar todo con `iter_stream` (fuera de la tx), mapear a `item_id(kind, raw["id"])` y, en una tx por stream, `tombstone_items(live - listed)` y `restore_items(deleted & listed)`. Salvaguarda: listado vacío y `live` no vacío → anomalía `f"{course_id}/{stream}: listado vacío con {n} ítems vivos; no se marcó nada"`. Al final, `set_course_included(id, False)` para `included_course_ids(conn) - {c.id for c in courses}`.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/sync/test_reconcile.py -v` · Expected: PASS (4 passed)
- [ ] **Step 5: Commit** — `git add src/frances/sync/reconcile.py tests/sync/test_reconcile.py` y `git commit -m "feat(sync): reconciliación con salvaguarda de listado vacío [SYN-06]"`

### Task SYN-07: Etapa sync/reconcile + CLI + semántica de fallo de auth

Deps: [SYN-01, SYN-04, SYN-06]

**Files:**
- Create: `src/frances/sync/run.py`
- Test: `tests/sync/test_run.py`

**Interfaces:**
- Consumes: `build_credentials` (SYN-01); `GoogleApi.refresh` (SYN-02); `ClassroomClient`, `CLASSROOM_BASE_URL`, `parse_course` (SYN-03); `sync_stream`, `select_courses`, `upsert_course`, `upsert_topic`, `count_attachments` (SYN-04); `reconcile` (SYN-06); `StageContext`, `StageReport`, `make_context`, `record_run` (FND-03); `DataOpt`, `exit_with`, `format_ts` (FND-04).
- Produces: `run_sync(ctx: StageContext, full: bool = False) -> StageReport` · `run_reconcile(ctx: StageContext) -> StageReport` · `register(app: typer.Typer) -> None` (`frances sync [--full] [--data DIR]`, `frances reconcile [--data DIR]`; cada uno `data: DataOpt = Path(".")` y `exit_with(lambda: run_sync(make_context(data), full))`). Counts de `run_sync`: `sync.courses`, `sync.items_seen`, `sync.items_upserted`, `sync.attachments_new`, `sync.seen.coursework`, `sync.seen.material`, `sync.seen.announcement`. Counts de `run_reconcile`: `reconcile.deleted`, `reconcile.restored`, `reconcile.anomalies`.

- [ ] **Step 1: Write the failing test**

```python
def test_auth_failure_writes_nothing(tmp_path, respx_mock):
    ctx = make_ctx(tmp_path)
    install_google_mocks(respx_mock, "v1")
    respx_mock.post("https://oauth2.googleapis.com/token").respond(400, json={"error": "invalid_grant"})
    before = sha256_file(ctx.paths.state_db)
    with pytest.raises(AuthError):
        run_sync(ctx)
    assert sha256_file(ctx.paths.state_db) == before
    assert not any(c.request.url.host == "classroom.googleapis.com" for c in respx_mock.calls)
def test_sync_cli_auth_failure_exits_3(tmp_path, respx_mock):
    install_google_mocks(respx_mock, "v1")
    respx_mock.post("https://oauth2.googleapis.com/token").respond(400, json={"error": "invalid_grant"})
    res = CliRunner(env=FAKE_ENV).invoke(make_app(), ["sync", "--data", str(tmp_path)])
    assert res.exit_code == 3
def test_sync_end_to_end_v1_then_rerun(tmp_path):
    ctx = make_ctx(tmp_path)
    seen = {k: len(raws("v1", k)) for k in ("coursework", "material", "announcement")}
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "v1"); rep1 = run_sync(ctx)
    assert rep1.status == "ok" and rep1.exit_code() == 0
    assert rep1.counts["sync.courses"] == 1                     # FND-05: un solo curso ACTIVE que pasa el regex
    assert {k: rep1.counts[f"sync.seen.{k}"] for k in seen} == seen
    assert rep1.counts["sync.items_seen"] == rep1.counts["sync.items_upserted"] == sum(seen.values())
    assert rep1.counts["sync.attachments_new"] == expected_attachments("v1")
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "v1"); rep2 = run_sync(ctx)
    assert (rep2.counts["sync.items_upserted"], rep2.counts["sync.attachments_new"]) == (0, 0)
    assert runs_rows(ctx.store) == [("sync", "ok"), ("sync", "ok")]
    assert course_row(ctx.store, FR)["included"] == 1 and course_row(ctx.store, CALC)["included"] == 0
```

Además: `test_reconcile_anomaly_is_partial` (announcements de `FR` vacío con anuncios vivos → `status == "partial"`, `exit_code() == 2`, `counts["reconcile.anomalies"] == 1`). `make_ctx(tmp_path)` = el `dataclasses.replace(make_context(...))` de «Restricciones»; `CALC` = id del curso «Cálculo Diferencial» en `courses("v1")`; `expected_attachments(s)` = `len({a.id for k in STREAMS for x in raws(s, k) for a in extract_attachments(x, item_id(k, x["id"]))})`.

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/sync/test_run.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.sync.run'"
- [ ] **Step 3: Implement `run_sync`, `run_reconcile` y `register` in `src/frances/sync/run.py`**
Orden fijo: `build_credentials(ctx.env)` → `GoogleApi(...).refresh()` → `list_courses()` → recién entonces la primera `store.tx()`. `AuthError` se propaga sin `record_run`. Upsert de todos los cursos con `included = c in select_courses(...)`, temas de los incluidos, y `sync_stream` por curso incluido y stream (`full` pasa tal cual). `sync.attachments_new = count_attachments` después − antes. `record_run(conn, report, started_at, finished_at)` en una tx final, con las marcas de `format_ts(ctx.now())`. Anomalías de `reconcile` → `status="partial"` y `errors` redactados. `register` no captura nada: `exit_with` hace la conversión (R-05).
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/sync -v` · Expected: PASS (todo `tests/sync`)
- [ ] **Step 5: Commit** — `git add src/frances/sync/run.py tests/sync/test_run.py` y `git commit -m "feat(sync): etapas sync y reconcile con fallo de auth sin escrituras [SYN-07]"`

### Task FET-01: DriveClient: metadatos, versión, descarga, exportación

Deps: [SYN-02, FND-05]

**Files:**
- Create: `src/frances/fetch/drive.py`
- Test: `tests/fetch/test_drive.py`

**Interfaces:**
- Consumes: `GoogleApi.get_json`, `GoogleApi.stream`, `ForbiddenError` (SYN-02).
- Produces:
  - `DRIVE_BASE_URL = "https://www.googleapis.com/drive/v3"`; `NATIVE_PREFIX = "application/vnd.google-apps."`
  - `@dataclass(frozen=True) class DriveMeta: id: str; name: str; mime_type: str; size: int | None; version: str; md5: str | None; can_download: bool; export_links: dict[str, str]`
  - `class TooLargeError(FrancesError)` · `class ExportTooLargeError(FrancesError)`
  - `GOOGLE_NATIVE_EXPORTS: dict[str, list[tuple[str, Literal["view", "text"]]]]` = `document`/`presentation` → `[("application/pdf", "view"), ("text/plain", "text")]`, `spreadsheet` → `[("application/pdf", "view"), ("text/csv", "text")]`, `drawing` → `[("image/png", "view")]`, claves con `NATIVE_PREFIX`
  - `class DriveClient`: `__init__(self, api: GoogleApi)`; `get_metadata(self, file_id: str) -> DriveMeta`; `download(self, file_id: str, dest: BinaryIO, max_bytes: int) -> int`; `export(self, file_id: str, mime: str, dest: BinaryIO, max_bytes: int) -> int`

- [ ] **Step 1: Write the failing test**

```python
def test_get_metadata_fields(respx_mock):
    meta = drive_meta("v1")
    doc = next(i for i, m in meta.items() if m and m["mimeType"] == "application/vnd.google-apps.document")
    install_google_mocks(respx_mock, "v1")
    m = drive().get_metadata(doc)
    assert (m.mime_type, m.version, m.can_download, m.size) == (
        meta[doc]["mimeType"], meta[doc]["version"], meta[doc]["capabilities"]["canDownload"], None)
    p = respx_mock.calls.last.request.url.params
    assert p["supportsAllDrives"] == "true" and "capabilities/canDownload" in p["fields"]
def test_download_streams_and_counts(respx_mock):
    pdf = first_id(drive_meta("v1"), mime="application/pdf", can_download=True)
    install_google_mocks(respx_mock, "v1")
    buf = io.BytesIO()
    n = drive().download(pdf, buf, max_bytes=50 * 1024 * 1024)
    assert n == len(buf.getvalue()) > 0 and buf.getvalue().startswith(b"%PDF")
    assert respx_mock.calls.last.request.url.params["alt"] == "media"
def test_export_size_limit_raises_export_too_large(respx_mock):
    slides = first_id(drive_meta("v1"), mime="application/vnd.google-apps.presentation")
    install_google_mocks(respx_mock, "v1")                       # FND-05: export de Slides a PDF → 403
    with pytest.raises(ExportTooLargeError):
        drive().export(slides, "application/pdf", io.BytesIO(), max_bytes=50 * 1024 * 1024)
```

Además: `test_download_over_limit_raises` (`download(pdf, …, max_bytes=10)` → `TooLargeError`) · `test_native_exports_table` (`GOOGLE_NATIVE_EXPORTS["application/vnd.google-apps.spreadsheet"][1] == ("text/csv", "text")`). `drive_meta` es el helper de «Restricciones»; `first_id(meta, mime=None, can_download=None)` devuelve el primer id cuyo metadato cumple los filtros dados.

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/fetch/test_drive.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.fetch.drive'"
- [ ] **Step 3: Implement `DriveClient` in `src/frances/fetch/drive.py`**
`files/{id}` con `fields=id,name,mimeType,size,version,md5Checksum,capabilities/canDownload,exportLinks` y `supportsAllDrives=true`; `download` = `files/{id}` con `alt=media`; `export` = `files/{id}/export` con `mimeType`. Ambos copian `iter_bytes()` a `dest` acumulando bytes y lanzan `TooLargeError` en cuanto el acumulado supera `max_bytes`. `ForbiddenError` con `reason == "exportSizeLimitExceeded"` → `ExportTooLargeError`; otras razones se propagan.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/fetch/test_drive.py -v` · Expected: PASS (5 passed)
- [ ] **Step 5: Commit** — `git add src/frances/fetch/drive.py tests/fetch/test_drive.py` y `git commit -m "feat(fetch): DriveClient con metadatos, descarga y export [FET-01]"`

### Task FET-02: BlobStore content-addressed con tope de tamaño

Deps: [FND-04]

**Files:**
- Create: `src/frances/fetch/blobs.py`
- Test: `tests/fetch/test_blobs.py`

**Interfaces:**
- Consumes: `DataPaths.blob_path`, `DataPaths.cache` (FND-04).
- Produces: `class BlobTooLargeError(FrancesError)` · `class BlobStore`: `__init__(self, paths: DataPaths)`; `put_stream(self, write_fn: Callable[[BinaryIO], int], max_bytes: int) -> tuple[str, int]`; `put_bytes(self, data: bytes) -> tuple[str, int]`; `exists(self, sha: str) -> bool`; `path(self, sha: str) -> Path`. Solo filesystem.

- [ ] **Step 1: Write the failing test**

```python
def test_same_content_same_sha_single_file(tmp_path):
    bs = BlobStore(DataPaths(tmp_path))
    a = bs.put_stream(lambda f: f.write(b"bonjour"), max_bytes=100)
    b = bs.put_bytes(b"bonjour")
    assert a == b == (hashlib.sha256(b"bonjour").hexdigest(), 7)
    assert bs.path(a[0]) == DataPaths(tmp_path).blob_path(a[0]) and bs.exists(a[0])
    assert len([p for p in (tmp_path / "blobs").rglob("*") if p.is_file()]) == 1
    assert list(DataPaths(tmp_path).cache.glob("*")) == []
def test_too_large_leaves_no_temp(tmp_path):
    bs = BlobStore(DataPaths(tmp_path))
    with pytest.raises(BlobTooLargeError):
        bs.put_stream(lambda f: f.write(b"x" * 11), max_bytes=10)
    assert list(DataPaths(tmp_path).cache.glob("*")) == [] and not (tmp_path / "blobs").exists()
```

Además: `test_write_fn_exception_leaves_no_temp` (`write_fn` que escribe y lanza `RuntimeError` → se propaga y `.cache/` queda vacío).

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/fetch/test_blobs.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.fetch.blobs'"
- [ ] **Step 3: Implement `BlobStore` in `src/frances/fetch/blobs.py`**
`write_fn` recibe un envoltorio `BinaryIO` que actualiza el sha256 y el conteo en cada `write` y lanza `BlobTooLargeError` al superar `max_bytes`. Temporal con `tempfile.NamedTemporaryFile(dir=paths.cache, delete=False)`; `try/finally` borra el temporal ante cualquier excepción; si el destino ya existe se borra el temporal, si no `os.replace`.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/fetch/test_blobs.py -v` · Expected: PASS (3 passed)
- [ ] **Step 5: Commit** — `git add src/frances/fetch/blobs.py tests/fetch/test_blobs.py` y `git commit -m "feat(fetch): BlobStore content-addressed con tope [FET-02]"`

### Task FET-03: Etapa fetch: descarga/export, re-fetch por versión, estados

Deps: [FET-01, FET-02, FND-03, SYN-01]

**Files:**
- Create: `src/frances/fetch/run.py`, `src/frances/fetch/repo.py`
- Test: `tests/fetch/test_run.py`

**Interfaces:**
- Consumes: `DriveClient`, `DriveMeta`, `GOOGLE_NATIVE_EXPORTS`, `NATIVE_PREFIX`, `TooLargeError`, `ExportTooLargeError`, `DRIVE_BASE_URL` (FET-01); `BlobStore`, `BlobTooLargeError` (FET-02); `GoogleApi`, `NotFoundError` (SYN-02); `build_credentials` (SYN-01, R-10); `StageContext`, `StageReport`, `make_context`, `record_run` (FND-03); `DataOpt`, `exit_with`, `format_ts`, `redact` (FND-04).
- Produces (`repo.py`): `@dataclass class FetchCandidate: id: str; external_id: str; status: AttachmentStatus; drive_version: str | None; attempts: int` · `list_fetch_candidates(conn) -> list[FetchCandidate]` (`drive_file`, `removed_at IS NULL`, ítem no borrado, y `status = 'pending'` o `'downloaded'` o (`'error'` con `attempts < 5`)) · `insert_blob(conn, sha256: str, size: int, mime_type: str, now: str) -> None` (INSERT OR IGNORE) · `mark_downloaded(conn, attachment_id: str, *, blob_sha256: str | None, export_pdf_sha256: str | None, export_text_sha256: str | None, mime_type: str, title: str, drive_version: str, now: str) -> None` · `mark_status(conn, attachment_id: str, status: AttachmentStatus, error: str | None, now: str, bump_attempts: bool = False) -> None`
- Produces (`run.py`): `run_fetch(ctx: StageContext) -> StageReport` · `register(app: typer.Typer) -> None` (`frances fetch [--data DIR]`: `data: DataOpt = Path(".")` y `exit_with(lambda: run_fetch(make_context(data)))`). Counts: `fetch.checked`, `fetch.downloaded`, `fetch.unchanged`, `fetch.forbidden`, `fetch.not_found`, `fetch.skipped_too_large`, `fetch.error`, `fetch.export_pdf_skipped`.

- [ ] **Step 1: Write the failing test**

```python
def test_fetch_v1_outcomes_match_fixture(tmp_path):
    meta = drive_meta("v1"); ctx = synced_ctx(tmp_path, "v1")
    with mocks("v1"):
        rep = run_fetch(ctx)
    want = {i: expected_status(m) for i, m in meta.items()}
    assert {i: {a["status"] for a in atts(ctx, i)} for i in meta} == {i: {s} for i, s in want.items()}
    assert rep.counts["fetch.checked"] == sum(len(atts(ctx, i)) for i in meta)
    assert rep.counts["fetch.downloaded"] == sum(len(atts(ctx, i)) for i, s in want.items() if s == "downloaded")
    for i, m in meta.items():
        for a in (atts(ctx, i) if want[i] == "downloaded" else []):
            assert a["drive_version"] == m["version"]
            assert (a["blob_sha256"] is None) == m["mimeType"].startswith(NATIVE_PREFIX)
    assert rep.exit_code() == (2 if set(want.values()) != {"downloaded"} or slides_ids(meta) else 0)
def test_refetch_when_drive_version_changes(tmp_path):            # REVIEW FOCUS 2
    v1, v2 = drive_meta("v1"), drive_meta("v2")
    changed = {i for i in v1 if v1[i] and v2.get(i) and v1[i]["version"] != v2[i]["version"]
               and expected_status(v1[i]) == "downloaded"}
    pdf = next(i for i in changed if v1[i]["mimeType"] == "application/pdf")
    ctx = synced_ctx(tmp_path, "v1")
    with mocks("v1"):
        rep1 = run_fetch(ctx)
    old = {a["id"]: a["blob_sha256"] for a in atts(ctx, pdf)}
    with mocks("v2") as r:
        rep = run_fetch(ctx)
        media = [c for c in r.calls if c.request.url.path.endswith(f"/files/{pdf}")
                 and c.request.url.params.get("alt") == "media"]
    assert len(media) == len(old) > 0
    assert all(a["blob_sha256"] not in (None, old[a["id"]]) and a["drive_version"] == v2[pdf]["version"]
               for a in atts(ctx, pdf))
    assert rep.counts["fetch.downloaded"] == sum(len(atts(ctx, i)) for i in changed)
    assert rep.counts["fetch.unchanged"] == rep1.counts["fetch.downloaded"] - rep.counts["fetch.downloaded"]
def test_forbidden_download_is_partial(tmp_path):                  # REVIEW FOCUS 4
    locked = first_id(drive_meta("v1"), can_download=False)
    ctx = synced_ctx(tmp_path, "v1")
    with mocks("v1"):
        assert run_fetch(ctx).exit_code() == 2
    assert {a["status"] for a in atts(ctx, locked)} == {"forbidden"}
    assert all(item_row(ctx.store, a["item_id"])["deleted_at"] is None for a in atts(ctx, locked))
    with mocks("v1") as r:
        assert run_fetch(ctx).exit_code() == 0
        assert not any(c.request.url.path.endswith(f"/files/{locked}") for c in r.calls)
def test_export_too_large_falls_back_to_text(tmp_path):            # REVIEW FOCUS 4
    slides = first_id(drive_meta("v1"), mime="application/vnd.google-apps.presentation")
    ctx = synced_ctx(tmp_path, "v1")
    with mocks("v1"):
        rep = run_fetch(ctx)
    rows = atts(ctx, slides)
    assert rows and all(a["status"] == "downloaded" and a["export_pdf_sha256"] is None and a["export_text_sha256"]
                        for a in rows)
    assert rep.exit_code() == 2 and rep.counts["fetch.export_pdf_skipped"] == len(rows)
    with mocks("v1"):
        assert run_fetch(ctx).exit_code() == 0
def test_too_large_skipped_with_link(tmp_path):                    # REVIEW FOCUS 4
    ctx = with_max_download_mb(synced_ctx(tmp_path, "v1"), 0)
    with mocks("v1"):
        rep = run_fetch(ctx)
    binaries = [a for i, m in drive_meta("v1").items() if expected_status(m) == "downloaded"
                and not m["mimeType"].startswith(NATIVE_PREFIX) for a in atts(ctx, i)]
    assert binaries and all(a["status"] == "skipped_too_large" and a["blob_sha256"] is None
                            and a["url"].startswith("https://") for a in binaries)
    assert rep.exit_code() == 2 and rep.counts["fetch.skipped_too_large"] == len(binaries)
def test_same_file_in_two_posts_single_blob(tmp_path):
    ctx = synced_ctx(tmp_path, "v1")
    b = first_id(drive_meta("v1"), mime="application/pdf", can_download=True)
    add_drive_attachment(ctx, item_without(ctx, b), b)          # segundo adjunto con el mismo fileId
    with mocks("v1"):
        run_fetch(ctx)
    rows = atts(ctx, b)
    assert len(rows) >= 2 and len({a["blob_sha256"] for a in rows}) == 1
    assert len([p for p in (tmp_path / "blobs").rglob("*") if p.is_file()]) == blob_rows(ctx)
```

Además: `test_unexpected_error_bumps_attempts_and_redacts` (`monkeypatch.setattr(DriveClient, "download", ...)` que lanza `httpx.ReadError("ya29.fixture boom")` → cada adjunto binario descargable queda `("error", 1)` en `(status, attempts)`, `exit_code() == 2` y `"ya29.fixture"` no aparece en `rep.errors`). Helpers locales, además de los de «Restricciones»: `mocks(s)` = `respx.mock(assert_all_called=False)` con `install_google_mocks(router, s)`; `synced_ctx(tmp_path, s)` = `make_ctx` + `run_sync` bajo `mocks(s)`; `atts(ctx, file_id)` = filas de `attachments` con ese `external_id`; `expected_status(m)` = `"not_found"` si `m is None`, `"forbidden"` si `canDownload` es falso, `"skipped_too_large"` si `int(m.get("size", 0))` supera `max_download_mb` de los defaults, si no `"downloaded"`; `slides_ids(meta)` (ids con `mimeType` de Slides); `first_id` (el mismo helper que en FET-01); `with_max_download_mb(ctx, n)` = `dataclasses.replace` con `settings.model_copy` de la sección `classroom`; `add_drive_attachment`/`item_without` siembran con `sync_attachments` (SYN-04); `blob_rows(ctx)` = `SELECT COUNT(*) FROM blobs`.

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/fetch/test_run.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.fetch.run'"
- [ ] **Step 3: Implement `fetch/repo.py` y `run_fetch(ctx) -> StageReport` in `src/frances/fetch/run.py`**
Credenciales y `api.refresh()` antes de la primera tx (`AuthError` sale sin escribir). Por candidato, red fuera de la tx y luego una tx corta: metadata → `downloaded` con misma `version` = `unchanged`; `can_download=False` → `forbidden`; nativo → `GOOGLE_NATIVE_EXPORTS` (`"view"` → `export_pdf_sha256`, `"text"` → `export_text_sha256`; `ExportTooLargeError` en `"view"` → sin PDF, `fetch.export_pdf_skipped += 1`, mensaje en `errors`); binario con `size > settings.classroom.max_download_mb * 1024 * 1024` → `skipped_too_large` sin descargar; si no, `blobs.put_stream(lambda f: drive.download(id, f, max_bytes), max_bytes)`. `TooLargeError` o `BlobTooLargeError` → `skipped_too_large`; `NotFoundError` → `not_found`; otra `FrancesError` o `httpx.HTTPError` → `error`, `bump_attempts=True`, `redact(str(exc))`. `status="partial"` si este run produjo algún `forbidden`/`not_found`/`skipped_too_large`/`error` o un `export_pdf_skipped` (export > 10 MB = `partial` en el run que lo detecta, R-26; `TooLargeError` y `BlobTooLargeError` siguen siendo dos clases, R-26). Las marcas `now` salen de `format_ts(ctx.now())`.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/fetch -v` · Expected: PASS (todo `tests/fetch`)
- [ ] **Step 5: Commit** — `git add src/frances/fetch/run.py src/frances/fetch/repo.py tests/fetch/test_run.py` y `git commit -m "feat(fetch): etapa fetch con re-fetch por versión y estados parciales [FET-03]"`

### Task EXT-01: PDF: capa de texto + OCR por página

Deps: [FND-02, FND-05]

**Files:**
- Create: `src/frances/extract/pdf.py`
- Test: `tests/extract/test_pdf.py`

**Interfaces:**
- Consumes: fixtures `tests/fixtures/pdf/lesson-text.pdf` y `pdf/lesson-scanned.pdf` (FND-05); dev dep `reportlab` (FND-05).
- Produces: `@dataclass class PageText: page: int; text: str; method: Literal["pdf_text", "pdf_ocr"]` · `extract_pdf(path: Path, ocr: Callable[[PIL.Image.Image], str], min_chars: int = 40, dpi: int = 200) -> list[PageText]` (`page` empieza en 1)

- [ ] **Step 1: Write the failing test**

```python
def test_text_pdf_never_calls_ocr():
    ocr = CountingOcr("x")
    pages = extract_pdf(FIX / "pdf/lesson-text.pdf", ocr)
    assert [p.page for p in pages] == list(range(1, n_pages(FIX / "pdf/lesson-text.pdf") + 1)) and ocr.calls == 0
    assert all(p.method == "pdf_text" for p in pages) and "l’école" in "".join(p.text for p in pages)
def test_scanned_pdf_ocrs_every_page_at_200_dpi():
    ocr = CountingOcr("Bonjour la classe")
    pages = extract_pdf(FIX / "pdf/lesson-scanned.pdf", ocr)
    assert ocr.calls == len(pages) == n_pages(FIX / "pdf/lesson-scanned.pdf")
    assert all(p.method == "pdf_ocr" for p in pages) and pages[0].text == "Bonjour la classe"
    assert abs(ocr.images[0].width - page_width_pt(FIX / "pdf/lesson-scanned.pdf") * 200 / 72) <= 1
def test_page_without_text_layer_uses_ocr(tmp_path):
    pdf = two_page_pdf(tmp_path, "Bonjour, je m’appelle Ana et j’étudie le français.", "")   # pág. 2 vacía
    ocr = CountingOcr("Hola, me llamo Ana y estudio francés.")
    pages = extract_pdf(pdf, ocr)
    assert [p.method for p in pages] == ["pdf_text", "pdf_ocr"] and ocr.calls == 1
    assert "Bonjour" in pages[0].text and "Hola" in pages[1].text
```

`n_pages`/`page_width_pt` leen el PDF con pypdfium2; `two_page_pdf` lo arma con reportlab en `tmp_path` (sintético, sin depender del contenido de `mixed-es-fr.pdf`, que FND-05 no fija).

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/extract/test_pdf.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.extract.pdf'"
- [ ] **Step 3: Implement `extract_pdf(...) -> list[PageText]` in `src/frances/extract/pdf.py`**
`pypdfium2.PdfDocument(path)`; texto con `page.get_textpage().get_text_range()`; «útiles» = caracteres no blancos; render con `page.render(scale=dpi / 72).to_pil()`. Cerrar documento y páginas en `finally`.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/extract/test_pdf.py -v` · Expected: PASS (3 passed)
- [ ] **Step 5: Commit** — `git add src/frances/extract/pdf.py tests/extract/test_pdf.py` y `git commit -m "feat(extract): PDF con capa de texto y OCR por página [EXT-01]"`

### Task EXT-02: OCR de imágenes fra+spa

Deps: [FND-02, FND-05]

**Files:**
- Create: `src/frances/extract/ocr.py`
- Test: `tests/extract/test_ocr.py`

**Interfaces:**
- Produces: `preprocess(img: Image.Image) -> Image.Image` · `ocr_image(img: Image.Image, langs: str = "fra+spa") -> str` · `ocr_file(path: Path) -> str` · `tesseract_version() -> str`

- [ ] **Step 1: Write the failing test**

```python
def test_preprocess_grayscale_and_upscale():
    out = preprocess(Image.new("RGB", (500, 100), "white"))
    assert out.mode == "L" and out.size == (1000, 200)
    assert preprocess(Image.new("RGB", (1200, 100))).size == (1200, 100)
@needs_tesseract
def test_ocr_file_reads_french_fixture():
    text = fold(ocr_file(FIX / "images/phrase.png"))      # FND-05: «Les enfants chantent une chanson.»
    assert "enfants" in text and "chanson" in text
```

Además: `test_tesseract_version_is_semver_like` (`re.match(r"^\d+\.\d+", tesseract_version())` (`@needs_tesseract`)). `fold(s)` = `unicodedata.normalize("NFKD", s.casefold())` sin marcas combinantes; `needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract")` (la CI de FND-01 instala `tesseract-ocr-fra` y `-spa`).

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/extract/test_ocr.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.extract.ocr'"
- [ ] **Step 3: Implement las cuatro funciones in `src/frances/extract/ocr.py`**
`preprocess`: `ImageOps.grayscale` → `ImageOps.autocontrast` → si `width < 1000`, `resize((w*2, h*2), Image.LANCZOS)`. `ocr_image`: `pytesseract.image_to_string(preprocess(img), lang=langs, config="--psm 6")`. `tesseract_version`: `str(pytesseract.get_tesseract_version())`.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/extract/test_ocr.py -v` · Expected: PASS (3 passed)
- [ ] **Step 5: Commit** — `git add src/frances/extract/ocr.py tests/extract/test_ocr.py` y `git commit -m "feat(extract): OCR de imágenes fra+spa [EXT-02]"`

### Task EXT-03: Etiquetado de idioma por bloque

Deps: [FND-02]

**Files:**
- Create: `src/frances/extract/lang.py`
- Test: `tests/extract/test_lang.py`

**Interfaces:**
- Consumes: `Lang`, `TextBlock` (FND-02).
- Produces (firmas del plan maestro): `detect_lang(text: str) -> Lang` · `split_blocks(text: str, source: str, page: int | None = None) -> list[TextBlock]`

- [ ] **Step 1: Write the failing test**

```python
def test_french_and_spanish_sentences():
    assert detect_lang("Je voudrais un café, s'il vous plaît.") == "fr"
    assert detect_lang("Quisiera un café, por favor, gracias.") == "es"
def test_mixed_paragraph():
    txt = "Le chat dort sur le canapé tout l'après-midi. El perro juega en el jardín con los niños."
    assert detect_lang(txt) == "mixed"
def test_split_blocks_by_blank_line():
    blocks = split_blocks("Je suis étudiant à l'université.\n\n   \n\nSoy estudiante de la universidad.", "at_0123456789abcdef", page=2)
    assert [(b.lang, b.source, b.page) for b in blocks] == [("fr", "at_0123456789abcdef", 2),
                                                           ("es", "at_0123456789abcdef", 2)]
    assert blocks[0].text == "Je suis étudiant à l'université."
```

Además: `test_short_text_is_unknown` (`detect_lang("Bonjour") == "unknown"` (7 letras < 12)).

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/extract/test_lang.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.extract.lang'"
- [ ] **Step 3: Implement `detect_lang` y `split_blocks` in `src/frances/extract/lang.py`**
Detector lingua perezoso y único: `LanguageDetectorBuilder.from_languages(FRENCH, SPANISH, ENGLISH).with_minimum_relative_distance(0.1).build()`; `None` → `"unknown"`. Mixto: partir en oraciones por `(?<=[.!?])\s+`, detectar cada una y, si las letras de oraciones `fr` y las de `es` son cada una ≥ 25 % del total de letras, `"mixed"`; si no, detección del texto completo. Bloques: `re.split(r"\n\s*\n", text)`, `strip()`, descartar vacíos.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/extract/test_lang.py -v` · Expected: PASS (4 passed)
- [ ] **Step 5: Commit** — `git add src/frances/extract/lang.py tests/extract/test_lang.py` y `git commit -m "feat(extract): etiquetado de idioma por bloque [EXT-03]"`

### Task EXT-04: Etapa extract idempotente por (blob, versión)

Deps: [EXT-01, EXT-02, EXT-03, FET-02, FND-03]

**Files:**
- Create: `src/frances/extract/run.py`, `src/frances/extract/repo.py`
- Test: `tests/extract/test_run.py`

**Interfaces:**
- Consumes: `extract_pdf`, `PageText` (EXT-01); `ocr_image`, `ocr_file` (EXT-02); `split_blocks` (EXT-03); `BlobStore.path` (FET-02); `Extraction`, `TextBlock`, `ExtractMethod` (FND-02); `DataPaths.extraction_path`, `redact`, `format_ts`, `DataOpt`, `exit_with` (FND-04); `StageContext`, `StageReport`, `make_context`, `record_run` (FND-03).
- Produces (`repo.py`): `@dataclass class ExtractCandidate: attachment_id: str; sha256: str; mime_type: str; native: bool` · `list_extract_candidates(conn, extractor_version: str) -> list[ExtractCandidate]` (adjuntos `downloaded`, `removed_at IS NULL`, ítem no borrado, sin fila en `extractions` para `(sha, extractor_version)`; nativo → `export_text_sha256`, si no `blob_sha256`; un sha repetido aparece una vez) · `insert_extraction(conn, ex: Extraction, lang: Lang, path: str, now: str) -> None`
- Produces (`run.py`): `EXTRACTOR_VERSION = "1"` · `run_extract(ctx: StageContext) -> StageReport` · `register(app: typer.Typer) -> None` (`frances extract [--data DIR]`: `data: DataOpt = Path(".")` y `exit_with(lambda: run_extract(make_context(data)))`). Counts: `extract.extracted`, `extract.skipped_unsupported`, `extract.error`.

- [ ] **Step 1: Write the failing test**

```python
def test_dispatch_by_mime(tmp_path, fakes):
    ctx = ctx_with_blobs(tmp_path, {"pdf": "application/pdf", "png": "image/png",
                                    "txt": "text/plain", "doc": "application/vnd.google-apps.document"})
    rep = run_extract(ctx)
    assert rep.exit_code() == 0 and rep.counts["extract.extracted"] == 4
    assert methods(ctx) == {"pdf": "pdf_text", "png": "image_ocr", "txt": "plain", "doc": "export_text"}
    assert (fakes.pdf_calls, fakes.ocr_calls) == (1, 1)
def test_row_and_file_agree(tmp_path, fakes):
    ctx = ctx_with_blobs(tmp_path, {"pdf": "application/pdf"})
    run_extract(ctx)
    row = extraction_row(ctx, "pdf")
    path = ctx.paths.extraction_path(row["blob_sha256"], "1")
    ex = Extraction.model_validate_json(path.read_text(encoding="utf-8"))
    assert row["path"] == str(path.relative_to(ctx.paths.root)) and row["extractor_version"] == "1"
    assert ex.char_count == row["char_count"] == sum(len(b.text) for b in ex.blocks)
    assert row["lang"] == "fr" and ex.blocks[0].source == attachment_of(ctx, "pdf") and ex.blocks[0].page == 1
    assert path.read_text(encoding="utf-8") == json.dumps(ex.model_dump(), sort_keys=True, indent=0, ensure_ascii=False)
def test_extractor_error_is_partial_and_redacted(tmp_path, fakes):
    fakes.pdf_raises = RuntimeError(f"boom en {tmp_path}/secret.pdf")
    ctx = ctx_with_blobs(tmp_path, {"pdf": "application/pdf", "txt": "text/plain"})
    rep = run_extract(ctx)
    assert rep.status == "partial" and rep.exit_code() == 2 and rep.counts["extract.extracted"] == 1
    assert str(tmp_path) not in " ".join(rep.errors)
```

Además: `test_extract_idempotent` (dos `run_extract` seguidos → el segundo con `counts["extract.extracted"] == 0` y `fakes.pdf_calls == 1`). `fakes` es un fixture local que hace `monkeypatch.setattr(run, "extract_pdf", ...)` (devuelve `[PageText(1, "Je suis étudiant à l'université de Bogotá.", "pdf_text")]`) y `monkeypatch.setattr(run, "ocr_file", ...)`, contando llamadas; `ctx_with_blobs` parte de `make_ctx` (Restricciones) y siembra ítem, adjuntos `downloaded` y blobs vía `BlobStore.put_bytes` con SQL directo.

- [ ] **Step 2: Run test to verify it fails** — Run: `uv run pytest tests/extract/test_run.py -v` · Expected: FAIL with "ModuleNotFoundError: No module named 'frances.extract.run'"
- [ ] **Step 3: Implement `extract/repo.py` y `run_extract(ctx) -> StageReport` in `src/frances/extract/run.py`**
Despacho: nativo → `export_text`; `application/pdf` → `extract_pdf(path, ocr=ocr_image)` con un bloque por página (`method` = `pdf_ocr` si alguna página usó OCR, si no `pdf_text`); `image/*` → `image_ocr`; `text/*` → `plain` (UTF-8 con `errors="replace"`); otro mime → `skipped_unsupported` (no es parcial). `lang` de la fila = idioma con más caracteres entre los bloques (`"unknown"` si no hay bloques). Archivo escrito antes de insertar la fila, en una tx por candidato; una excepción por candidato → `error` + `redact(str(exc))` y sigue con el siguiente. `created_at` = `format_ts(ctx.now())`.
- [ ] **Step 4: Run test to verify it passes** — Run: `uv run pytest tests/extract -v` · Expected: PASS (todo `tests/extract`)
- [ ] **Step 5: Commit** — `git add src/frances/extract/run.py src/frances/extract/repo.py tests/extract/test_run.py` y `git commit -m "feat(extract): etapa extract idempotente por blob y versión [EXT-04]"`

## Preguntas de contrato

Resueltas en el plan maestro:

1. Contenido de los fixtures (FND-05) → decisión del punto de fixtures: solo se usa lo que FND-05 exporta y declara (ver «Restricciones»); ids y conteos se derivan leyendo los JSON y los metadatos del mock; sin rutas nombradas ni `PNG_META`.
2. `frances.errors` y conversión a exit codes → FND-04 (`FrancesError.exit_code`, `AuthError` 3, `ConfigError` 4) + R-05 (`exit_with`).
3. Dependencias no declaradas → R-10 (SYN-01 += SYN-02; FET-03 += SYN-01).
4. Fábrica de `StageContext` desde `--data DIR` → R-04/R-05 (`make_context` en FND-03, `DataOpt` por comando).
5. Export > 10 MB y las dos clases `TooLargeError`/`BlobTooLargeError` → R-26 (aceptado: `partial` en el run que lo detecta; dos clases).
6. Red dentro de la tx en SYN-04 → R-26 (aceptado solo para SYN-04).
7. Firmas de FND-04/FND-01 → R-06 (`norm_ts` solo `str`; `format_ts` para datetimes), R-08 (`Settings` por sección); Tesseract `fra`+`spa` lo instala la CI de FND-01.

- Lo que suponíamos de los fixtures (export text/plain del Slides, streams del curso `FRENCH_COURSE_ID`, archivos `slides`/`locked`/`pdf_v2` adjuntos) → R-29: lo garantiza FND-05.

Ninguna abierta.

## Autorrevisión

1. **Tareas:** están las 14 asignadas, en el orden pedido. Cada una abre con `Deps:` copiado de `tasks.yaml` y su Files solo crea rutas de su `owns`.
2. **Un paso, una cosa:** cada Step 3 fija firma, archivo y valores del spec (10 min de solape, `pageSize=100`, 5 intentos, backoff 1 s × 2^n ± 20 %, 50 MB, 40 caracteres, 200 dpi, `fra+spa`, `--psm 6`, umbrales de idioma 12 letras y 25 %, `EXTRACTOR_VERSION = "1"`). Solo se describe el algoritmo cuando la firma no lo determina.
3. **Nombres:** `run_sync`, `run_reconcile`, `run_fetch`, `run_extract`, `detect_lang`, `split_blocks`, `SCOPES` y los modelos coinciden con el plan maestro. Los nombres nuevos (`RetryExhaustedError`, `BlobTooLargeError`, `HttpxAuthRequest`, `GoogleApi.refresh`, las funciones de los `repo.py`) los define una sola tarea, en su bloque Produces.
4. **Review Focus:** están los tests de los ítems 1 (SYN-04), 2 (FET-03) y 4 (FET-03, tres tests).
5. **Proporción:** el plan tiene tests y firmas, no cuerpos de función. El único algoritmo descrito en prosa es el corte por watermark y el despacho de fetch/extract.
