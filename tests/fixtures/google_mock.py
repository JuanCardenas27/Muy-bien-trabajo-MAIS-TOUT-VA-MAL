"""Mocks respx de Classroom/Drive/OAuth sobre los fixtures (Task FND-05).

SYN-03/05, FET-01/03 y EXT-01/02 usan ``install_google_mocks`` en sus tests.
Todo el contenido servido sale de ``make_fixtures.py`` (nunca datos reales).
"""

import json
import re
from pathlib import Path

import httpx
import respx

from make_fixtures import (
    DOC_FILE_ID,
    DRIVE_FILE_IDS,
    FRENCH_COURSE_ID,
    IMAGE_FILE_ID,
    LOCKED_FILE_ID,
    MISSING_FILE_ID,
    PDF_FILE_ID,
    SLIDES_FILE_ID,
)

__all__ = [
    "CW_URL",
    "DOC_FILE_ID",
    "DRIVE_FILE_IDS",
    "FRENCH_COURSE_ID",
    "IMAGE_FILE_ID",
    "LOCKED_FILE_ID",
    "MISSING_FILE_ID",
    "PDF_FILE_ID",
    "SLIDES_FILE_ID",
    "install_google_mocks",
    "ts_sort_key",
]

CW_URL = f"https://classroom.googleapis.com/v1/courses/{FRENCH_COURSE_ID}/courseWork"
CLASSROOM_BASE = f"https://classroom.googleapis.com/v1/courses/{FRENCH_COURSE_ID}"
DRIVE_BASE = "https://www.googleapis.com/drive/v3/files"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:?\d{2}(?::\d{2})?)$"
)

SCENARIOS = ("v1", "v2", "deleted")


def ts_sort_key(ts: str) -> str:
    """Clave ordenable para `updateTime` con 0–9 decimales.

    Rellena la fracción a 9 dígitos y normaliza el offset a UTC. No depende
    de ``frances.timeutil`` (FND-05 solo depende de FND-01).
    """
    match = _TS_RE.match(ts)
    if match is None:  # pragma: no cover
        raise ValueError(f"timestamp inválido: {ts!r}")
    base, frac, zone = match.groups()
    frac9 = ((frac or "") + "0" * 9)[:9]
    if zone == "Z":
        return f"{base}.{frac9}Z"
    sign = 1 if zone[0] == "+" else -1
    digits = zone[1:].replace(":", "")
    offset_min = sign * (int(digits[:2]) * 60 + int(digits[2:4]))
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    utc = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc) - timedelta(
        minutes=offset_min
    )
    return utc.strftime("%Y-%m-%dT%H:%M:%S") + f".{frac9}Z"


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parent


def _scenario_file(scenario: str, name: str) -> dict[str, object]:
    path = _fixtures_root() / "classroom" / scenario / name
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _drive_meta(file_id: str) -> dict[str, object] | None:
    path = _fixtures_root() / "drive" / "files" / f"{file_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _error(status: int, reason: str, message: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"error": {"code": status, "message": message, "errors": [{"reason": reason}]}},
    )


def install_google_mocks(router: respx.Router, scenario: str = "v1") -> None:
    """Registra en ``router`` los endpoints de Classroom, Drive y OAuth."""
    if scenario not in SCENARIOS:
        raise ValueError(f"escenario desconocido: {scenario!r} (esperado uno de {SCENARIOS})")

    def coursework(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        page1 = _scenario_file(scenario, "courseWork.page1.json")
        page2 = _scenario_file(scenario, "courseWork.page2.json")
        items = list(page1["courseWork"]) + list(page2["courseWork"])  # type: ignore[union-attr]
        if params.get("orderBy") == "updateTime desc":
            items.sort(key=lambda i: ts_sort_key(str(i["updateTime"])), reverse=True)
        if params.get("pageToken"):
            return httpx.Response(200, json={"courseWork": items[len(page1["courseWork"]):]})  # type: ignore[union-attr]  # noqa: E501
        first = items[: len(page1["courseWork"])]  # type: ignore[union-attr]
        token = page1.get("nextPageToken", "page2")  # type: ignore[union-attr]
        return httpx.Response(200, json={"courseWork": first, "nextPageToken": token})

    router.get(f"{CLASSROOM_BASE}/courseWork").mock(side_effect=coursework)
    router.get(f"{CLASSROOM_BASE}/courseWorkMaterials").mock(
        side_effect=lambda _: httpx.Response(
            200, json=_scenario_file(scenario, "courseWorkMaterials.json")
        )
    )
    router.get(f"{CLASSROOM_BASE}/announcements").mock(
        side_effect=lambda _: httpx.Response(200, json=_scenario_file(scenario, "announcements.json"))
    )
    router.get(f"{CLASSROOM_BASE}/topics").mock(
        side_effect=lambda _: httpx.Response(200, json=_scenario_file(scenario, "topics.json"))
    )
    router.get("https://classroom.googleapis.com/v1/courses").mock(
        side_effect=lambda _: httpx.Response(200, json=_scenario_file(scenario, "courses.json"))
    )

    def drive_file(request: httpx.Request) -> httpx.Response:
        file_id = request.url.path.rsplit("/", 1)[-1]
        meta = _drive_meta(file_id)
        if meta is None:
            return _error(404, "notFound", f"archivo inexistente: {file_id}")
        if scenario != "v1" and file_id == PDF_FILE_ID:
            # La profesora reemplazó el PDF sin editar la publicación (Review Focus 2).
            meta = {**meta, "version": str(int(str(meta["version"])) + 1)}
        if request.url.params.get("alt") == "media":
            return _download_bytes(file_id, meta)
        return httpx.Response(200, json=meta)

    def drive_export(request: httpx.Request) -> httpx.Response:
        file_id = request.url.path.rsplit("/", 2)[-2]
        meta = _drive_meta(file_id)
        if meta is None:
            return _error(404, "notFound", f"archivo inexistente: {file_id}")
        mime = request.url.params.get("mimeType", "")
        if mime == "application/pdf":
            # Exportación pesada rechazada por Drive (Review Focus 4).
            return _error(403, "exportSizeLimitExceeded", "exportación demasiado grande")
        if mime == "text/plain":
            export = _fixtures_root() / "drive" / "export" / f"{file_id}.txt"
            if export.is_file():
                return httpx.Response(
                    200, content=export.read_bytes(), headers={"Content-Type": "text/plain"}
                )
        return _error(400, "badRequest", f"export no soportado: {mime!r}")

    router.get(url__regex=re.compile(rf"{re.escape(DRIVE_BASE)}/[^/?]+(\?.*)?$")).mock(
        side_effect=drive_file
    )
    router.get(url__regex=re.compile(rf"{re.escape(DRIVE_BASE)}/[^/?]+/export(\?.*)?$")).mock(
        side_effect=drive_export
    )
    router.post(TOKEN_URL).mock(
        side_effect=lambda _: httpx.Response(
            200,
            json={
                "access_token": "ya29.fixture",
                "expires_in": 3599,
                "token_type": "Bearer",
            },
        )
    )


def _download_bytes(file_id: str, meta: dict[str, object]) -> httpx.Response:
    if meta.get("capabilities", {}).get("canDownload") is False:  # type: ignore[union-attr]
        return _error(403, "downloadRestricted", "descarga no permitida")
    root = _fixtures_root()
    if file_id == PDF_FILE_ID:
        blob = root / "pdf" / "lesson-text.pdf"
    elif file_id == IMAGE_FILE_ID:
        blob = root / "images" / "phrase.png"
    else:  # pragma: no cover
        return _error(400, "badRequest", "los tipos Google Apps se descargan con export")
    return httpx.Response(
        200, content=blob.read_bytes(), headers={"Content-Type": str(meta["mimeType"])}
    )
