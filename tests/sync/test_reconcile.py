"""Reconciliación completa: tombstones de publicaciones y adjuntos (SYN-06)."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import respx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

from google_mock import FRENCH_COURSE_ID, install_google_mocks

from frances.db.store import Store
from frances.models.ids import item_id
from frances.sync.classroom import (
    CLASSROOM_BASE_URL,
    ClassroomClient,
    parse_course,
)
from frances.sync.google_http import GoogleApi
from frances.sync.reconcile import reconcile
from frances.sync.streams import sync_stream
from frances.timeutil import format_ts

FR = FRENCH_COURSE_ID
BASE = CLASSROOM_BASE_URL
FIX = Path(__file__).resolve().parents[1] / "fixtures"

FIXED = datetime(2026, 10, 14, 10, 17, tzinfo=UTC)
NOW = format_ts(FIXED)
NOW2 = "2026-10-15T10:17:00.000000Z"
NOW3 = "2026-10-16T10:17:00.000000Z"


def mt(x: str) -> str:
    return item_id("material", x)


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


FR_COURSE = parse_course(next(c for c in courses("v1") if c["id"] == FR))


class FakeCreds:
    def __init__(self, token: str = "t0") -> None:
        self.token = token
        self.valid = True

    def refresh(self, request: object) -> None:
        self.token = "t1"


def client() -> ClassroomClient:
    return ClassroomClient(GoogleApi(FakeCreds(), CLASSROOM_BASE_URL))


def synced_store(tmp_path: Path, scenario: str) -> Store:
    store = Store.open(tmp_path / "state.db")
    with store.tx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO courses"
            " (id, name, section, state, alternate_link, update_time, included, raw_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (FR, "Français A2", "G3", "ACTIVE", None, NOW, 1, "{}"),
        )
    with respx.mock(assert_all_called=False) as router:
        install_google_mocks(router, scenario)
        for stream in ("coursework", "material", "announcement"):
            sync_stream(store, client(), FR, stream, NOW)  # type: ignore[arg-type]
    return store


def item_row(store: Store, item: str) -> dict[str, Any]:
    cur = store.conn.execute("SELECT * FROM items WHERE id = ?", (item,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    assert row is not None
    return dict(zip(cols, row, strict=True))


def attachments_of(store: Store, item: str) -> list[dict[str, Any]]:
    cur = store.conn.execute("SELECT * FROM attachments WHERE item_id = ?", (item,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def test_deleted_scenario_tombstones_gone_materials(tmp_path: Path) -> None:
    store = synced_store(tmp_path, "v1")
    gone = {mt(x["id"]) for x in raws("v1", "material")} - {
        mt(x["id"]) for x in raws("deleted", "material")
    }
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "deleted")
        res = reconcile(store, client(), [FR_COURSE], NOW2)
    assert (res.deleted, res.restored, res.anomalies) == (len(gone), 0, []) and gone
    assert all(item_row(store, i)["deleted_at"] == NOW2 for i in gone)
    assert all(a["removed_at"] == NOW2 for i in gone for a in attachments_of(store, i))


def test_empty_stream_is_anomaly_and_marks_nothing(tmp_path: Path) -> None:
    store = synced_store(tmp_path, "v1")
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "v1")
        r.get(f"{BASE}/courses/{FR}/announcements").respond(200, json={})
        res = reconcile(store, client(), [FR_COURSE], NOW2)
    assert res.deleted == 0 and len(res.anomalies) == 1 and f"{FR}/announcement" in res.anomalies[0]
    assert all(
        item_row(store, an(x["id"]))["deleted_at"] is None for x in raws("v1", "announcement")
    )


def test_reappearing_item_is_restored(tmp_path: Path) -> None:
    store = synced_store(tmp_path, "v1")
    gone = {mt(x["id"]) for x in raws("v1", "material")} - {
        mt(x["id"]) for x in raws("deleted", "material")
    }
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "deleted")
        reconcile(store, client(), [FR_COURSE], NOW2)
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "v1")
        res = reconcile(store, client(), [FR_COURSE], NOW3)
    assert (res.deleted, res.restored) == (0, len(gone))
    assert all(item_row(store, i)["deleted_at"] is None for i in gone)


def test_course_not_listed_is_excluded(tmp_path: Path) -> None:
    store = synced_store(tmp_path, "v1")
    with respx.mock(assert_all_called=False) as r:
        install_google_mocks(r, "v1")
        res = reconcile(store, client(), [], NOW2)
    assert (res.deleted, res.restored, res.anomalies) == (0, 0, [])
    row = store.conn.execute("SELECT included FROM courses WHERE id = ?", (FR,)).fetchone()
    assert row is not None and int(row[0]) == 0
