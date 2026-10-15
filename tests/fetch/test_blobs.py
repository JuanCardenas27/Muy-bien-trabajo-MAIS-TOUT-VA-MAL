import hashlib
from pathlib import Path
from typing import BinaryIO

import pytest

from frances.fetch.blobs import BlobStore, BlobTooLargeError
from frances.paths import DataPaths


def test_same_content_same_sha_single_file(tmp_path: Path) -> None:
    bs = BlobStore(DataPaths(tmp_path))
    a = bs.put_stream(lambda f: f.write(b"bonjour"), max_bytes=100)
    b = bs.put_bytes(b"bonjour")
    assert a == b == (hashlib.sha256(b"bonjour").hexdigest(), 7)
    assert bs.path(a[0]) == DataPaths(tmp_path).blob_path(a[0]) and bs.exists(a[0])
    assert len([p for p in (tmp_path / "blobs").rglob("*") if p.is_file()]) == 1
    assert list(DataPaths(tmp_path).cache.glob("*")) == []


def test_too_large_leaves_no_temp(tmp_path: Path) -> None:
    bs = BlobStore(DataPaths(tmp_path))
    with pytest.raises(BlobTooLargeError):
        bs.put_stream(lambda f: f.write(b"x" * 11), max_bytes=10)
    assert list(DataPaths(tmp_path).cache.glob("*")) == [] and not (tmp_path / "blobs").exists()


def test_write_fn_exception_leaves_no_temp(tmp_path: Path) -> None:
    bs = BlobStore(DataPaths(tmp_path))

    def write_fn(f: BinaryIO) -> int:
        f.write(b"partial")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        bs.put_stream(write_fn, max_bytes=100)
    assert list(DataPaths(tmp_path).cache.glob("*")) == []
