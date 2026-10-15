"""Cliente de Drive: metadatos, descarga y exportación de archivos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Literal

import httpx

from frances.errors import FrancesError
from frances.sync.google_http import ForbiddenError, GoogleApi

DRIVE_BASE_URL = "https://www.googleapis.com/drive/v3"
NATIVE_PREFIX = "application/vnd.google-apps."

_METADATA_FIELDS = "id,name,mimeType,size,version,md5Checksum,capabilities/canDownload,exportLinks"

GOOGLE_NATIVE_EXPORTS: dict[str, list[tuple[str, Literal["view", "text"]]]] = {
    f"{NATIVE_PREFIX}document": [("application/pdf", "view"), ("text/plain", "text")],
    f"{NATIVE_PREFIX}presentation": [("application/pdf", "view"), ("text/plain", "text")],
    f"{NATIVE_PREFIX}spreadsheet": [("application/pdf", "view"), ("text/csv", "text")],
    f"{NATIVE_PREFIX}drawing": [("image/png", "view")],
}


@dataclass(frozen=True)
class DriveMeta:
    """Metadatos mínimos de un archivo de Drive para decidir su descarga."""

    id: str
    name: str
    mime_type: str
    size: int | None
    version: str
    md5: str | None
    can_download: bool
    export_links: dict[str, str]


class TooLargeError(FrancesError):
    """La descarga supera el tope permitido y se omite con enlace."""


class ExportTooLargeError(FrancesError):
    """Drive rechazó la exportación por tamaño (`exportSizeLimitExceeded`)."""


def _copy_limited(response: httpx.Response, dest: BinaryIO, max_bytes: int) -> int:
    """Copia `iter_bytes()` a `dest`; lanza `TooLargeError` al superar `max_bytes`."""
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise TooLargeError(f"descarga supera el tope de {max_bytes} bytes")
        dest.write(chunk)
    return total


class DriveClient:
    """Metadatos, descarga (`alt=media`) y exportación de archivos de Drive."""

    def __init__(self, api: GoogleApi) -> None:
        self._api = api

    def get_metadata(self, file_id: str) -> DriveMeta:
        """Lee `files/{id}` y lo normaliza a `DriveMeta`."""
        raw = self._api.get_json(
            f"files/{file_id}",
            {"fields": _METADATA_FIELDS, "supportsAllDrives": "true"},
        )
        size = raw.get("size")
        capabilities = raw.get("capabilities") or {}
        exports = raw.get("exportLinks") or {}
        return DriveMeta(
            id=str(raw["id"]),
            name=str(raw["name"]),
            mime_type=str(raw["mimeType"]),
            size=int(size) if size is not None else None,
            version=str(raw["version"]),
            md5=str(raw["md5Checksum"]) if raw.get("md5Checksum") is not None else None,
            can_download=bool(capabilities.get("canDownload", True)),
            export_links=dict(exports),
        )

    def download(self, file_id: str, dest: BinaryIO, max_bytes: int) -> int:
        """Descarga `files/{id}?alt=media` a `dest`; devuelve los bytes escritos."""
        with self._api.stream(f"files/{file_id}", {"alt": "media"}) as response:
            return _copy_limited(response, dest, max_bytes)

    def export(self, file_id: str, mime: str, dest: BinaryIO, max_bytes: int) -> int:
        """Exporta un documento nativo al `mime` pedido; devuelve los bytes escritos."""
        try:
            with self._api.stream(f"files/{file_id}/export", {"mimeType": mime}) as response:
                return _copy_limited(response, dest, max_bytes)
        except ForbiddenError as exc:
            if exc.reason == "exportSizeLimitExceeded":
                raise ExportTooLargeError(
                    f"exportación a {mime} demasiado grande: {file_id}"
                ) from exc
            raise
