"""Bundle de demostración sintético (Task BND-04, R-20).

``build_demo`` restaura ``tests/fixtures/demo_state.sql`` en un repo de datos
temporal, copia los blobs de FND-05 y el audio de ``tests/fixtures/demo_audio/``,
y escribe el bundle con una passphrase pública. ``--make-audio`` regenera el
audio con espeak-ng + ffmpeg (binarios por subprocess, sin shell).
"""

import argparse
import hashlib
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from frances.audio.voices import load_voices
from frances.bundle.run import write_bundle
from frances.cards.drills import seed_drills
from frances.db.dump import restore_sql
from frances.models.bundle import BundleManifest
from frances.paths import DataPaths

DEMO_PASSPHRASE = "demo demo demo demo demo demo"
DEMO_SALT = "ZGVtby1zYWx0LTE2Ynl0ZQ"
DEMO_ITERATIONS = 600000
DEMO_NOW = "2026-10-14T10:17:00.000000Z"
DEMO_MAX_TOTAL_BYTES = 900 * 1024 * 1024

FIXTURES: Path = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
DEMO_SQL: Path = FIXTURES / "demo_state.sql"
DEMO_AUDIO: Path = FIXTURES / "demo_audio"
#: Variante de espeak-ng por voz, para que Denise y Henri no suenen idénticas.
_ESPEAK_VOICE: dict[str, str] = {"fr-FR-DeniseNeural": "fr+f3", "fr-FR-HenriNeural": "fr+m3"}


def _blob_sources() -> dict[str, Path]:
    """Marcador → archivo: dos primeros PDF y primera imagen (orden alfabético)."""
    pdfs = sorted((FIXTURES / "pdf").glob("*.pdf"), key=lambda p: p.name)
    images = sorted(
        (p for p in (FIXTURES / "images").iterdir() if p.is_file()), key=lambda p: p.name
    )
    return {"pdf1": pdfs[0], "pdf2": pdfs[1], "img1": images[0]}


def _demo_sql(blobs: dict[str, Path]) -> str:
    """SQL del demo con ``{{marcador}}`` y ``{{marcador_size}}`` sustituidos."""
    text = DEMO_SQL.read_text(encoding="utf-8")
    for name, path in blobs.items():
        data = path.read_bytes()
        text = text.replace("{{" + name + "_size}}", str(len(data)))
        text = text.replace("{{" + name + "}}", hashlib.sha256(data).hexdigest())
    return text


def _q_audio_done(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """``(cache_key, voice_id, text)`` de las filas de audio ``done``, por clave."""
    rows = conn.execute(
        "SELECT cache_key, voice_id, text FROM audio WHERE status = 'done' ORDER BY cache_key"
    ).fetchall()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]


def build_demo(out_dir: Path) -> BundleManifest:
    """Escribe el bundle de demo en ``out_dir`` (determinista)."""
    blobs = _blob_sources()
    with tempfile.TemporaryDirectory(prefix="frances-demo-") as tmp:
        paths = DataPaths(Path(tmp))
        paths.ensure_dirs()
        for path in blobs.values():
            dest = paths.blob_path(hashlib.sha256(path.read_bytes()).hexdigest())
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        for mp3 in sorted(DEMO_AUDIO.glob("*.mp3")):
            shutil.copyfile(mp3, paths.audio_path(mp3.stem))
        store = restore_sql(_demo_sql(blobs), paths.state_db)
        try:
            with store.tx() as conn:
                seed_drills(conn, DEMO_NOW)
            return write_bundle(
                store.conn,
                paths,
                load_voices(paths),
                out_dir,
                DEMO_PASSPHRASE,
                DEMO_SALT,
                DEMO_ITERATIONS,
                DEMO_MAX_TOTAL_BYTES,
                None,
                DEMO_NOW,
            )
        finally:
            store.close()


def make_demo_audio(dest: Path) -> list[Path]:
    """Genera un MP3 (24 kHz, mono, 48 kbps, -16 LUFS) por fila de audio ``done``."""
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="frances-demo-audio-") as tmp:
        tmp_dir = Path(tmp)
        store = restore_sql(_demo_sql(_blob_sources()), tmp_dir / "state.db")
        try:
            rows = _q_audio_done(store.conn)
        finally:
            store.close()
        wav = tmp_dir / "tmp.wav"
        for key, voice_id, text in rows:
            mp3 = dest / f"{key}.mp3"
            voice = _ESPEAK_VOICE.get(voice_id, "fr")
            subprocess.run(["espeak-ng", "-v", voice, "-w", str(wav), text], check=True)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(wav),
                    "-af",
                    "loudnorm=I=-16",
                    "-ac",
                    "1",
                    "-ar",
                    "24000",
                    "-b:a",
                    "48k",
                    "-map_metadata",
                    "-1",
                    "-fflags",
                    "+bitexact",
                    "-flags:a",
                    "+bitexact",
                    str(mp3),
                ],
                check=True,
            )
            out.append(mp3)
    return out


def main(argv: list[str] | None = None) -> int:
    """``python -m frances.bundle.demo --make-audio`` regenera ``demo_audio/``."""
    parser = argparse.ArgumentParser(description="Utilidades del bundle de demo")
    parser.add_argument(
        "--make-audio", action="store_true", help="Regenera tests/fixtures/demo_audio/"
    )
    args = parser.parse_args(argv)
    if not args.make_audio:
        parser.print_help()
        return 2
    for stale in sorted(DEMO_AUDIO.glob("*.mp3")):
        stale.unlink()
    files = make_demo_audio(DEMO_AUDIO)
    print(f"{len(files)} archivos en {DEMO_AUDIO}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
