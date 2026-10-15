"""Almacén content-addressed de blobs (solo filesystem)."""

import hashlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, cast

from frances.errors import FrancesError
from frances.paths import DataPaths


class BlobTooLargeError(FrancesError):
    """El contenido supera ``max_bytes``: salida 1."""


class _HashingWriter:
    """Envoltorio que hashea y cuenta cada ``write`` con tope de tamaño."""

    def __init__(self, raw: BinaryIO, max_bytes: int) -> None:
        self._raw = raw
        self._max_bytes = max_bytes
        self.hasher = hashlib.sha256()
        self.count = 0

    def write(self, data: bytes | bytearray | memoryview) -> int:
        size = len(data)
        if self.count + size > self._max_bytes:
            raise BlobTooLargeError(f"blob supera el tope de {self._max_bytes} bytes")
        self.hasher.update(data)
        self._raw.write(data)
        self.count += size
        return size

    def __getattr__(self, name: str) -> object:
        return getattr(self._raw, name)


class BlobStore:
    """Guarda bytes por su sha256 bajo ``blobs/<sha[:2]>/<sha>``."""

    def __init__(self, paths: DataPaths) -> None:
        self._paths = paths

    def put_stream(self, write_fn: Callable[[BinaryIO], int], max_bytes: int) -> tuple[str, int]:
        """Ejecuta ``write_fn`` sobre un temporal en ``cache`` y lo publica.

        El temporal se borra ante cualquier excepción (tope superado o fallo
        de ``write_fn``); si el destino ya existe se reutiliza sin duplicar.
        """
        self._paths.cache.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self._paths.cache, prefix=".tmp-")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as raw:
                writer = _HashingWriter(cast(BinaryIO, raw), max_bytes)
                write_fn(cast(BinaryIO, writer))
                sha = writer.hasher.hexdigest()
                size = writer.count
            dest = self._paths.blob_path(sha)
            if dest.exists():
                tmp_path.unlink(missing_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(tmp_path, dest)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return (sha, size)

    def put_bytes(self, data: bytes) -> tuple[str, int]:
        """Guarda ``data`` en el almacén; devuelve ``(sha256, len)``."""

        def write_fn(f: BinaryIO) -> int:
            return f.write(data)

        return self.put_stream(write_fn, max_bytes=len(data))

    def exists(self, sha: str) -> bool:
        return self._paths.blob_path(sha).is_file()

    def path(self, sha: str) -> Path:
        return self._paths.blob_path(sha)
