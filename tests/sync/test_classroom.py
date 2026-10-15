"""Tests del ClassroomClient: cursos, temas y streams por updateTime desc (SYN-03)."""

import json
import sys
from pathlib import Path

import pytest
import respx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

from google_mock import FRENCH_COURSE_ID, install_google_mocks

from frances.models.ids import item_id
from frances.sync.classroom import (
    ClassroomClient,
    parse_course,
    parse_item,
)
from frances.sync.google_http import GoogleApi

pytestmark = pytest.mark.respx(assert_all_called=False)

FR = FRENCH_COURSE_ID
FIX = Path(__file__).resolve().parents[1] / "fixtures"

_KIND_FILES: dict[str, tuple[str, str]] = {
    "coursework": ("courseWork.page1.json,courseWork.page2.json", "courseWork"),
    "material": ("courseWorkMaterials.json", "courseWorkMaterial"),
    "announcement": ("announcements.json", "announcements"),
}


def raws(scenario: str, kind: str) -> list[dict]:
    sdir = FIX / "classroom" / scenario
    if kind == "coursework":
        out: list[dict] = []
        for name in ("courseWork.page1.json", "courseWork.page2.json"):
            out.extend(json.loads((sdir / name).read_text(encoding="utf-8"))["courseWork"])
        return out
    fname, key = _KIND_FILES[kind]
    return json.loads((sdir / fname).read_text(encoding="utf-8"))[key]


def courses(scenario: str) -> list[dict]:
    return json.loads((FIX / "classroom" / scenario / "courses.json").read_text(encoding="utf-8"))[
        "courses"
    ]


class FakeCreds:
    """Doble local de credenciales siempre válidas."""

    def __init__(self, token: str = "t0") -> None:
        self.token = token
        self.valid = True

    def refresh(self, request: object) -> None:
        self.token = "t1"


def client() -> ClassroomClient:
    from frances.sync.classroom import CLASSROOM_BASE_URL

    return ClassroomClient(GoogleApi(FakeCreds(), CLASSROOM_BASE_URL))


BASE_RAW: dict = {
    "id": "cw_9999",
    "courseId": FR,
    "title": "Le passé composé (exercice 001)",
    "description": "Les enfants chantent une chanson.",
    "materials": [],
    "topicId": "topic_vocabulaire",
    "state": "PUBLISHED",
    "alternateLink": f"https://classroom.google.com/c/{FR}/a/cw_9999",
    "creationTime": "2026-10-01T10:00:23Z",
    "updateTime": "2026-10-01T10:00:23.045123456Z",
}

M_PDF: dict = {"driveFile": {"driveFile": {"id": "drive_pdf_lesson", "title": "lesson-text.pdf"}}}
M_LINK: dict = {"link": {"url": "https://example.test/guide", "title": "Guide"}}


def test_iter_stream_params(respx_mock: respx.Router) -> None:
    install_google_mocks(respx_mock, "v1")
    list(client().iter_stream(FR, "coursework"))
    p = respx_mock.calls.last.request.url.params
    assert p["orderBy"] == "updateTime desc" and p["pageSize"] == "100"
    assert p["courseWorkStates"] == "PUBLISHED"
    list(client().iter_stream(FR, "material"))
    assert respx_mock.calls.last.request.url.params["courseWorkMaterialStates"] == "PUBLISHED"


def test_parse_three_kinds() -> None:
    cw_raw, mt_raw, an_raw = (raws("v1", k)[0] for k in ("coursework", "material", "announcement"))
    cw = parse_item(cw_raw, "coursework", FR)
    an = parse_item(an_raw, "announcement", FR)
    assert cw.id == item_id("coursework", cw_raw["id"]) and cw.text == cw_raw.get("description", "")
    assert an.id == item_id("announcement", an_raw["id"])
    assert an.title is None and an.text == an_raw["text"]
    assert parse_item(mt_raw, "material", FR).id == item_id("material", mt_raw["id"])


def test_due_at_with_time_and_default_bogota() -> None:
    raw = {
        **BASE_RAW,
        "dueDate": {"year": 2026, "month": 10, "day": 20},
        "dueTime": {"hours": 15, "minutes": 30},
    }
    assert parse_item(raw, "coursework", FR).due_at == "2026-10-20T15:30:00.000000Z"
    raw = {**BASE_RAW, "dueDate": {"year": 2026, "month": 10, "day": 20}}
    assert parse_item(raw, "coursework", FR).due_at == "2026-10-21T04:59:00.000000Z"
    raw = {
        **BASE_RAW,
        "dueDate": {"year": 2026, "month": 10, "day": 20},
        "dueTime": {"hours": 9},
    }
    assert parse_item(raw, "coursework", FR).due_at == "2026-10-20T09:00:00.000000Z"


def test_content_hash_stable_under_materials_order() -> None:
    a = parse_item({**BASE_RAW, "materials": [M_PDF, M_LINK]}, "coursework", FR)
    b = parse_item({**BASE_RAW, "materials": [M_LINK, M_PDF]}, "coursework", FR)
    c = parse_item({**BASE_RAW, "title": "Autre", "materials": [M_PDF, M_LINK]}, "coursework", FR)
    assert a.content_hash == b.content_hash != c.content_hash


def test_list_courses_active_student_me(respx_mock: respx.Router) -> None:
    install_google_mocks(respx_mock, "v1")
    got = client().list_courses()
    ids = [c.id for c in got]
    assert FR in ids
    assert set(ids) <= {c["id"] for c in courses("v1")}
    assert [parse_course(c).id for c in courses("v1") if c["id"] in ids] == ids
    p = respx_mock.calls.last.request.url.params
    assert p["studentId"] == "me" and p["courseStates"] == "ACTIVE"


def test_timestamps_normalized_and_raw_json_canonical() -> None:
    item = parse_item(BASE_RAW, "coursework", FR)
    assert item.update_time == "2026-10-01T10:00:23.045123Z"
    assert item.creation_time == "2026-10-01T10:00:23.000000Z"
    assert item.raw_json == json.dumps(BASE_RAW, sort_keys=True, ensure_ascii=False)
