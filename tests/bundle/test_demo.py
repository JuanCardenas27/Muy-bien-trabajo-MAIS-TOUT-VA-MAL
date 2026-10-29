"""Tests de frances.bundle.demo (Task BND-04)."""

import gzip
import json
from pathlib import Path

import pytest

from frances.bundle.demo import (
    DEMO_ITERATIONS,
    DEMO_NOW,
    DEMO_PASSPHRASE,
    DEMO_SALT,
    build_demo,
    make_demo_audio,
)
from frances.bundle.frb1 import CHECK_PLAINTEXT, b64url_decode, decrypt, derive_keys, derive_master
from frances.models.bundle import BundleManifest, ContentIndex

NASAL_A = "ɑ̃"  # noqa: RUF001 - a nasal (mazo curado drill-an)
DEMO_COURSE = "Français A2 – Démo"  # noqa: RUF001 - nombre del curso demo


def _key(passphrase: str) -> bytes:
    return derive_keys(derive_master(passphrase, b64url_decode(DEMO_SALT), DEMO_ITERATIONS))[0]


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, BundleManifest]:
    out = tmp_path_factory.mktemp("demo") / "site"
    return out, build_demo(out)


def test_demo_bundle_manifest_and_index_validate(demo: tuple[Path, BundleManifest]) -> None:
    out, m = demo
    on_disk = BundleManifest.model_validate_json((out / "bundle.json").read_bytes())
    assert on_disk == m
    assert m.kdf.salt == DEMO_SALT and m.kdf.iterations == DEMO_ITERATIONS
    assert m.created_at == DEMO_NOW
    key = _key(DEMO_PASSPHRASE)
    assert decrypt(b64url_decode(m.check), key) == CHECK_PLAINTEXT
    raw = gzip.decompress(decrypt((out / "d" / f"{m.index.id}.bin").read_bytes(), key))
    idx = ContentIndex.model_validate(json.loads(raw))
    assert idx.speech is None and [c.name for c in idx.courses] == [DEMO_COURSE]
    assert len(idx.items) == 6 and len(idx.topics) == 3 and len(idx.sheets) == 2
    assert sum(1 for c in idx.cards if c.kind == "drill") >= 10
    assert sum(1 for c in idx.cards if len(c.audio) == 2) == 10
    assert any(a.status == "forbidden" and a.file is None for a in idx.attachments)
    assert any(d.phoneme == NASAL_A for d in idx.drills) and any(
        c.front_fr == "Bonjour" for c in idx.cards
    )
    titles = {i.title for i in idx.items}
    assert {"Leçon 1 — Les salutations", "Leçon 2 — Les nasales"} <= titles
    bonjour = next(c for c in idx.cards if c.front_fr == "Bonjour")
    assert {a.voice_id for a in bonjour.audio} == {"fr-FR-DeniseNeural", "fr-FR-HenriNeural"}
    assert [p.voice_id for p in bonjour.audio_pending] == ["fr-FR-EloiseNeural"]
    lecon1 = next(i for i in idx.items if i.title == "Leçon 1 — Les salutations")
    pdfs = [a for a in idx.attachments if a.item_id == lecon1.id and a.file is not None]
    assert pdfs and pdfs[0].file is not None and pdfs[0].file.mime == "application/pdf"
    # todos los FileRef publicados existen en d/
    for att in idx.attachments:
        if att.file is not None:
            assert (out / "d" / f"{att.file.id}.bin").exists()


def test_demo_check_rejects_wrong_passphrase(demo: tuple[Path, BundleManifest]) -> None:
    _, m = demo
    with pytest.raises(ValueError):
        decrypt(b64url_decode(m.check), _key("una passphrase equivocada ok"))


def test_demo_is_deterministic(tmp_path: Path, demo: tuple[Path, BundleManifest]) -> None:
    out, m = demo
    again = tmp_path / "b"
    assert build_demo(again) == m
    assert (again / "bundle.json").read_bytes() == (out / "bundle.json").read_bytes()
    assert sorted(p.name for p in (again / "d").iterdir()) == sorted(
        p.name for p in (out / "d").iterdir()
    )


def _mp3_frame_header(data: bytes) -> bytes:
    """Primer encabezado de frame MPEG tras un posible tag ID3v2."""
    pos = 0
    if data[:3] == b"ID3":
        size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        pos = 10 + size
    while pos < len(data) - 4:
        if data[pos] == 0xFF and data[pos + 1] & 0xE0 == 0xE0:
            return data[pos : pos + 4]
        pos += 1
    raise AssertionError("sin frame MPEG")


@pytest.mark.heavy
def test_make_demo_audio_writes_mp3_24k_mono(tmp_path: Path) -> None:
    files = make_demo_audio(tmp_path)
    assert len(files) == 20 and all(f.suffix == ".mp3" for f in files)
    for f in files:
        h = _mp3_frame_header(f.read_bytes())
        assert (h[1] >> 3) & 0b11 == 0b10  # MPEG-2 (16/22.05/24 kHz)
        assert (h[2] >> 2) & 0b11 == 0b01  # 24000 Hz en MPEG-2
        assert (h[3] >> 6) & 0b11 == 0b11  # mono
