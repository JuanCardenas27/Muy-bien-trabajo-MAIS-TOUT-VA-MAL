from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import pytest

from frances.audio.post import ffmpeg_available, postprocess, probe_duration_ms
from frances.errors import FrancesError


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def make_sine_wav(
    path: Path, seconds: float = 1.0, rate: int = 44100, channels: int = 2
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ar",
            str(rate),
            "-ac",
            str(channels),
            str(path),
        ]
    )
    return path


def ffprobe_stream(path: Path) -> dict[str, str]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,bit_rate",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)["streams"][0]


def dominant_frequency(path: Path, rate: int = 24000) -> float:
    raw = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(rate),
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    n = len(raw) // 2
    samples = struct.unpack(f"<{n}h", raw[: n * 2])
    samples = samples[2000:-2000]
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if (a < 0) != (b < 0))
    return crossings / 2 / (len(samples) / rate)


def test_sine_wav_becomes_spec_mp3(tmp_path: Path) -> None:
    src = make_sine_wav(tmp_path / "s.wav", seconds=1.0)
    ms = postprocess(src, tmp_path / "out" / "a.mp3")
    info = ffprobe_stream(tmp_path / "out" / "a.mp3")
    assert info["codec_name"] == "mp3"
    assert info["sample_rate"] == "24000"
    assert info["channels"] == 1
    assert 44_000 <= int(info["bit_rate"]) <= 52_000
    assert 940 <= ms <= 1060
    assert probe_duration_ms(tmp_path / "out" / "a.mp3") == ms


def test_no_tmp_left_behind(tmp_path: Path) -> None:
    src = make_sine_wav(tmp_path / "s.wav", seconds=0.5)
    postprocess(src, tmp_path / "out" / "a.mp3")
    assert list((tmp_path / "out").glob("*.mp3.tmp")) == []


def test_invalid_input_raises_and_cleans(tmp_path: Path) -> None:
    src = tmp_path / "bad.txt"
    src.write_text("no soy audio", encoding="utf-8")
    with pytest.raises(FrancesError):
        postprocess(src, tmp_path / "out" / "a.mp3")
    assert not (tmp_path / "out" / "a.mp3").exists()
    assert list((tmp_path / "out").glob("*.mp3.tmp")) == []


def test_ffmpeg_available_true_in_ci() -> None:
    assert ffmpeg_available() is True


def test_shift_ratio_keeps_duration_and_raises_pitch(tmp_path: Path) -> None:
    src = make_sine_wav(tmp_path / "s.wav", seconds=1.0, rate=24000, channels=1)
    ms = postprocess(src, tmp_path / "out" / "a.mp3", shift_ratio=1.25)
    assert 980 <= ms <= 1020
    assert 530 <= dominant_frequency(tmp_path / "out" / "a.mp3") <= 570
