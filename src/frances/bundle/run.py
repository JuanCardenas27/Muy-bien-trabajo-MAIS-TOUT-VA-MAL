"""Etapa ``bundle``: política de passphrase y escritura del bundle FRB1 (Task BND-04).

Salida en disco: ``out_dir/bundle.json`` (``BundleManifest``) y ``out_dir/d/*.bin``.
Nunca se loguea ni se imprime la passphrase ni ninguna clave derivada.
"""

import binascii
import gzip
import sqlite3
import unicodedata
from pathlib import Path
from typing import Annotated

import typer

from frances.audio.voices import load_voices
from frances.bundle.frb1 import b64url_decode, derive_keys, derive_master, make_check
from frances.bundle.index import build_index
from frances.bundle.pack import Packer
from frances.cards.drills import build_drill_decks, seed_drills
from frances.cli import DataOpt, exit_with
from frances.db.usage import record_run
from frances.errors import ConfigError
from frances.models.audio import Voice
from frances.models.bundle import (
    BundleManifest,
    ContentIndex,
    FileRef,
    KdfParams,
    SpeechCredentials,
)
from frances.paths import DataPaths
from frances.stage import StageContext, StageReport, make_context
from frances.timeutil import format_ts

MIN_PASSPHRASE_CHARS = 24
SALT_BYTES = 16
_INDEX_MIME = "application/gzip"
OutOpt = Annotated[Path, typer.Option("--out", help="Carpeta de salida del sitio")]
_GZIP_OS_UNKNOWN = b"\xff"


def validate_passphrase(passphrase: str) -> str:
    """Devuelve la passphrase en NFC; menos de 24 caracteres tras NFC → ``ConfigError``."""
    normalized = unicodedata.normalize("NFC", passphrase)
    if len(normalized) < MIN_PASSPHRASE_CHARS:
        raise ConfigError(f"La passphrase debe tener al menos {MIN_PASSPHRASE_CHARS} caracteres")
    return normalized


def validate_salt(salt_b64: str) -> bytes:
    """Decodifica ``[bundle] salt`` (base64url); vacío o ≠ 16 bytes → ``ConfigError``."""
    if not salt_b64.strip():
        raise ConfigError("Falta [bundle] salt en frances.toml (16 bytes en base64url)")
    try:
        salt = b64url_decode(salt_b64.strip())
    except (binascii.Error, ValueError) as exc:
        raise ConfigError("[bundle] salt no es base64url válido") from exc
    if len(salt) != SALT_BYTES:
        raise ConfigError(f"[bundle] salt debe decodificar a {SALT_BYTES} bytes, no {len(salt)}")
    return salt


def _gzip_index(index: ContentIndex) -> bytes:
    """JSON del índice en gzip reproducible: ``mtime=0`` y byte de SO fijo (255)."""
    gz = gzip.compress(index.model_dump_json().encode("utf-8"), mtime=0)
    # El byte 9 (SO) depende de la plataforma con zlib (Windows 10, Linux 3).
    return gz[:9] + _GZIP_OS_UNKNOWN + gz[10:]


def _referenced_ids(index: ContentIndex, index_ref: FileRef) -> set[str]:
    """Ids de todos los ``FileRef`` del índice más el del propio índice."""
    ids = {index_ref.id}
    for att in index.attachments:
        for ref in (att.file, att.view_pdf):
            if ref is not None:
                ids.add(ref.id)
    for card in index.cards:
        ids.update(audio.file.id for audio in card.audio)
    return ids


def _remove_unreferenced(out_dir: Path, keep: set[str]) -> None:
    """Borra de ``out_dir/d/`` cada ``.bin`` que el índice ya no referencia."""
    d_dir = out_dir / "d"
    if not d_dir.is_dir():
        return
    for path in sorted(d_dir.glob("*.bin")):
        if path.stem not in keep:
            path.unlink()


def write_bundle(
    conn: sqlite3.Connection,
    paths: DataPaths,
    voices: list[Voice],
    out_dir: Path,
    passphrase: str,
    salt_b64: str,
    iterations: int,
    max_total_bytes: int,
    speech: SpeechCredentials | None,
    now: str,
) -> BundleManifest:
    """Empaqueta índice y archivos en ``out_dir`` y escribe ``bundle.json``.

    Los mazos de taladro se construyen aquí con ``build_drill_decks(conn)``; quien
    llama ya sembró los taladros (``seed_drills``) en su transacción.
    """
    salt = validate_salt(salt_b64)
    enc_key, nonce_key = derive_keys(derive_master(passphrase, salt, iterations))
    packer = Packer(out_dir, enc_key, nonce_key, max_total_bytes)
    index = build_index(conn, paths, packer, voices, build_drill_decks(conn), speech, now)
    pack_ref = packer.add_bytes(_gzip_index(index), _INDEX_MIME)
    index_ref = FileRef(
        id=pack_ref.id, size=pack_ref.size, mime=pack_ref.mime, sha256=pack_ref.sha256
    )
    manifest = BundleManifest(
        format="FRB1",
        kdf=KdfParams(name="PBKDF2", hash="SHA-256", iterations=iterations, salt=salt_b64),
        check=make_check(enc_key, nonce_key),
        index=index_ref,
        created_at=now,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "bundle.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_bytes((manifest.model_dump_json(indent=2) + "\n").encode("utf-8"))
    tmp.replace(target)
    _remove_unreferenced(out_dir, _referenced_ids(index, index_ref))
    return manifest


def _speech(ctx: StageContext) -> SpeechCredentials | None:
    """Credenciales de Azure Speech solo si ambas variables están en el entorno."""
    key = ctx.settings.optional_secret("AZURE_SPEECH_KEY")
    region = ctx.settings.optional_secret("AZURE_SPEECH_REGION")
    if not key or not region:
        return None
    return SpeechCredentials(region=region, key=key)


def run_bundle(ctx: StageContext, out_dir: Path, passphrase: str) -> StageReport:
    """Etapa ``bundle``: valida antes de tocar disco, siembra taladros y escribe."""
    normalized = validate_passphrase(passphrase)
    validate_salt(ctx.settings.bundle.salt)
    now = format_ts(ctx.now())
    with ctx.store.tx() as conn:
        seed_drills(conn, now)
    voices = load_voices(ctx.paths)
    write_bundle(
        ctx.store.conn,
        ctx.paths,
        voices,
        out_dir,
        normalized,
        ctx.settings.bundle.salt,
        ctx.settings.bundle.iterations,
        ctx.settings.bundle.max_total_mb * 1024 * 1024,
        _speech(ctx),
        now,
    )
    files = sorted((out_dir / "d").glob("*.bin"))
    items, cards = _q_counts(ctx.store.conn)
    report = StageReport(
        stage="bundle",
        status="ok",
        counts={
            "files": len(files),
            "bytes": sum(path.stat().st_size for path in files),
            "items": items,
            "cards": cards,
        },
    )
    with ctx.store.tx() as conn:
        record_run(conn, report, now, format_ts(ctx.now()))
    return report


def _q_counts(conn: sqlite3.Connection) -> tuple[int, int]:
    """Ítems vivos de cursos incluidos y tarjetas (mismo criterio que el índice)."""
    items = conn.execute(
        "SELECT COUNT(*) FROM items WHERE deleted_at IS NULL"
        " AND course_id IN (SELECT id FROM courses WHERE included = 1)"
    ).fetchone()[0]
    cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    return int(items), int(cards)


def register(app: typer.Typer) -> None:
    """Registra ``bundle`` y ``demo-bundle`` (R-05)."""

    @app.command("bundle")
    def bundle(
        out: OutOpt,
        data: DataOpt = Path("."),
    ) -> None:
        """Empaqueta el estado en un bundle FRB1 cifrado (passphrase en FRANCES_PASSPHRASE)."""

        def _run() -> StageReport:
            ctx = make_context(data)
            passphrase = ctx.settings.optional_secret("FRANCES_PASSPHRASE") or ""
            return run_bundle(ctx, out, passphrase)

        exit_with(_run)

    @app.command("demo-bundle")
    def demo_bundle(
        out: OutOpt,
        data: DataOpt = Path("."),
    ) -> None:
        """Escribe el bundle de demostración sintético (no lee --data)."""
        _ = data

        def _demo() -> None:
            from frances.bundle.demo import build_demo  # import diferido: demo importa este módulo

            build_demo(out)

        exit_with(_demo)
