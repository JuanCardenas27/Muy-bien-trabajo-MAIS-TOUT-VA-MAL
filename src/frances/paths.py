"""Rutas del repo de datos (réplica local del bucket R2 ``frances-data``)."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataPaths:
    """Todas las rutas cuelgan de ``root`` (--data DIR)."""

    root: Path

    @property
    def config(self) -> Path:
        return self.root / "frances.toml"

    @property
    def voices_yaml(self) -> Path:
        return self.root / "voices.yaml"

    @property
    def voice_refs(self) -> Path:
        return self.root / "voices" / "refs"

    @property
    def state_sql(self) -> Path:
        return self.root / "state" / "state.sql"

    @property
    def state_db(self) -> Path:
        return self.root / ".cache" / "state.db"

    @property
    def cache(self) -> Path:
        return self.root / ".cache"

    def blob_path(self, sha: str) -> Path:
        return self.root / "blobs" / sha[:2] / sha

    def extraction_path(self, sha: str, ver: str) -> Path:
        return self.root / "extractions" / f"{sha}.{ver}.json"

    def audio_path(self, key: str) -> Path:
        return self.root / "audio" / f"{key}.mp3"

    def ensure_dirs(self) -> None:
        """Crea los directorios del layout que son carpetas (idempotente)."""
        for directory in (
            self.cache,
            self.voice_refs,
            self.state_sql.parent,
            self.root / "blobs",
            self.root / "extractions",
            self.root / "audio",
        ):
            directory.mkdir(parents=True, exist_ok=True)
