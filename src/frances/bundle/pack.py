"""Empaquetador d/*.bin con dedupe y presupuesto de tamano (Task BND-03)."""

import hashlib
from pathlib import Path

from frances.bundle.frb1 import encrypt, file_id
from frances.errors import FrancesError

try:  # FND-02 define el contrato canonico; fallback provisional hasta su merge.
    from frances.models.bundle import FileRef
except ModuleNotFoundError:  # pragma: no cover
    from pydantic import BaseModel, ConfigDict

    class FileRef(BaseModel):
        """Referencia a un blob publicado (provisional; canonica en FND-02)."""

        model_config = ConfigDict(extra="forbid", frozen=True)

        id: str
        size: int
        mime: str
        sha256: str


_MB = 1024 * 1024


class BudgetExceeded(FrancesError):
    """El bundle supera el presupuesto de tamano: salida 1."""

    exit_code: int = 1

    def __init__(self, total: int, max: int) -> None:
        self.total = total
        self.max = max
        super().__init__(
            f"El bundle supera el presupuesto: {total / _MB:.1f} MB > {max / _MB:.1f} MB"
        )


class Packer:
    """Cifra blobs con FRB1 en ``out_dir/d/<id>.bin`` con dedupe por sha256."""

    def __init__(
        self, out_dir: Path, enc_key: bytes, nonce_key: bytes, max_total_bytes: int
    ) -> None:
        self._out_dir = out_dir
        self._enc_key = enc_key
        self._nonce_key = nonce_key
        self._max_total_bytes = max_total_bytes
        self._by_sha: dict[str, FileRef] = {}
        self._total_bytes = 0

    @property
    def total_bytes(self) -> int:
        """Suma de bytes cifrados unicos agregados (cada contenido cuenta una vez)."""
        return self._total_bytes

    def add_file(self, path: Path, mime: str) -> FileRef:
        """Lee el archivo completo y lo agrega como blob."""
        return self.add_bytes(path.read_bytes(), mime)

    def add_bytes(self, data: bytes, mime: str) -> FileRef:
        """Agrega bytes; el contenido repetido devuelve el mismo FileRef sin reescribir."""
        sha = hashlib.sha256(data).hexdigest()
        cached = self._by_sha.get(sha)
        if cached is not None:
            return cached
        blob = encrypt(data, self._enc_key, self._nonce_key)
        total = self._total_bytes + len(blob)
        if total > self._max_total_bytes:
            raise BudgetExceeded(total, self._max_total_bytes)
        ref = FileRef(id=file_id(blob), size=len(data), mime=mime, sha256=sha)
        dest = self._out_dir / "d" / f"{ref.id}.bin"
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")
            tmp.write_bytes(blob)
            tmp.replace(dest)
        self._by_sha[sha] = ref
        self._total_bytes = total
        return ref
