"""Tests de los mocks respx de Classroom/Drive/OAuth (Task FND-05)."""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
import respx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

from google_mock import (  # noqa: E402
    CW_URL,
    FRENCH_COURSE_ID,
    LOCKED_FILE_ID,
    MISSING_FILE_ID,
    PDF_FILE_ID,
    SLIDES_FILE_ID,
    install_google_mocks,
    ts_sort_key,
)


@contextmanager
def mocked(scenario: str = "v1") -> Iterator[httpx.Client]:
    """Cliente sin proxies del entorno sobre el router con mocks instalados."""
    with respx.mock(assert_all_called=False) as router:
        install_google_mocks(router, scenario)
        with httpx.Client(trust_env=False) as client:
            yield client


def test_ts_sort_key_pads_fraction_to_nine_digits() -> None:
    assert ts_sort_key("2026-08-03T13:00:00Z") == "2026-08-03T13:00:00.000000000Z"
    assert ts_sort_key("2026-08-03T13:00:00.12Z") == "2026-08-03T13:00:00.120000000Z"
    assert ts_sort_key("2026-08-03T13:00:00.123456789Z") > ts_sort_key("2026-08-03T13:00:00.12Z")
    assert ts_sort_key("2026-08-03T13:00:00.5Z") < ts_sort_key("2026-08-03T13:00:01Z")


def test_coursework_pagination_and_order() -> None:
    with mocked("v1") as client:
        p1 = client.get(f"{CW_URL}?orderBy=updateTime%20desc&pageSize=100").json()
        p2 = client.get(
            f"{CW_URL}?orderBy=updateTime%20desc&pageSize=100&pageToken={p1['nextPageToken']}"
        ).json()
    items = p1["courseWork"] + p2["courseWork"]
    assert len(items) == 120 and "nextPageToken" not in p2
    keys = [ts_sort_key(i["updateTime"]) for i in items]
    assert keys == sorted(keys, reverse=True)
    assert {i["courseId"] for i in items} == {FRENCH_COURSE_ID}


def test_mock_scenarios_cover_review_focus() -> None:
    with mocked("v1") as client:
        v1_meta = client.get(f"https://www.googleapis.com/drive/v3/files/{PDF_FILE_ID}").json()
    with mocked("v2") as client:
        v2_meta = client.get(f"https://www.googleapis.com/drive/v3/files/{PDF_FILE_ID}").json()
        # El Slides se exporta a texto pero el PDF grande se rechaza (Review Focus 4).
        txt = client.get(
            f"https://www.googleapis.com/drive/v3/files/{SLIDES_FILE_ID}/export",
            params={"mimeType": "text/plain"},
        )
        denied = client.get(
            f"https://www.googleapis.com/drive/v3/files/{SLIDES_FILE_ID}/export",
            params={"mimeType": "application/pdf"},
        )
        locked = client.get(f"https://www.googleapis.com/drive/v3/files/{LOCKED_FILE_ID}").json()
        missing = client.get(f"https://www.googleapis.com/drive/v3/files/{MISSING_FILE_ID}")
    assert v1_meta["id"] == v2_meta["id"] == PDF_FILE_ID
    assert int(v2_meta["version"]) > int(v1_meta["version"])  # Review Focus 2
    assert txt.status_code == 200 and len(txt.content) > 0
    assert denied.status_code == 403
    assert denied.json()["error"]["errors"][0]["reason"] == "exportSizeLimitExceeded"
    assert locked["capabilities"]["canDownload"] is False
    assert missing.status_code == 404


def test_deleted_scenario_misses_one_v1_material() -> None:
    def material_ids(scenario: str) -> set[str]:
        base = f"https://classroom.googleapis.com/v1/courses/{FRENCH_COURSE_ID}"
        with mocked(scenario) as client:
            payload = client.get(f"{base}/courseWorkMaterials").json()
        return {item["id"] for item in payload["courseWorkMaterial"]}

    assert material_ids("deleted") < material_ids("v1")


def test_drive_download_serves_fixture_bytes(fixtures_dir: Path) -> None:
    with mocked("v1") as client:
        pdf = client.get(
            f"https://www.googleapis.com/drive/v3/files/{PDF_FILE_ID}", params={"alt": "media"}
        )
    expected = (fixtures_dir / "pdf" / "lesson-text.pdf").read_bytes()
    assert pdf.status_code == 200 and pdf.content == expected


def test_token_endpoint_mocked() -> None:
    with mocked("v1") as client:
        resp = client.post("https://oauth2.googleapis.com/token", data={"grant_type": "x"})
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "ya29.fixture"


def test_unknown_scenario_raises() -> None:
    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(ValueError):
            install_google_mocks(router, "nope")
