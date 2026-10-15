"""Post-proceso de audio con ffmpeg: MP3 mono 24 kHz a -16 LUFS.

ffmpeg se usa solo como binario en subprocess (Global Constraints); nunca se
importa. El formato final es único: MP3 mono, 24 kHz, 48 kbps, loudness
integrada -16 LUFS. Las voces sintéticas reciben además ``shift_ratio``, que
sube tono y timbre con ``asetrate``+``aresample``+``atempo`` sin cambiar la
duración (R-16).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from frances.errors import FrancesError

LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
SAMPLE_RATE = 24000

_ERR_TAIL = 500


def ffmpeg_available() -> bool:
    """True si ``ffmpeg`` y ``ffprobe`` están en el PATH."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _filter_chain(shift_ratio: float) -> str:
    if shift_ratio == 1.0:
        return LOUDNORM
    return (
        f"asetrate={SAMPLE_RATE * shift_ratio:g},aresample={SAMPLE_RATE},"
        f"atempo={1 / shift_ratio:g},{LOUDNORM}"
    )


def postprocess(src: Path, dst: Path, shift_ratio: float = 1.0) -> int:
    """Normaliza ``src`` a MP3 mono 24 kHz y escribe ``dst`` de forma atómica.

    Devuelve la duración en milisegundos del archivo resultante.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".mp3.tmp")
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-af",
        _filter_chain(shift_ratio),
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        "1",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "48k",
        "-f",
        "mp3",
        str(tmp),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise FrancesError(f"ffmpeg falló: {proc.stderr[-_ERR_TAIL:]}")
        os.replace(tmp, dst)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        if isinstance(exc, FrancesError):
            raise
        raise FrancesError(f"ffmpeg falló: {exc}") from exc
    return probe_duration_ms(dst)


def probe_duration_ms(path: Path) -> int:
    """Duración de ``path`` en milisegundos vía ``ffprobe``."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise FrancesError(f"ffprobe falló: {proc.stderr[-_ERR_TAIL:]}")
    try:
        return round(float(proc.stdout.strip()) * 1000)
    except ValueError as exc:
        raise FrancesError(f"ffprobe devolvió una duración inválida: {proc.stdout!r}") from exc
