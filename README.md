# Frances Classroom

App personal de estudio de francés que convierte automáticamente lo publicado en Google Classroom en práctica: sincroniza los cursos, extrae el texto de los materiales, genera flashcards, produce audios con voces variadas y evalúa la pronunciación por fonema.

El contenido de estudio se empaqueta cifrado y se consume desde una PWA offline en el navegador, con repetición espaciada (FSRS) y progreso almacenado localmente.

> **Estado del proyecto:** en desarrollo activo. La interfaz y los comandos pueden cambiar sin aviso.

## Características

- **Sincronización incremental de Google Classroom**: tareas, materiales, anuncios y temas de los cursos activos, con adjuntos de Drive (PDF, imágenes, Docs/Slides/Sheets), enlaces y YouTube. Reconciliación completa semanal para detectar borrados.
- **Extracción de texto**: PDF con capa de texto, OCR (`fra+spa`) para escaneados e imágenes, y exportación de Google Docs/Slides.
- **Flashcards y fichas de estudio**: tarjetas de vocabulario, frase, gramática, conjugación y taladro, con generador LLM opcional y respaldo determinista (spaCy + traducción automática).
- **Audio TTS por lotes**: voces francesas variadas (adultos, adolescentes, niños), cacheadas por hash y pre-generadas fuera del runtime.
- **Evaluación de pronunciación por fonema**: práctica en voz alta con puntajes de frase, palabra y fonema, historial y taladro automático de fonemas débiles.
- **PWA offline**: React + Vite, repaso con el algoritmo FSRS, visor de PDF, buscador de tarjetas y almacenamiento en IndexedDB.
- **Privacidad por diseño**: el contenido viaja cifrado (AES-256-GCM con clave derivada por PBKDF2) y los secretos nunca tocan el repositorio ni los logs.

## Requisitos previos

- **Python** 3.11–3.13 y [**uv**](https://docs.astral.sh/uv/) como gestor de dependencias.
- **Node.js** 22 (con npm) para el frontend y el worker.
- Dependencias de sistema para OCR y audio (opcional para desarrollo básico):
  `tesseract-ocr` con los paquetes de idiomas `fra` y `spa`, `ffmpeg` y `espeak-ng`.

En Debian/Ubuntu:

```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-fra tesseract-ocr-spa espeak-ng ffmpeg
```

## Instalación

### Backend (Python)

```bash
uv sync --all-groups
```

Esto instala el paquete `frances` y sus dependencias, incluidas las de desarrollo (pytest, ruff, mypy).

### Frontend (`web/`)

```bash
npm --prefix web ci
```

### Worker (`worker/`)

Opcional: solo hace falta si vas a desplegar el servicio de distribución del bundle.

```bash
npm --prefix worker ci
```

## Configuración

### `frances.toml`

La configuración no sensible vive en un TOML dentro del *repo de datos* (el directorio que pasas con `--data`). Copia el ejemplo y ajústalo:

```bash
cp frances.example.toml data/frances.toml   # ajusta la ruta a tu repo de datos
```

Secciones disponibles: `classroom` (cursos a incluir, tamaño máximo de descargas), `cards` (motor de tarjetas y topes diarios), `audio` (voces y cuotas de TTS), `translator` (tope mensual) y `bundle` (parámetros de cifrado y tamaño máximo). Todas tienen valores por defecto razonables; si el archivo no existe, la app arranca con los defaults.

**Los secretos nunca van en el TOML**: solo se leen de variables de entorno.

### Variables de entorno

Las variables sensibles se definen en el entorno (en producción, como secretos de CI). Las principales para la generación de tarjetas con LLM:

| Variable | Obligatoria | Uso |
| --- | --- | --- |
| `LLM_BASE_URL` | No | URL base del endpoint de chat que genera las tarjetas (API estándar de chat/completions). Si no está definida, la generación LLM queda desactivada y se usa el respaldo determinista. |
| `LLM_API_KEY` | No | Clave de API para autenticarse contra ese endpoint. Nunca la escribas en el TOML ni en el código. |
| `LLM_MODEL` | No | Modelo a invocar en ese endpoint. |

El código no conoce proveedores concretos: cambia la URL, la clave y el modelo, y no hace falta tocar nada. Existen más variables para Google Classroom, Azure y el almacenamiento; están documentadas en `docs/superpowers/plans/2026-10-14-00-master-plan.md`.

## Uso básico

La CLI se llama `frances` y cada comando recibe `--data DIR`, la raíz del repo de datos:

```bash
uv run frances --help
```

Comandos principales:

| Comando | Descripción |
| --- | --- |
| `frances auth check` | Verifica las credenciales de Google Classroom. |
| `frances sync --data DIR` | Sincronización incremental de Classroom. |
| `frances reconcile --data DIR` | Reconciliación completa (detecta borrados). |
| `frances fetch --data DIR` | Descarga los adjuntos nuevos o modificados. |
| `frances extract --data DIR` | Extrae texto de PDFs, imágenes (OCR) y Docs/Slides. |
| `frances audio --data DIR` | Genera los audios TTS pendientes. |
| `frances dump` / `frances restore` | Volcado y restauración SQL determinista del estado. |
| `frances r2 pull` / `push` / `publish` / `prune` | Sincroniza el repo de datos con el bucket privado y publica el bundle del sitio. |
| `frances doctor` | Diagnóstico: tamaños, cuotas, pendientes y voces. |
| `frances report-failure` | Reporta fallos como issues idempotentes. |
| `frances schema export DIR` | Exporta los JSON Schema de los contratos de datos. |

Flujo típico de una corrida manual:

```bash
uv run frances sync --data data
uv run frances fetch --data data
uv run frances extract --data data
uv run frances audio --data data
```

> La orquestación diaria (generación de tarjetas, empaquetado del bundle y publicación programada) está en desarrollo; los comandos anteriores son las etapas que ya están disponibles.

## Arquitectura

```
src/frances/     Pipeline en Python (CLI Typer):
  sync/          Sincronización incremental con Classroom API (watermark en SQLite)
  fetch/         Descarga de adjuntos de Drive, content-addressed por sha256
  extract/       Extracción de texto (PDF, OCR, Docs/Slides)
  cards/         Generación de flashcards (reglas deterministas + LLM opcional)
  audio/         Síntesis TTS por lotes con política de voces y caché por hash
  bundle/        Empaquetado cifrado del contenido (formato FRB1: AES-256-GCM)
  ops/           Operación: R2, diagnóstico y reporte de fallos
  db/            Store SQLite y volcado SQL determinista
  models/        Contratos Pydantic (fuente de los JSON Schema)

web/             PWA en React 19 + TypeScript estricto (Vite):
                 repaso FSRS (ts-fsrs), IndexedDB (idb), visor PDF (pdfjs-dist)

worker/          Cloudflare Worker que sirve el bundle cifrado desde un bucket
                 privado, con CORS limitado al origen de la app
```

El repo de datos (`--data`) es una réplica local de un bucket privado: configuración, estado (`state/state.sql`), blobs por sha256, extracciones, audios y el bundle publicado. El pipeline corre programado en CI; el navegador solo consume el bundle cifrado.

## Tests

Los tests de Python corren sin red y con cobertura mínima del 85 %:

```bash
uv run pytest
```

Pruebas que necesitan red o modelos pesados están marcadas `@pytest.mark.heavy` y se excluyen por defecto.

Calidad de código:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

Frontend y worker:

```bash
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test

npm --prefix worker run typecheck
npm --prefix worker test
```

> **Nota:** nunca se commitean datos reales del Classroom. Todos los fixtures se generan con `tests/fixtures/make_fixtures.py`.

## Licencia

[MIT](LICENSE)
