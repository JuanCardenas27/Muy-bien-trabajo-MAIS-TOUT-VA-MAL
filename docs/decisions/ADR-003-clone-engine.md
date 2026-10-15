# ADR-003: motor de clonación por benchmark (Chatterbox vs XTTS v2)

Fecha: 2026-10-14 · Estado: aceptado · Tarea: SPK-03

## Contexto

AUD-07 necesita fijar el motor de clonación de voz (`clone/`) con sus
versiones exactas, AUD-08 necesita el método de QA (CER con faster-whisper)
y AUD-09 necesita la estimación de rendimiento para `clone.max_per_run`
(hoy 400). Este spike mide ambos candidatos en CPU sobre la misma
referencia (Edge-TTS `fr-FR-EloiseNeural`, `ref.wav` de 12.8 s a 24 kHz
mono) y las mismas 10 frases cortas francesas (1–3 palabras, índices 0–9
del script).

**Cambio de alcance (decisión del usuario, 2026-10-14):** el plan pedía
30 clips por motor, pero el benchmark se redujo a **10 clips por motor**
porque la VM solo tiene 2 vCPU / 7 GB y Chatterbox tarda ~2 min/clip en
CPU (10 clips ≈ 20 min; 30 clips habrían sido ~1 h por motor solo para
Chatterbox, más XTTS y QA). Las 10 frases usadas son exactamente las
10 cortas (1–3 palabras) que el plan ya destacaba como el caso crítico.
El script conserva las 30 frases fijas; los benchmarks se corren con
`--limit 10`.

Máquina del benchmark: 2 vCPU, ~7 GB RAM, CPU solo, Python 3.11.17.

## Opciones medidas

| motor | s/clip medio | RTF medio | RAM pico GB | CER medio | % CER>0.15 (todas) | % CER>0.15 (1–3 palabras) | n | licencia |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| chatterbox | 119.1 | 101.43 | 5.37 | 0.000 | 0% | 0% | 10 | MIT |
| xtts | 91.1 | 58.54 | 4.71 | 0.200 | 20% | 20% | 10 | CPML (no comercial) |

Notas:

- QA idéntico para ambos: faster-whisper `small`, `compute_type="int8"`,
  `device="cpu"`, `language="fr"`; CER con `jiwer.cer` sobre `norm`
  (minúsculas sin puntuación). Umbral de fallo 0.15.
- Chatterbox: 0 fallos en 10; todos los CER = 0.000 (verificado por
  re-transcripción con `requant`). Rango por clip: 63.6–295.1 s.
- XTTS: 2 fallos en 10, ambos en frases ultracortas — `À demain.`
  (hipótesis `I don't know`) y `Bravo !` (hipótesis `Parvaux !`), con
  audio real en ambos clips (verificado con `volumedetect`: media
  −15.7 dB, pico 0 dB). Sin esos fallos, el CER medio XTTS sería 0.000.
- El primer clip XTTS (840.2 s) incluye la descarga/carga única del
  modelo; en régimen son **~7.9 s/clip (RTF ~5.5)**. Chatterbox no separa
  la carga (primer clip 124.1 s, media 119.1 s). XTTS en régimen es
  ~15× más rápido que Chatterbox.
- Rendimiento con la fórmula del plan
  (`clips_per_hour = 3600 / s_por_clip × 1 / (1 + %fallo)`, medido en
  2 vCPU): chatterbox ≈ **30 clips/h** (3600/119.1 × 1.0); XTTS régimen
  ≈ **380 clips/h** (3600/7.9 × 1/1.2). La proyección a 12c
  (`clips_per_hour_12c`) **no se midió**: se informa `≈30` como cota
  inferior en hardware modesto; re-medir en el runner self-hosted.
- Versiones exactas medidas: `chatterbox-tts==0.1.7`,
  `coqui-tts==0.27.5`, `torch==2.6.0`, `torchaudio==2.6.0`,
  `transformers==4.57.6` (el último 4.x: coqui-tts 0.27.5 importa
  `GenerationMixin` desde la raíz, roto en transformers 5.x),
  `setuptools==80.9.0` (aporta `pkg_resources`, que `perth>=1.0.0`
  exige; setuptools ≥81 lo eliminó), `faster-whisper==1.2.1`,
  `jiwer==4.0.0`, `psutil==7.2.2`, `soundfile==0.14.0`,
  `edge-tts==7.3.1` (referencia). Modelo XTTS:
  `tts_models/multilingual/multi-dataset/xtts_v2`
  (`COQUI_TOS_AGREED=1`); Chatterbox con `language_id="fr"`.
- Robustez sandbox (lección 2026-10-14): el script dirige todos sus
  temporales a `.cache/spikes/spk03/tmp` (nunca `/tmp`); `uv`/modelos
  usan la caché de `$HOME`, que sobrevive reinicios de la VM.

## Decisión

**`default_engine: chatterbox`.**

Criterio del plan (menor % CER>0.15; desempate por s/clip): chatterbox
0% frente a xtts 20%. Chatterbox no falla en ninguna frase corta —el
caso de uso central (tarjetas de 1–3 palabras)— mientras XTTS falla en
2 de 10. La velocidad favorece claramente a XTTS (~8 s frente a
~119 s/clip en régimen), pero no compensa la calidad en este
benchmark; si a futuro se añade QA por clip con reintento/fallback,
XTTS podrá reconsiderarse. Suma a favor de Chatterbox: licencia MIT
frente a CPML no comercial de XTTS v2 (confinado a `clone/` en todo
caso).

`clips_per_hour_12c ≈ 30` (cota inferior medida en 2 vCPU; re-medir en
el runner). Recomendación de `max_per_run`: **100** (≈3.5 h a 30
clips/h en hardware modesto); el techo de 400 solo vale para un runner
dimensionado (regla: `max_per_run ≤ throughput_medido × 8 h`).

## Consecuencias para las tareas AUD-07, AUD-08, AUD-09

- AUD-07: fija en `clone/pyproject.toml` `chatterbox-tts==0.1.7`,
  `torch==2.6.0`, `setuptools==80.9.0` (+ `faster-whisper==1.2.1` para
  QA local si aplica); XTTS (`coqui-tts==0.27.5`, `torch==2.6.0`,
  `torchaudio==2.6.0`, `transformers==4.57.6`) queda como alternativa
  documentada, confinada a `clone/` por su licencia CPML no comercial.
- AUD-08: implementa el QA con faster-whisper `small` int8 CPU en
  francés y CER sobre texto normalizado, umbral de fallo 0.15 (mismo
  método de este benchmark).
- AUD-09: `frances-clone run` usa `max_per_run=100` por defecto
  (≈3.5 h por lote en hardware como el medido) y reanuda por lote;
  documenta la regla de dimensionado del runner.

## Cómo reproducir

```bash
# 1. Referencia (10–15 s, fr-FR-EloiseNeural → .cache/spikes/spk03/ref.wav)
uv run --python 3.11 scripts/spikes/spk03_clone_bench.py make-ref

# 2a. Chatterbox, 10 clips (CPU; ~20 min en 2 vCPU)
uv run --python 3.11 --with chatterbox-tts==0.1.7 --with setuptools==80.9.0 \
    scripts/spikes/spk03_clone_bench.py run --engine chatterbox --limit 10

# 2b. Reconstruir chatterbox.json desde clips+log sin re-sintetizar
uv run --python 3.11 --with chatterbox-tts==0.1.7 --with setuptools==80.9.0 \
    scripts/spikes/spk03_clone_bench.py requant --engine chatterbox --limit 10

# 3. XTTS v2, 10 clips (CPU; el primer clip incluye la carga del modelo)
COQUI_TOS_AGREED=1 uv run --python 3.11 --with coqui-tts==0.27.5 \
    --with torch==2.6.0 --with torchaudio==2.6.0 --with transformers==4.57.6 \
    scripts/spikes/spk03_clone_bench.py run --engine xtts --limit 10

# 4. Tabla comparativa
uv run --python 3.11 scripts/spikes/spk03_clone_bench.py report
```

Resultados crudos (no versionados, en `.cache/spikes/spk03/`):
`ref.wav`, `clips/chatterbox/00–09.wav`, `clips/xtts/00–09.wav`,
`chatterbox.json`, `xtts.json`, `chatterbox.log`, `xtts.log`.
