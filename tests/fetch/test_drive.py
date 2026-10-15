"""Tests del DriveClient: metadatos, descarga y exportación (FET-01)."""

import io
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

from google_mock import install_google_mocks  # noqa: E402

from frances.fetch.drive import (  # noqa: E402
    DRIVE_BASE_URL,
    GOOGLE_NATIVE_EXPORTS,
    DriveClient,
    ExportTooLargeError,
    TooLargeError,
)
from frances.sync.google_http import GoogleApi  # noqa: E402

pytestmark = pytest.mark.respx(assert_all_called=False)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"


class FakeCreds:
    """Doble local de credenciales: token, valid y refresh(request)."""

    def __init__(self, token: str = "t0") -> None:
        self.token = token
        self.valid = True
        self.refresh_calls = 0

    def refresh(self, request: object) -> None:
        self.refresh_calls += 1
        self.token = f"t{self.refresh_calls}"


def drive() -> DriveClient:
    return DriveClient(GoogleApi(FakeCreds(token="t0"), DRIVE_BASE_URL))


def raws(scenario: str, kind: str) -> list[dict[str, Any]]:
    base = FIXTURES / "classroom" / scenario
    if kind == "coursework":
        pages = []
        for name in ("courseWork.page1.json", "courseWork.page2.json"):
            payload = json.loads((base / name).read_text(encoding="utf-8"))
            pages.extend(payload["courseWork"])
        return pages
    if kind == "material":
        payload = json.loads((base / "courseWorkMaterials.json").read_text(encoding="utf-8"))
        return list(payload["courseWorkMaterial"])
    if kind == "announcement":
        payload = json.loads((base / "announcements.json").read_text(encoding="utf-8"))
        return list(payload["announcements"])
    raise ValueError(f"kind desconocido: {kind!r}")


def courses(scenario: str) -> list[dict[str, Any]]:
    payload = json.loads(
        (FIXTURES / "classroom" / scenario / "courses.json").read_text(encoding="utf-8")
    )
    return list(payload["courses"])


def drive_ids(scenario: str) -> list[str]:
    ids: list[str] = []
    for kind in ("coursework", "material", "announcement"):
        for raw in raws(scenario, kind):
            for material in raw.get("materials", []):
                entry = material.get("driveFile", {}).get("driveFile", {})
                file_id = entry.get("id")
                if file_id and file_id not in ids:
                    ids.append(file_id)
    return ids


def drive_meta(scenario: str) -> dict[str, dict[str, Any] | None]:
    meta: dict[str, dict[str, Any] | None] = {}
    with respx.mock(assert_all_called=False) as router:
        install_google_mocks(router, scenario)
        with httpx.Client(trust_env=False) as client:
            for file_id in drive_ids(scenario):
                resp = client.get(f"{DRIVE_FILES_URL}/{file_id}")
                meta[file_id] = resp.json() if resp.status_code == 200 else None
    return meta


def first_id(
    meta: dict[str, dict[str, Any] | None],
    mime: str | None = None,
    can_download: bool | None = None,
) -> str:
    for file_id, raw in meta.items():
        if raw is None:
            continue
        if mime is not None and raw["mimeType"] != mime:
            continue
        if can_download is not None and raw["capabilities"]["canDownload"] is not can_download:
            continue
        return file_id
    raise AssertionError(f"sin id para mime={mime!r} can_download={can_download!r}")


def test_get_metadata_fields(respx_mock: respx.Router) -> None:
    meta = drive_meta("v1")
    doc = next(i for i, m in meta.items() if m and m["mimeType"] == "application/vnd.google-apps.document")
    install_google_mocks(respx_mock, "v1")
    m = drive().get_metadata(doc)
    assert (m.mime_type, m.version, m.can_download, m.size) == (
        meta[doc]["mimeType"],
        meta[doc]["version"],
        meta[doc]["capabilities"]["canDownload"],
        None,
    )
    p = respx_mock.calls.last.request.url.params
    assert p["supportsAllDrives"] == "true" and "capabilities/canDownload" in p["fields"]


def test_download_streams_and_counts(respx_mock: respx.Router) -> None:
    pdf = first_id(drive_meta("v1"), mime="application/pdf", can_download=True)
    install_google_mocks(respx_mock, "v1")
    buf = io.BytesIO()
    n = drive().download(pdf, buf, max_bytes=50 * 1024 * 1024)
    assert n == len(buf.getvalue()) > 0 and buf.getvalue().startswith(b"%PDF")
    assert respx_mock.calls.last.request.url.params["alt"] == "media"


def test_export_size_limit_raises_export_too_large(respx_mock: respx.Router) -> None:
    slides = first_id(drive_meta("v1"), mime="application/vnd.google-apps.presentation")
    install_google_mocks(respx_mock, "v1")  # FND-05: export de Slides a PDF → 403
    with pytest.raises(ExportTooLargeError):
        drive().export(slides, "application/pdf", io.BytesIO(), max_bytes=50 * 1024 * 1024)


def test_download_over_limit_raises(respx_mock: respx.Router) -> None:
    pdf = first_id(drive_meta("v1"), mime="application/pdf", can_download=True)
    install_google_mocks(respx_mock, "v1")
    with pytest.raises(TooLargeError):
        drive().download(pdf, io.BytesIO(), max_bytes=10)


def test_native_exports_table() -> None:
    assert GOOGLE_NATIVE_EXPORTS["application/vnd.google-apps.spreadsheet"][1] == (
        "text/csv",
        "text",
    )
