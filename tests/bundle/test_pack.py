"""Tests for frances.bundle.pack (Task BND-03)."""

import hashlib
import os
from pathlib import Path

import pytest

from frances.bundle.frb1 import decrypt
from frances.bundle.pack import BudgetExceeded, Packer

ENC = bytes(32)
NON = bytes([1]) * 32


def test_same_file_twice_writes_one_bin(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 demo")
    p = Packer(tmp_path / "out", ENC, NON, 10_000)
    r1 = p.add_file(src, "application/pdf")
    r2 = p.add_bytes(b"%PDF-1.4 demo", "application/pdf")
    assert r1 == r2
    assert len(list((tmp_path / "out" / "d").glob("*.bin"))) == 1


def test_fileref_has_plaintext_sha_and_size(tmp_path: Path) -> None:
    ref = Packer(tmp_path, ENC, NON, 10_000).add_bytes(b"hola", "text/plain")
    assert ref.sha256 == hashlib.sha256(b"hola").hexdigest()
    assert ref.size == 4
    assert len(ref.id) == 32
    assert ref.mime == "text/plain"


def test_bin_decrypts_to_plaintext(tmp_path: Path) -> None:
    ref = Packer(tmp_path, ENC, NON, 10_000).add_bytes(b"hola", "text/plain")
    assert decrypt((tmp_path / "d" / f"{ref.id}.bin").read_bytes(), ENC) == b"hola"


def test_total_bytes_counts_encrypted_once(tmp_path: Path) -> None:
    p = Packer(tmp_path, ENC, NON, 10_000)
    p.add_bytes(b"x" * 10, "text/plain")
    p.add_bytes(b"x" * 10, "text/plain")
    assert p.total_bytes == 4 + 12 + 10 + 16


def test_budget_exceeded(tmp_path: Path) -> None:
    p = Packer(tmp_path, ENC, NON, 50)
    with pytest.raises(BudgetExceeded) as exc:
        p.add_bytes(b"y" * 100, "text/plain")
    assert exc.value.total == 132
    assert exc.value.max == 50


def test_existing_bin_not_rewritten(tmp_path: Path) -> None:
    ref = Packer(tmp_path, ENC, NON, 10_000).add_bytes(b"z", "text/plain")
    path = tmp_path / "d" / f"{ref.id}.bin"
    os.utime(path, (1, 1))
    Packer(tmp_path, ENC, NON, 10_000).add_bytes(b"z", "text/plain")
    assert path.stat().st_mtime == 1
