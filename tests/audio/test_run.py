"""Etapa audio: cola, concurrencia y fallback Edge→Azure (AUD-06)."""

from __future__ import annotations

import asyncio
import math
import struct
import wave
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

import frances.audio.run as audio_run
from frances.audio.azure_tts import AzureTtsEngine, CapExceeded
from frances.audio.edge import EdgeEngine, EngineError
from frances.audio.run import EngineSet, run_audio
from frances.audio.voices import load_voices
from frances.db.store import Store
from frances.errors import ConfigError
from frances.models.audio import Voice
from frances.stage import StageContext, make_context

NOW = "2026-10-14T15:00:00.000000Z"

CARDS = (
    ("c_voc1", "Bonjour", "Je dis bonjour"),
    ("c_voc2", "Salut", "Je dis salut"),
    ("c_voc3", "Merci", "Je dis merci"),
)


def _sine_wav(path: Path, seconds: float = 1.0) -> None:
    """Escribe un WAV PCM de seno 440 Hz, válido como entrada de ``postprocess``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 24000
    frames = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(int(rate * seconds))
    )
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames)


def _write_sine(_text: str, _voice: Voice, out: Path) -> None:
    _sine_wav(out)


def _fail_retryable(_text: str, _voice: Voice, _out: Path) -> None:
    raise EngineError("edge caída transitoria de red", retryable=True)


def _fail_final(_text: str, _voice: Voice, _out: Path) -> None:
    raise EngineError("edge fallo definitivo con Bearer abc.def.ghi", retryable=False)


def _cap_after(n: int) -> Callable[[str, Voice, Path], None]:
    """Lanza ``CapExceeded`` a partir de la llamada ``n + 1``; antes escribe seno."""
    state = {"calls": 0}

    def behavior(text: str, voice: Voice, out: Path) -> None:
        state["calls"] += 1
        if state["calls"] > n:
            raise CapExceeded("tope mensual de Azure TTS agotado: 450000/450000")
        _write_sine(text, voice, out)

    return behavior


class FakeEngine:
    """Motor falso que cumple el protocolo ``TtsEngine`` del plan maestro."""

    family = "ms-neural"
    family_version = "1"

    def __init__(self, behavior: Callable[[str, Voice, Path], None]) -> None:
        self.calls: list[tuple[str, str, Path]] = []
        self._behavior = behavior

    async def synthesize(self, text: str, voice: Voice, out_wav_or_mp3: Path) -> None:
        self.calls.append((text, voice.id, out_wav_or_mp3))
        self._behavior(text, voice, out_wav_or_mp3)


async def _no_sleep(_seconds: float) -> None:
    """Sustituye el backoff real en los tests."""


def _install_engines(
    monkeypatch: pytest.MonkeyPatch,
    edge_behavior: Callable[[str, Voice, Path], None],
    azure_behavior: Callable[[str, Voice, Path], None] | None = None,
) -> tuple[FakeEngine, FakeEngine | None]:
    edge = FakeEngine(edge_behavior)
    azure = FakeEngine(azure_behavior) if azure_behavior is not None else None
    monkeypatch.setattr(
        "frances.audio.run.make_engines",
        lambda _ctx: EngineSet(edge=edge, azure=azure),
    )
    return edge, azure


def _insert_cards(store: Store) -> None:
    with store.tx() as conn:
        for card_id, front, example in CARDS:
            conn.execute(
                "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    card_id,
                    "vocab",
                    front,
                    "Hola",
                    example,
                    "Digo hola",
                    None,
                    None,
                    "[]",
                    "[]",
                    "rules",
                    "1",
                    0,
                    NOW,
                    NOW,
                ),
            )


@pytest.fixture
def ctx_with_cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[StageContext]:
    """Contexto con 3 tarjetas vocab, ``voices.yaml`` vacío y backoff en no-op."""
    ctx = make_context(tmp_path / "data", env={})
    (ctx.paths.root / "voices.yaml").write_text("", encoding="utf-8")
    _insert_cards(ctx.store)
    monkeypatch.setattr("frances.audio.run._sleep", _no_sleep)
    yield ctx
    ctx.store.close()


def _statuses(store: Store) -> dict[str, int]:
    rows = store.conn.execute("SELECT status, count(*) FROM audio GROUP BY status").fetchall()
    return {status: count for status, count in rows}


def test_happy_path_writes_files_and_marks_done(
    ctx_with_cards: StageContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    edge, _azure = _install_engines(monkeypatch, _write_sine)
    report = run_audio(ctx_with_cards, None)
    assert report.stage == "audio"
    assert report.status == "ok"
    assert report.counts["planned"] == 12
    assert report.counts["done"] == 12
    assert report.counts["failed"] == 0
    assert report.counts["left_pending"] == 0
    assert report.counts["azure_used"] == 0
    assert len(edge.calls) == 12
    rows = ctx_with_cards.store.conn.execute(
        "SELECT cache_key, status, engine_used, path, duration_ms FROM audio"
    ).fetchall()
    assert len(rows) == 12
    for key, status, engine_used, path, duration_ms in rows:
        assert (status, engine_used, path) == ("done", "edge", f"audio/{key}.mp3")
        assert duration_ms is not None and duration_ms > 0
        assert ctx_with_cards.paths.audio_path(key).exists()


def test_breaker_switches_to_azure_after_three_failures(
    ctx_with_cards: StageContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    edge, _azure = _install_engines(monkeypatch, _fail_retryable, _write_sine)
    report = run_audio(ctx_with_cards, None)
    assert report.status == "partial"
    assert report.counts["planned"] == 12
    assert report.counts["failed"] == 3
    assert report.counts["done"] == 9
    assert report.counts["azure_used"] == 9
    assert report.counts["left_pending"] == 0
    assert len(edge.calls) == 9  # 3 clips x 3 intentos
    engines = dict(
        ctx_with_cards.store.conn.execute(
            "SELECT engine_used, count(*) FROM audio WHERE status = 'done' GROUP BY engine_used"
        ).fetchall()
    )
    assert engines == {"azure": 9}


def test_non_retryable_trips_breaker_immediately(
    ctx_with_cards: StageContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    edge, _azure = _install_engines(monkeypatch, _fail_final, _write_sine)
    report = run_audio(ctx_with_cards, None)
    assert report.status == "partial"
    assert report.counts["failed"] == 1
    assert report.counts["done"] == 11
    assert report.counts["azure_used"] == 11
    assert len(edge.calls) == 1  # un fallo no retryable basta


def test_cap_exceeded_leaves_rest_pending_and_partial(
    ctx_with_cards: StageContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_engines(monkeypatch, _write_sine, _cap_after(1))
    report = run_audio(ctx_with_cards, None, "azure")
    assert report.status == "partial"
    assert report.counts["done"] == 1
    assert report.counts["failed"] == 0
    assert report.counts["azure_used"] == 1
    assert report.counts["left_pending"] == 11
    pending = ctx_with_cards.store.conn.execute(
        "SELECT attempts FROM audio WHERE status = 'pending'"
    ).fetchall()
    assert pending == [(0,)] * 11  # sin intento sumado


def test_max_clips_respected(ctx_with_cards: StageContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_engines(monkeypatch, _write_sine)
    report = run_audio(ctx_with_cards, 2)
    assert report.status == "ok"  # cortar por max_clips no es partial
    assert report.counts["done"] == 2
    assert report.counts["failed"] == 0
    assert _statuses(ctx_with_cards.store) == {"done": 2, "pending": 10}


def test_failed_after_five_attempts(
    ctx_with_cards: StageContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_engines(monkeypatch, _fail_retryable)
    for _ in range(5):
        report = run_audio(ctx_with_cards, None, "edge")
    assert report.status == "partial"
    assert _statuses(ctx_with_cards.store) == {"failed": 12}
    rows = ctx_with_cards.store.conn.execute(
        "SELECT attempts FROM audio WHERE status = 'failed'"
    ).fetchall()
    assert rows == [(5,)] * 12
    # Los terminales no vuelven a la cola: un run más no tiene trabajo.
    final = run_audio(ctx_with_cards, None, "edge")
    assert final.status == "ok"
    assert final.counts["done"] == 0 and final.counts["failed"] == 0


def test_error_is_redacted(ctx_with_cards: StageContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_engines(monkeypatch, _fail_final)
    run_audio(ctx_with_cards, None)
    errors = ctx_with_cards.store.conn.execute(
        "SELECT error FROM audio WHERE attempts = 1"
    ).fetchall()
    assert len(errors) == 1
    assert "[REDACTED]" in errors[0][0]
    assert "Bearer" not in errors[0][0]


def test_synthetic_voice_rendered_with_shift(
    ctx_with_cards: StageContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx_with_cards.settings.audio.fixed_voices = ["fr-FR-DeniseNeural", "synth-teen-f"]
    _install_engines(monkeypatch, _write_sine)
    recorded: list[tuple[Path, Path, float]] = []
    real_postprocess = audio_run.postprocess

    def spy(src: Path, dst: Path, shift_ratio: float = 1.0) -> int:
        recorded.append((src, dst, shift_ratio))
        return real_postprocess(src, dst, shift_ratio)

    monkeypatch.setattr("frances.audio.run.postprocess", spy)
    report = run_audio(ctx_with_cards, None)
    assert report.status == "ok"
    voices_by_id = {voice.id: voice for voice in load_voices(ctx_with_cards.paths)}
    for src, dst, ratio in recorded:
        voice_id = ctx_with_cards.store.conn.execute(
            "SELECT voice_id FROM audio WHERE cache_key = ?", (dst.stem,)
        ).fetchone()[0]
        assert ratio == voices_by_id[voice_id].shift_ratio
        assert src.name == f"{dst.stem}.src"
    synth_keys = {
        row[0]
        for row in ctx_with_cards.store.conn.execute(
            "SELECT cache_key FROM audio WHERE voice_id = 'synth-teen-f'"
        ).fetchall()
    }
    assert len(synth_keys) == 3  # una fila por tarjeta
    synth_calls = [(src, dst, ratio) for src, dst, ratio in recorded if dst.stem in synth_keys]
    assert len(synth_calls) == 3
    assert all(ratio == 1.08 for _src, _dst, ratio in synth_calls)


def _app() -> typer.Typer:
    # Segundo comando solo para que typer use modo grupo (con uno solo
    # invocaría el comando directamente sin aceptar su nombre); igual que
    # tests/core/test_cli.py.
    app = typer.Typer()

    @app.command()
    def ping() -> None:
        typer.echo("pong")

    audio_run.register(app)
    return app


def test_cli_audio_exit_code_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "data"
    (root / ".cache").mkdir(parents=True)
    store = Store.open(root / ".cache" / "state.db")
    with store.tx() as conn:
        conn.execute(
            "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "c_cli",
                "vocab",
                "Bonjour",
                "Hola",
                "Je dis bonjour",
                "Digo hola",
                None,
                None,
                "[]",
                "[]",
                "rules",
                "1",
                0,
                NOW,
                NOW,
            ),
        )
    store.close()
    _install_engines(monkeypatch, _fail_final, _cap_after(0))
    monkeypatch.setattr("frances.audio.run._sleep", _no_sleep)
    result = CliRunner().invoke(_app(), ["audio", "--data", str(root), "--max", "5"])
    assert result.exit_code == 2, result.output
    # El reporte partial de verdad: la fila quedó en intento fallado, no pending.
    store = Store.open(root / ".cache" / "state.db")
    try:
        rows = store.conn.execute("SELECT status, attempts FROM audio").fetchall()
    finally:
        store.close()
    assert ("pending", 1) in rows  # el clip fallado: un intento, no terminal
    assert ("pending", 0) in rows  # los que quedaron sin despachar por el tope


def test_make_engines_edge_only_without_key(tmp_path: Path) -> None:
    ctx = make_context(tmp_path / "data", env={})
    try:
        engines = audio_run.make_engines(ctx)
        assert isinstance(engines.edge, EdgeEngine)
        assert engines.azure is None
    finally:
        ctx.store.close()


def test_make_engines_azure_from_env(tmp_path: Path) -> None:
    key = "clave-azure-fake-0001"
    ctx = make_context(
        tmp_path / "data", env={"AZURE_SPEECH_KEY": key, "AZURE_SPEECH_REGION": "westeurope"}
    )
    try:
        engines = audio_run.make_engines(ctx)
        assert isinstance(engines.edge, EdgeEngine)
        assert isinstance(engines.azure, AzureTtsEngine)
    finally:
        ctx.store.close()
    # Sin región explícita también se configura Azure (usa "eastus" por defecto).
    default = make_context(tmp_path / "data2", env={"AZURE_SPEECH_KEY": key})
    try:
        assert isinstance(audio_run.make_engines(default).azure, AzureTtsEngine)
    finally:
        default.store.close()


def test_forced_azure_without_key_raises(tmp_path: Path) -> None:
    ctx = make_context(tmp_path / "data", env={})
    try:
        with pytest.raises(ConfigError):
            run_audio(ctx, None, "azure")
    finally:
        ctx.store.close()


def test_postprocess_failure_marks_clip_failed(
    ctx_with_cards: StageContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def write_junk(_text: str, _voice: Voice, out: Path) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("no soy audio", encoding="utf-8")

    _install_engines(monkeypatch, write_junk)
    report = run_audio(ctx_with_cards, None, "edge")
    assert report.status == "partial"
    assert report.counts["done"] == 0
    assert report.counts["failed"] == 12
    # Fallo de clip (no terminal): attempts 1 y la fila sigue pending.
    assert _statuses(ctx_with_cards.store) == {"pending": 12}
    rows = ctx_with_cards.store.conn.execute(
        "SELECT attempts, error FROM audio WHERE error IS NOT NULL"
    ).fetchall()
    assert [attempts for attempts, _error in rows] == [1] * 12
    assert all("ffmpeg" in error for _attempts, error in rows)


def test_clip_with_unknown_voice_fails(
    ctx_with_cards: StageContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_engines(monkeypatch, _write_sine)
    key = "f" * 32
    with ctx_with_cards.store.tx() as conn:
        # Tarjeta stale: plan_audio no la toca y el enlace manual sobrevive.
        conn.execute(
            "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "c_stale",
                "vocab",
                "Stale",
                "Hola",
                None,
                None,
                None,
                None,
                "[]",
                "[]",
                "rules",
                "1",
                1,
                NOW,
                NOW,
            ),
        )
        conn.execute(
            "INSERT INTO audio VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                key,
                "Stale",
                "stale",
                "fr-XX-DesconocidaNeural",
                "ms-neural",
                "1",
                "pending",
                None,
                None,
                None,
                None,
                0,
                None,
                NOW,
            ),
        )
        conn.execute("INSERT INTO card_audio VALUES ('c_stale', 'front', ?)", (key,))
    report = run_audio(ctx_with_cards, None, "edge")
    assert report.status == "partial"
    assert report.counts["done"] == 12
    assert report.counts["failed"] == 1
    error = ctx_with_cards.store.conn.execute(
        "SELECT error FROM audio WHERE cache_key = ?", (key,)
    ).fetchone()[0]
    assert "fr-XX-DesconocidaNeural" in error and "no está en el registro" in error


def test_real_sleep_backoff_yields() -> None:
    asyncio.run(audio_run._sleep(0))
