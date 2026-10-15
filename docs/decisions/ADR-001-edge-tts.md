# ADR-001: Voces y límites de Edge-TTS
Fecha: 2026-10-15 · Estado: aceptado · Tarea: SPK-01

## Contexto

El diseño da por supuesto que Edge-TTS expone 13 voces francesas
(`fr-FR`, `fr-BE`, `fr-CA`, `fr-CH`), que el audio sale en MP3 mono de
24 kHz (~48 kbps) y que se puede sintetizar con concurrencia limitada sin
errores. Este spike lo confirma midiendo con `edge-tts` contra el servicio
real y fija la versión exacta y la concurrencia que usarán AUD-01/AUD-03/AUD-06.

## Opciones medidas

Versión exacta medida: `edge-tts==7.3.1` (última estable publicada el
2026-10-13; verificada en PyPI el día de la tarea). Frase de prueba:
"Bonjour, comment allez-vous ?".

### Voces fr-* encontradas (13/13, sin altas ni bajas)

| id | gender | accent | locale |
| --- | --- | --- | --- |
| fr-BE-CharlineNeural | Female | Bélgica | fr-BE |
| fr-BE-GerardNeural | Male | Bélgica | fr-BE |
| fr-CA-AntoineNeural | Male | Canadá (Quebec) | fr-CA |
| fr-CA-JeanNeural | Male | Canadá (Quebec) | fr-CA |
| fr-CA-SylvieNeural | Female | Canadá (Quebec) | fr-CA |
| fr-CA-ThierryNeural | Male | Canadá (Quebec) | fr-CA |
| fr-CH-ArianeNeural | Female | Suiza | fr-CH |
| fr-CH-FabriceNeural | Male | Suiza | fr-CH |
| fr-FR-DeniseNeural | Female | Francia | fr-FR |
| fr-FR-EloiseNeural | Female | Francia | fr-FR |
| fr-FR-HenriNeural | Male | Francia | fr-FR |
| fr-FR-RemyMultilingualNeural | Male | Francia | fr-FR |
| fr-FR-VivienneMultilingualNeural | Female | Francia | fr-FR |

Coinciden exactamente con las 13 esperadas por el plan: 5× fr-FR, 2× fr-BE,
4× fr-CA, 2× fr-CH.

### Formato real (ffprobe sobre clips sintetizados, 3 concursos × spot-check)

| clip | codec_name | sample_rate | channels | bit_rate |
| --- | --- | --- | --- | --- |
| bench_c1 (fr-BE-CharlineNeural) | mp3 | 24000 | 1 | 48000 |
| bench_c2 (fr-FR-EloiseNeural) | mp3 | 24000 | 1 | 48000 |
| bench_c4 (fr-FR-VivienneMultilingualNeural) | mp3 | 24000 | 1 | 48000 |

Formato confirmado: **MP3, 24000 Hz, 1 canal, 48 kbps** en las 3 tandas
(60/60 clips no vacíos; cada una de las 13 voces sintetizada al menos una vez).

### Concurrencia (20 clips por nivel, rotando las 13 voces)

| concurrency | clips | ok | latency_mean_s | latency_p95_s | error_rate |
| --- | --- | --- | --- | --- | --- |
| 1 | 20 | 20/20 | 1.081 | 1.548 | 0.000 |
| 2 | 20 | 20/20 | 1.008 | 1.542 | 0.000 |
| 4 | 20 | 20/20 | 1.074 | 1.538 | 0.000 |

## Decisión

- Voces: se adopta la tabla de arriba tal cual (13/13 confirmadas).
- Versión: `edge-tts==7.3.1`.
- Formato: MP3 24 kHz mono 48 kbps.
- **`concurrency_recommended = 2`**. Regla del plan: mayor nivel con error
  rate 0 y p95 < 2× la de concurrencia 1 (2 si empatan). Los tres niveles
  tienen error rate 0 y p95 casi idéntico (1.548 / 1.542 / 1.538 s, dispersión
  < 1 %, muy por debajo del umbral 2×): empatan, luego 2. Además 2 es el
  valor conservador frente al extremo gratuito de Edge (riesgo de throttling
  a escala con concurrencias altas).

## Consecuencias para las tareas AUD-01, AUD-03, AUD-06

- AUD-01: copiar la tabla `id | gender | accent | locale` a
  `src/frances/audio/voices_default.yaml` (las 13 voces; `fr-FR-EloiseNeural`
  pendiente de calificación infantil en SPK-02/ADR-002).
- AUD-03: fijar `edge-tts==7.3.1` y concurrencia 2 en el motor Edge-TTS.
- AUD-06: dimensionar la cola de síntesis con concurrencia 2 y fallback
  Edge→Azure según lo medido (latencia típica ~1.0–1.5 s por clip corto;
  incluye sobrecosto del proxy de egress del entorno de medición).

## Cómo reproducir

```bash
export UV_CACHE_DIR=$PWD/.cache/uv
export UV_PYTHON_INSTALL_DIR=$PWD/.cache/uv-python
uv run scripts/spikes/spk01_edge_voices.py list
uv run scripts/spikes/spk01_edge_voices.py bench --concurrency 1 --clips 20
uv run scripts/spikes/spk01_edge_voices.py bench --concurrency 2 --clips 20
uv run scripts/spikes/spk01_edge_voices.py bench --concurrency 4 --clips 20
uv run scripts/spikes/spk01_edge_voices.py probe
```

Los clips quedan en `.cache/spikes/spk01/` (ignorado por git).
Notas del entorno de medición (solo afectan al spike, no a producción):
el egress MITM exige confiar en su CA (`SSL_CERT_FILE`), pasar el proxy
explícito al `ws_connect` y tolerar que reescribe `Connection: Upgrade` a
`close` en el 101 del handshake WebSocket; el script
`scripts/spikes/spk01_edge_voices.py` contiene esos tres parches acotados y
documentados (sin desactivar TLS; no alteran los bytes de audio). En el
runner self-hosted de producción (sin MITM) no hacen falta.
