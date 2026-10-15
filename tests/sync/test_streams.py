"""Sync incremental por stream con watermark (SYN-04)."""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

from google_mock import CW_URL, FRENCH_COURSE_ID, install_google_mocks

from frances.config import ClassroomSettings, Settings
from frances.db.dump import dump_sql
from frances.db.store import Store
from frances.models.ids import item_id
from frances.sync.classroom import CLASSROOM_BASE_URL, ClassroomClient, parse_course
from frances.sync.google_http import GoogleApi, RetryExhaustedError
from frances.sync.streams import select_courses, sync_stream
from frances.timeutil import format_ts

pytestmark = pytest.mark.respx(assert_all_called=False)

FR = FRENCH_COURSE_ID
FIX = Path(__file__).resolve().parents[1] / "fixtures"

FIXED = datetime(2026, 10, 14, 10, 17, tzinfo=UTC)
NOW = format_ts(FIXED)
NOW2 = "2026-10-15T10:17:00.000000Z"
NOW3 = "2026-10-16T10:17:00.000000Z"

M_PDF: dict[str, Any] = {
    "driveFile": {
        "driveFile": {
            "id": "f_pdf",
            "title": "Leçon 1",
            "alternateLink": "https://drive.google.com/f_pdf",
        }
    }
}
M_LINK: dict[str, Any] = {
    "link": {"url": "https://example.org/conjugaison", "title": "Conjugaison"}
}


def cw(x: str) -> str:
    return item_id("coursework", x)


def an(x: str) -> str:
    return item_id("announcement", x)


def raws(scenario: str, kind: str) -> list[dict]:
    sdir = FIX / "classroom" / scenario
    if kind == "coursework":
        out: list[dict] = []
        for name in ("courseWork.page1.json", "courseWork.page2.json"):
            out.extend(json.loads((sdir / name).read_text(encoding="utf-8"))["courseWork"])
        return out
    files = {
        "material": ("courseWorkMaterials.json", "courseWorkMaterial"),
        "announcement": ("announcements.json", "announcements"),
    }
    fname, key = files[kind]
    return json.loads((sdir / fname).read_text(encoding="utf-8"))[key]


def courses(scenario: str) -> list[dict]:
    return json.loads((FIX / "classroom" / scenario / "courses.json").read_text(encoding="utf-8"))[
        "courses"
    ]


class FakeCreds:
    def __init__(self, token: str = "t0") -> None:
        self.token = token
        self.valid = True

    def refresh(self, request: object) -> None:
        self.token = "t1"


def client(sleep: Any = None) -> ClassroomClient:
    kw: dict[str, Any] = {}
    if sleep is not None:
        kw["sleep"] = sleep
    return ClassroomClient(GoogleApi(FakeCreds(), CLASSROOM_BASE_URL, **kw))


def raw(cid: str, update_time: str, title: str = "T", materials: Any = ()) -> dict[str, Any]:
    return {
        "id": cid,
        "courseId": FR,
        "title": title,
        "description": f"desc {cid}",
        "materials": list(materials),
        "topicId": None,
        "state": "PUBLISHED",
        "alternateLink": f"https://classroom.google.com/c/{FR}/a/{cid}",
        "creationTime": "2026-10-01T10:00:00Z",
        "updateTime": update_time,
    }


def seeded_store(tmp_path: Path, watermark: str | None) -> Store:
    store = Store.open(tmp_path / "state.db")
    with store.tx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO courses"
            " (id, name, section, state, alternate_link, update_time, included, raw_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (FR, "Français A2", "G3", "ACTIVE", None, NOW, 1, "{}"),
        )
        if watermark is not None:
            conn.execute(
                "INSERT OR REPLACE INTO watermarks"
                " (course_id, stream, last_update_time, last_run_at)"
                " VALUES (?, ?, ?, ?)",
                (FR, "coursework", watermark, NOW),
            )
    return store


def route_coursework(router: respx.Router, items: list[dict]) -> None:
    router.get(CW_URL, name="cw").mock(
        side_effect=lambda _req: httpx.Response(200, json={"courseWork": items})
    )


class _Counter:
    def __init__(self) -> None:
        self.call_count = 0


def route_two_pages(
    router: respx.Router,
    page1: list[dict],
    page2: list[dict] | None = None,
    page2_status: int = 200,
) -> tuple[_Counter, _Counter]:
    c1, c2 = _Counter(), _Counter()
    second: list[dict] = page2 if page2 is not None else [raw("1003", "2026-10-01T11:00:00Z")]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("pageToken") == "p2":
            c2.call_count += 1
            if page2_status != 200:
                return httpx.Response(page2_status)
            return httpx.Response(200, json={"courseWork": second})
        c1.call_count += 1
        return httpx.Response(200, json={"courseWork": page1, "nextPageToken": "p2"})

    router.get(CW_URL, name="cw").mock(side_effect=handler)
    return c1, c2


def item_ids(store: Store) -> set[str]:
    return {r[0] for r in store.conn.execute("SELECT id FROM items").fetchall()}


def update_time(store: Store, item: str) -> str | None:
    row = store.conn.execute("SELECT update_time FROM items WHERE id = ?", (item,)).fetchone()
    return str(row[0]) if row else None


def watermark(store: Store) -> str | None:
    row = store.conn.execute(
        "SELECT last_update_time FROM watermarks WHERE course_id = ? AND stream = ?",
        (FR, "coursework"),
    ).fetchone()
    return str(row[0]) if row else None


def item_row(store: Store, item: str) -> dict[str, Any]:
    cur = store.conn.execute("SELECT * FROM items WHERE id = ?", (item,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    assert row is not None
    return dict(zip(cols, row, strict=True))


def attachment(store: Store, item: str, kind: str) -> dict[str, Any]:
    cur = store.conn.execute(
        "SELECT * FROM attachments WHERE item_id = ? AND kind = ?", (item, kind)
    )
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    assert row is not None
    return dict(zip(cols, row, strict=True))


def test_watermark_variable_fraction_digits(tmp_path: Path, respx_mock: respx.Router) -> None:
    store = seeded_store(tmp_path, watermark="2026-10-01T10:00:23.000000Z")
    route_coursework(
        respx_mock,
        [
            raw("1001", "2026-10-01T10:00:23.5Z"),
            raw("1003", "2026-10-01T10:00:23.045123456Z"),
            raw("1002", "2026-10-01T10:00:22.9Z"),
        ],
    )
    r = sync_stream(store, client(), FR, "coursework", NOW, overlap=timedelta(0))
    assert (r.seen, r.upserted, r.stopped_at_watermark) == (2, 2, True)
    assert item_ids(store) == {cw("1001"), cw("1003")}
    assert update_time(store, cw("1003")) == "2026-10-01T10:00:23.045123Z"
    assert watermark(store) == "2026-10-01T10:00:23.500000Z" == r.max_update_time


def test_stops_paging_at_watermark(tmp_path: Path, respx_mock: respx.Router) -> None:
    store = seeded_store(tmp_path, watermark="2026-10-01T12:25:00.000000Z")
    p1, p2 = route_two_pages(
        respx_mock,
        page1=[
            raw("1001", "2026-10-01T12:30:00Z"),
            raw("1002", "2026-10-01T12:00:00Z"),
        ],
    )
    sync_stream(store, client(), FR, "coursework", NOW, overlap=timedelta(0))
    assert p1.call_count == 1 and p2.call_count == 0


def test_failure_mid_stream_keeps_watermark(tmp_path: Path, respx_mock: respx.Router) -> None:
    store = seeded_store(tmp_path, watermark="2026-09-01T00:00:00.000000Z")
    _p1, p2 = route_two_pages(
        respx_mock,
        page1=[raw("1001", "2026-10-01T12:30:00Z")],
        page2_status=500,
    )
    with pytest.raises(RetryExhaustedError):
        sync_stream(store, client(sleep=lambda s: None), FR, "coursework", NOW)
    assert watermark(store) == "2026-09-01T00:00:00.000000Z" and item_ids(store) == set()
    assert p2.call_count == 5


def test_overlap_reprocessing_is_idempotent(tmp_path: Path, respx_mock: respx.Router) -> None:
    install_google_mocks(respx_mock, "v1")
    store = seeded_store(tmp_path, watermark=None)
    sync_stream(store, client(), FR, "coursework", NOW)
    first = dump_sql(store)
    assert sync_stream(store, client(), FR, "coursework", NOW).upserted == 0
    assert dump_sql(store) == first


def test_edited_item_updates_and_marks_removed_attachment(
    tmp_path: Path, respx_mock: respx.Router
) -> None:
    store = seeded_store(tmp_path, watermark=None)
    route_coursework(respx_mock, [raw("1002", "2026-10-01T12:00:00Z", materials=[M_PDF, M_LINK])])
    sync_stream(store, client(), FR, "coursework", NOW)
    route_coursework(
        respx_mock,
        [raw("1002", "2026-10-08T15:00:00.123Z", title="Nouveau", materials=[M_PDF])],
    )
    res = sync_stream(store, client(), FR, "coursework", NOW2)
    assert res.upserted == 1
    row = item_row(store, cw("1002"))
    assert row["first_seen_at"] == NOW and row["last_seen_at"] == NOW2
    assert row["title"] == "Nouveau"
    assert attachment(store, cw("1002"), "link")["removed_at"] == NOW2
    assert attachment(store, cw("1002"), "drive_file")["removed_at"] is None


def test_full_ignores_watermark(tmp_path: Path, respx_mock: respx.Router) -> None:
    store = seeded_store(tmp_path, watermark="2026-10-01T12:25:00.000000Z")
    p1, p2 = route_two_pages(
        respx_mock,
        page1=[
            raw("1001", "2026-10-01T12:30:00Z"),
            raw("1002", "2026-10-01T12:00:00Z"),
        ],
    )
    r = sync_stream(store, client(), FR, "coursework", NOW, overlap=timedelta(0), full=True)
    assert r.seen == 3
    assert p1.call_count == 1 and p2.call_count == 1


def test_select_courses_ids_override_regex() -> None:
    parsed = [parse_course(c) for c in courses("v1")]
    calc = next(c for c in courses("v1") if c["name"] == "Cálculo Diferencial")
    only_calc = select_courses(
        parsed, Settings(classroom=ClassroomSettings(include_course_ids=[calc["id"]]))
    )
    assert [c.id for c in only_calc] == [calc["id"]]
    default = select_courses(parsed, Settings())
    assert [c.id for c in default] == [FR]
