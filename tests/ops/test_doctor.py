"""Tests de `frances doctor` (OPS-07): tamaños, cuotas, pendientes, voces y token."""

import os
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from frances.config import Settings, load_settings
from frances.db.store import Store
from frances.db.usage import usage_add
from frances.ops import doctor
from frances.ops.doctor import (
    collect_sizes,
    estimate_bundle_bytes,
    pending_counts,
    run_doctor,
    usage_lines,
)
from frances.paths import DataPaths
from frances.stage import StageContext, make_context

_NOW = "2026-10-01T10:00:00Z"
_BLOB_A = "aa" * 32  # 100 B, lo comparten dos adjuntos
_BLOB_B = "bb" * 32  # 50 B, export_pdf
_AUDIO_KEY = "cc" * 16
_SIZE_SHAS = [f"{i:064x}" for i in range(12)]

app = typer.Typer()
doctor.register(app)


@app.command()
def ping() -> None:
    """Segundo comando para que typer use modo grupo (igual que tests/audio/test_run.py)."""
    typer.echo("pong")


class FakeBin:
    """El `frances` falso de `fake_bin`: anota su argv y sale 3."""

    def __init__(self, record: Path) -> None:
        self._record = record

    def argv(self) -> list[str]:
        return json.loads(self._record.read_text(encoding="utf-8"))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Árbol `DataPaths` sintético: `frances.toml` mínimo con salt de prueba,
    12 blobs de 1000..12000 bytes, 1 mp3 de 500 B y `site/` de 1,5 GB (sparse)."""
    paths = DataPaths(tmp_path)
    paths.ensure_dirs()
    (tmp_path / "frances.toml").write_text(
        '[bundle]\nsalt = "c2FsdC1kZS1wcnVlYmE="\n', encoding="utf-8"
    )
    for sha, size in zip(_SIZE_SHAS, range(1000, 13000, 1000), strict=True):
        blob = paths.blob_path(sha)
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(b"x" * size)
    paths.audio_path(_AUDIO_KEY).write_bytes(b"m" * 500)
    (tmp_path / "site").mkdir()
    with (tmp_path / "site" / "index.html").open("wb") as fh:
        fh.truncate(1_500_000_000)
    return tmp_path


@pytest.fixture
def store(data_dir: Path) -> Iterator[Store]:
    s = Store.open(DataPaths(data_dir).state_db)
    yield s
    s.close()


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return load_settings(DataPaths(data_dir).config, {})


@pytest.fixture
def store_with_rows(store: Store, data_dir: Path) -> Store:
    """2 adjuntos downloaded con el mismo blob (100 B), 1 export_pdf (50 B),
    1 adjunto `forbidden` con `removed_at` (no cuenta) y audio: 2 pending + 1 done (10 B)."""
    conn = store.conn
    conn.execute(
        "INSERT INTO courses (id, name, state, update_time, raw_json)"
        " VALUES ('c1', 'Français 1', 'ACTIVE', ?, '{}')",
        (_NOW,),
    )
    for item_id in ("it_1", "it_2", "it_3"):
        conn.execute(
            "INSERT INTO items (id, course_id, kind, classroom_id, text, state, creation_time,"
            " update_time, content_hash, raw_json, first_seen_at, last_seen_at)"
            " VALUES (?, 'c1', 'material', ?, '', 'PUBLISHED', ?, ?, ?, '{}', ?, ?)",
            (item_id, item_id, _NOW, _NOW, item_id, _NOW, _NOW),
        )
    conn.execute(
        "INSERT INTO blobs (sha256, size, mime_type, created_at) VALUES (?, 100, 'application/pdf', ?)",
        (_BLOB_A, _NOW),
    )
    conn.execute(
        "INSERT INTO blobs (sha256, size, mime_type, created_at) VALUES (?, 50, 'application/pdf', ?)",
        (_BLOB_B, _NOW),
    )
    for n in ("a1", "a2"):
        conn.execute(
            "INSERT INTO attachments (id, item_id, kind, external_id, blob_sha256, status,"
            " updated_at) VALUES (?, 'it_1', 'drive_file', ?, ?, 'downloaded', ?)",
            (n, f"ext-{n}", _BLOB_A, _NOW),
        )
    conn.execute(
        "INSERT INTO attachments (id, item_id, kind, external_id, export_pdf_sha256, status,"
        " updated_at) VALUES ('a3', 'it_2', 'drive_file', 'ext-a3', ?, 'downloaded', ?)",
        (_BLOB_B, _NOW),
    )
    conn.execute(
        "INSERT INTO attachments (id, item_id, kind, external_id, status, updated_at, removed_at)"
        " VALUES ('a4', 'it_3', 'drive_file', 'ext-a4', 'forbidden', ?, ?)",
        (_NOW, _NOW),
    )
    for key in ("k1", "k2"):
        conn.execute(
            "INSERT INTO audio (cache_key, text, text_norm, voice_id, family, family_version,"
            " status, attempts, updated_at)"
            " VALUES (?, 'Bonjour', 'bonjour', 'fr-FR-DeniseNeural', 'ms-neural', '1',"
            " 'pending', 0, ?)",
            (key, _NOW),
        )
    data_dir.joinpath("audio", f"k3.mp3").write_bytes(b"a" * 10)
    conn.execute(
        "INSERT INTO audio (cache_key, text, text_norm, voice_id, family, family_version, status,"
        " engine_used, path, duration_ms, attempts, updated_at)"
        " VALUES ('k3', 'Bonjour', 'bonjour', 'fr-FR-DeniseNeural', 'ms-neural', '1', 'done',"
        " 'edge', 'audio/k3.mp3', 900, 0, ?)",
        (_NOW,),
    )
    return store


@pytest.fixture
def ctx(data_dir: Path) -> Iterator[StageContext]:
    context = make_context(data_dir, {})
    yield context
    context.store.close()


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def fake_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeBin:
    """Script `frances` falso antepuesto a `PATH`: anota argv y sale 3."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = bin_dir / "argv.json"
    script = bin_dir / "frances"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"Path({str(record)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return FakeBin(record)


def test_sizes_by_dir_and_top10(data_dir: Path) -> None:
    rep = collect_sizes(DataPaths(data_dir))
    assert rep.by_dir["blobs"] == sum(range(1000, 13000, 1000))
    assert rep.by_dir["audio"] == 500
    assert len(rep.largest_blobs) == 10
    assert rep.largest_blobs[0][1] == 12000


def test_bundle_estimate_counts_unique_files_and_overhead(
    store_with_rows: Store, data_dir: Path
) -> None:
    assert estimate_bundle_bytes(store_with_rows.conn, DataPaths(data_dir)) == 100 + 50 + 10 + 3 * 32


def test_usage_lines_against_caps(store: Store, settings: Settings) -> None:
    usage_add(store.conn, "2026-10", "azure_tts_chars", 400_000)
    tts = next(
        u for u in usage_lines(store.conn, settings, "2026-10") if u.meter == "azure_tts_chars"
    )
    assert (tts.used, tts.cap, tts.warn) == (400_000, 450_000, True)
    tr = next(
        u
        for u in usage_lines(store.conn, settings, "2026-10")
        if u.meter == "azure_translator_chars"
    )
    assert (tr.used, tr.cap, tr.warn) == (0, 1_800_000, False)


def test_pending_counts(store_with_rows: Store) -> None:
    p = pending_counts(store_with_rows.conn)
    assert p["attachments"]["forbidden"] == 1
    assert p["audio"]["ms-neural/pending"] == 2


def test_invalid_voices_exits_4(data_dir: Path, cli_runner: CliRunner) -> None:
    (data_dir / "voices.yaml").write_text("voices: [{id: x}]", encoding="utf-8")
    assert cli_runner.invoke(app, ["doctor", "--data", str(data_dir)]).exit_code == 4


def test_repo_over_limit_warns_but_exits_0(
    data_dir: Path,
    ctx: StageContext,
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "REPO_WARN_BYTES", 1)
    assert any("1,5 GB" in w for w in run_doctor(ctx, online=False).warnings)
    assert cli_runner.invoke(app, ["doctor", "--data", str(data_dir)]).exit_code == 0


def test_online_runs_auth_check_subprocess(
    data_dir: Path, fake_bin: FakeBin, cli_runner: CliRunner
) -> None:
    r = cli_runner.invoke(app, ["doctor", "--online", "--data", str(data_dir)])
    assert r.exit_code == 0
    assert "auth: FALLA (exit 3)" in r.output
    assert fake_bin.argv() == ["auth", "check"]
