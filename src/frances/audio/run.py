"""Etapa audio: cola, concurrencia y fallback Edge→Azure (AUD-06).

Sintetiza la cola ``pending`` que deja ``plan_audio`` (AUD-02) con Edge-TTS
(AUD-03) y Azure TTS F0 de respaldo (AUD-04), post-procesa con ffmpeg
(AUD-05) y escribe ``audio/<key>.mp3``. Un breaker pasa el resto del run a
Azure tras fallos seguidos de Edge; el tope mensual de caracteres detiene el
despacho sin sumar intentos.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, Protocol

import typer

from frances.audio.azure_tts import AzureTtsEngine, CapExceeded
from frances.audio.edge import EdgeEngine, EngineError
from frances.audio.policy import plan_audio
from frances.audio.post import postprocess
from frances.audio.repo import AudioRow, mark_attempt_failed, mark_done, select_work
from frances.audio.voices import load_voices
from frances.cli import DataOpt, exit_with
from frances.errors import ConfigError
from frances.log import redact
from frances.models.audio import EngineFamily, Voice
from frances.stage import StageContext, StageReport, make_context
from frances.timeutil import format_ts

MAX_ATTEMPTS = 5
BREAKER_THRESHOLD = 3
CONCURRENCY = 2
MAX_SYNTH_ATTEMPTS = 3
_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0)


class TtsEngine(Protocol):
    """Protocolo de motor TTS del plan maestro."""

    family: EngineFamily
    family_version: str

    async def synthesize(self, text: str, voice: Voice, out_wav_or_mp3: Path) -> None: ...


@dataclass
class EngineSet:
    edge: TtsEngine | None
    azure: TtsEngine | None


def make_engines(ctx: StageContext) -> EngineSet:
    """Edge siempre; Azure solo si ``AZURE_SPEECH_KEY`` está en el entorno."""
    azure: TtsEngine | None = None
    key = ctx.env.get("AZURE_SPEECH_KEY")
    if key:
        region = ctx.env.get("AZURE_SPEECH_REGION") or "eastus"
        azure = AzureTtsEngine(
            key, region, ctx.store, ctx.settings.audio.azure_tts_monthly_char_cap
        )
    return EngineSet(edge=EdgeEngine(), azure=azure)


async def _sleep(seconds: float) -> None:
    """Backoff entre reintentos; los tests la reemplazan por una no-op."""
    await asyncio.sleep(seconds)


@dataclass
class _Counters:
    consecutive_edge_failures: int = 0
    breaker_tripped: bool = False
    cap_hit: bool = False
    missing_engine: bool = False
    done: int = 0
    failed: int = 0
    left_pending: int = 0
    azure_used: int = 0
    errors: list[str] = field(default_factory=list)


def _engine_for(
    engines: EngineSet, forced: Literal["edge", "azure"] | None, state: _Counters
) -> tuple[str, TtsEngine | None]:
    """Motor del clip: el forzado, o Edge/Azure según el breaker."""
    if forced is not None:
        return forced, (engines.edge if forced == "edge" else engines.azure)
    if state.breaker_tripped:
        return "azure", engines.azure
    return "edge", engines.edge


async def _synthesize_with_retries(engine: TtsEngine, text: str, voice: Voice, tmp: Path) -> None:
    """Hasta ``MAX_SYNTH_ATTEMPTS`` intentos si el error es retryable."""
    for attempt in range(1, MAX_SYNTH_ATTEMPTS + 1):
        try:
            await engine.synthesize(text, voice, tmp)
            return
        except EngineError as exc:
            if not exc.retryable or attempt == MAX_SYNTH_ATTEMPTS:
                raise
            await _sleep(_BACKOFF_SECONDS[attempt - 1])


def _mark_done(
    ctx: StageContext, row: AudioRow, engine_name: str, duration_ms: int, now_str: str
) -> None:
    with ctx.store.tx() as conn:
        mark_done(
            conn, row.cache_key, engine_name, f"audio/{row.cache_key}.mp3", duration_ms, now_str
        )


def _mark_failed(ctx: StageContext, row: AudioRow, error: str, now_str: str) -> None:
    with ctx.store.tx() as conn:
        mark_attempt_failed(conn, row.cache_key, error, MAX_ATTEMPTS, "failed", now_str)


def _trip_breaker(state: _Counters, exc: EngineError, forced: bool) -> None:
    """Cuenta fallos de Edge; el breaker solo aplica sin ``--engine``."""
    if forced:
        return
    if not exc.retryable:
        state.breaker_tripped = True
        return
    state.consecutive_edge_failures += 1
    if state.consecutive_edge_failures >= BREAKER_THRESHOLD:
        state.breaker_tripped = True


async def _process_clip(
    row: AudioRow,
    voice: Voice | None,
    sem: asyncio.Semaphore,
    state: _Counters,
    ctx: StageContext,
    engines: EngineSet,
    forced: Literal["edge", "azure"] | None,
    now_str: str,
) -> None:
    async with sem:
        if state.cap_hit:
            state.left_pending += 1
            return
        engine_name, engine = _engine_for(engines, forced, state)
        if engine is None:
            state.left_pending += 1
            state.missing_engine = True
            return
        if voice is None:
            error = redact(f"voz {row.voice_id} no está en el registro de voces")
            state.failed += 1
            state.errors.append(error)
            _mark_failed(ctx, row, error, now_str)
            return
        tmp = ctx.paths.cache / "audio_tmp" / f"{row.cache_key}.src"
        try:
            await _synthesize_with_retries(engine, row.text_norm, voice, tmp)
            duration_ms = postprocess(tmp, ctx.paths.audio_path(row.cache_key), voice.shift_ratio)
        except CapExceeded as exc:
            state.cap_hit = True
            state.left_pending += 1
            state.errors.append(redact(str(exc)))
            return
        except EngineError as exc:
            error = redact(str(exc))
            state.failed += 1
            state.errors.append(error)
            _mark_failed(ctx, row, error, now_str)
            _trip_breaker(state, exc, forced is not None)
            return
        except Exception as exc:
            error = redact(str(exc))
            state.failed += 1
            state.errors.append(error)
            _mark_failed(ctx, row, error, now_str)
            return
        _mark_done(ctx, row, engine_name, duration_ms, now_str)
        state.done += 1
        state.consecutive_edge_failures = 0
        if engine_name == "azure":
            state.azure_used += 1


async def _drain(
    ctx: StageContext,
    rows: list[AudioRow],
    voices_by_id: dict[str, Voice],
    engines: EngineSet,
    forced: Literal["edge", "azure"] | None,
    now_str: str,
) -> _Counters:
    state = _Counters()
    if not rows:
        return state
    sem = asyncio.Semaphore(CONCURRENCY)
    (ctx.paths.cache / "audio_tmp").mkdir(parents=True, exist_ok=True)
    await asyncio.gather(
        *(
            _process_clip(
                row, voices_by_id.get(row.voice_id), sem, state, ctx, engines, forced, now_str
            )
            for row in rows
        )
    )
    return state


def run_audio(
    ctx: StageContext,
    max_clips: int | None,
    engine: Literal["edge", "azure"] | None = None,
) -> StageReport:
    """Etapa audio: planifica, sintetiza la cola y registra el resultado.

    ``counts``: ``planned`` filas nuevas de ``plan_audio``; ``done`` y ``failed``
    clips procesados en este run; ``left_pending`` clips de la cola que quedaron
    ``pending`` (tope de Azure o sin motor); ``azure_used`` clips hechos con el
    respaldo. Cortar por ``max_clips`` es ``ok``.
    """
    now_str = format_ts(ctx.now())
    voices = load_voices(ctx.paths)
    engines = make_engines(ctx)
    if engine == "azure" and engines.azure is None:
        raise ConfigError("--engine azure pero AZURE_SPEECH_KEY no está configurada")
    planned = plan_audio(ctx.store, voices, ctx.settings, now_str)
    rows = select_work(
        ctx.store.conn,
        ["ms-neural"],
        ["pending"],
        MAX_ATTEMPTS,
        max_clips or ctx.settings.audio.max_clips_per_run,
    )
    state = asyncio.run(
        _drain(ctx, rows, {voice.id: voice for voice in voices}, engines, engine, now_str)
    )
    status: Literal["ok", "partial", "failed"] = (
        "partial" if (state.failed or state.cap_hit or state.missing_engine) else "ok"
    )
    return StageReport(
        stage="audio",
        status=status,
        counts={
            "planned": planned,
            "done": state.done,
            "failed": state.failed,
            "left_pending": state.left_pending,
            "azure_used": state.azure_used,
        },
        errors=state.errors,
    )


def register(app: typer.Typer) -> None:
    @app.command("audio")
    def audio(
        data: DataOpt = Path("."),
        max_clips: Annotated[
            int | None, typer.Option("--max", help="Tope de clips a sintetizar en este run")
        ] = None,
        engine: Annotated[
            Literal["edge", "azure"] | None,
            typer.Option("--engine", help="Fuerza un motor (desactiva el breaker)"),
        ] = None,
    ) -> None:
        """Etapa audio: cola, concurrencia y fallback Edge→Azure."""
        exit_with(lambda: run_audio(make_context(data), max_clips, engine))
