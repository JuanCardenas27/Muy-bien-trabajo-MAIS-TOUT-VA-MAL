"""Tests de frances.bundle.run (Task BND-04)."""

import gzip
import json
import unicodedata
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from frances.bundle.frb1 import b64url_decode, b64url_encode, decrypt, derive_keys, derive_master
from frances.bundle.run import (
    MIN_PASSPHRASE_CHARS,
    register,
    run_bundle,
    validate_passphrase,
    validate_salt,
)
from frances.db.store import Store
from frances.errors import ConfigError
from frances.models.bundle import BundleManifest, ContentIndex, SpeechCredentials
from frances.paths import DataPaths
from frances.stage import StageContext, make_context

SALT = b64url_encode(bytes(range(16)))
ITERATIONS = 1000
PASS = "x" * 24
NOW = "2026-10-15T00:00:00.000000Z"

cli = typer.Typer()
register(cli)


def _make_data_dir(root: Path, salt: str = SALT) -> Path:
    """Repo de datos mínimo: frances.toml + DB con un curso y un ítem."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "frances.toml").write_text(
        f'[bundle]\nsalt = "{salt}"\niterations = {ITERATIONS}\nmax_total_mb = 50\n',
        encoding="utf-8",
    )
    paths = DataPaths(root)
    paths.ensure_dirs()
    store = Store.open(paths.state_db)
    with store.tx() as conn:
        conn.execute(
            "INSERT INTO courses VALUES (?,?,?,?,?,?,?,?)",
            ("c1", "Français test", None, "ACTIVE", None, NOW, 1, "{}"),
        )
        conn.execute(
            "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "mt_1",
                "c1",
                "material",
                "1",
                None,
                "Leçon test",
                "Bonjour à tous, voici la leçon.",
                "PUBLISHED",
                None,
                NOW,
                NOW,
                None,
                "h",
                "{}",
                NOW,
                NOW,
                None,
            ),
        )
    store.close()
    return root


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return _make_data_dir(tmp_path / "data")


@pytest.fixture
def data_dir_no_salt(tmp_path: Path) -> Path:
    return _make_data_dir(tmp_path / "data", salt="")


@pytest.fixture
def ctx(data_dir: Path) -> StageContext:
    return make_context(data_dir, env={})


@pytest.fixture
def ctx_with_speech_env(data_dir: Path) -> StageContext:
    return make_context(
        data_dir, env={"AZURE_SPEECH_KEY": "k-test", "AZURE_SPEECH_REGION": "eastus"}
    )


def _read_index(out: Path, passphrase: str = PASS) -> tuple[BundleManifest, ContentIndex]:
    manifest = BundleManifest.model_validate_json((out / "bundle.json").read_bytes())
    master = derive_master(passphrase, b64url_decode(manifest.kdf.salt), manifest.kdf.iterations)
    enc_key, _ = derive_keys(master)
    blob = (out / "d" / f"{manifest.index.id}.bin").read_bytes()
    raw = gzip.decompress(decrypt(blob, enc_key))
    return manifest, ContentIndex.model_validate(json.loads(raw))


def test_short_passphrase_exits_4(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRANCES_PASSPHRASE", "corta")
    res = CliRunner().invoke(
        cli, ["bundle", "--out", str(data_dir / "site"), "--data", str(data_dir)]
    )
    assert res.exit_code == 4
    assert not (data_dir / "site" / "bundle.json").exists()


def test_missing_passphrase_exits_4(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRANCES_PASSPHRASE", raising=False)
    res = CliRunner().invoke(
        cli, ["bundle", "--out", str(data_dir / "site"), "--data", str(data_dir)]
    )
    assert res.exit_code == 4


def test_empty_salt_exits_4(data_dir_no_salt: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRANCES_PASSPHRASE", PASS)
    res = CliRunner().invoke(
        cli,
        ["bundle", "--out", str(data_dir_no_salt / "site"), "--data", str(data_dir_no_salt)],
    )
    assert res.exit_code == 4
    assert not (data_dir_no_salt / "site" / "bundle.json").exists()


def test_cli_bundle_ok_and_passphrase_not_printed(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRANCES_PASSPHRASE", PASS)
    res = CliRunner().invoke(
        cli, ["bundle", "--out", str(data_dir / "site"), "--data", str(data_dir)]
    )
    assert res.exit_code == 0, res.output
    assert (data_dir / "site" / "bundle.json").exists()
    assert PASS not in res.output


def test_validate_passphrase_counts_after_nfc() -> None:
    nfd = unicodedata.normalize("NFD", "é" * 12) + "x" * 11
    assert len(nfd) >= MIN_PASSPHRASE_CHARS
    with pytest.raises(ConfigError, match="al menos 24 caracteres"):
        validate_passphrase(nfd)
    ok = unicodedata.normalize("NFD", "é" * 12) + "x" * 12
    assert validate_passphrase(ok) == unicodedata.normalize("NFC", ok)


@pytest.mark.parametrize("salt", ["", "!!!", b64url_encode(bytes(15)), b64url_encode(bytes(17))])
def test_validate_salt_rejects_bad_values(salt: str) -> None:
    with pytest.raises(ConfigError):
        validate_salt(salt)


def test_validate_salt_accepts_16_bytes() -> None:
    assert validate_salt(SALT) == bytes(range(16))


def test_manifest_kdf_matches_settings(ctx: StageContext, tmp_path: Path) -> None:
    out = tmp_path / "site"
    report = run_bundle(ctx, out, PASS)
    assert report.stage == "bundle" and report.status == "ok"
    m, idx = _read_index(out)
    assert m.kdf.iterations == ctx.settings.bundle.iterations
    assert m.kdf.salt == ctx.settings.bundle.salt
    assert m.format == "FRB1"
    assert idx.speech is None
    assert [i.id for i in idx.items] == ["mt_1"]
    assert report.counts["items"] == 1
    assert report.counts["cards"] == len(idx.cards)
    assert report.counts["files"] == len(list((out / "d").glob("*.bin")))
    # run_bundle siembra los taladros (R-13)
    assert any(d.curated for d in idx.drills)
    assert any(c.kind == "drill" for c in idx.cards)
    raw = (out / "bundle.json").read_bytes()
    assert b"\r\n" not in raw


def test_speech_from_env(ctx_with_speech_env: StageContext, tmp_path: Path) -> None:
    run_bundle(ctx_with_speech_env, tmp_path / "site", PASS)
    _, idx = _read_index(tmp_path / "site")
    assert idx.speech == SpeechCredentials(region="eastus", key="k-test")


def test_rerun_removes_unreferenced_bins(ctx: StageContext, tmp_path: Path) -> None:
    out = tmp_path / "site"
    (out / "d").mkdir(parents=True)
    stale = out / "d" / ("0" * 32 + ".bin")
    stale.write_bytes(b"viejo")
    run_bundle(ctx, out, PASS)
    assert not stale.exists()
    m, _ = _read_index(out)
    assert (out / "d" / f"{m.index.id}.bin").exists()


def test_index_gzip_is_platform_independent(ctx: StageContext, tmp_path: Path) -> None:
    out = tmp_path / "site"
    run_bundle(ctx, out, PASS)
    m = BundleManifest.model_validate_json((out / "bundle.json").read_bytes())
    master = derive_master(PASS, b64url_decode(m.kdf.salt), m.kdf.iterations)
    enc_key, _ = derive_keys(master)
    gz = decrypt((out / "d" / f"{m.index.id}.bin").read_bytes(), enc_key)
    assert gz[4:8] == b"\x00\x00\x00\x00"  # mtime 0
    assert gz[9] == 0xFF  # SO desconocido: igual en Windows y Linux
