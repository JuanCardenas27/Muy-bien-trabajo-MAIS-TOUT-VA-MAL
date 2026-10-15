"""Repo de sync: watermarks, items, adjuntos, tombstones (SYN-04)."""

import sqlite3

import pytest

from frances.db.store import Store
from frances.models.classroom import Attachment
from frances.models.ids import attachment_id, item_id
from frances.sync.repo import (
    get_watermark,
    live_item_ids,
    set_watermark,
    sync_attachments,
    tombstone_items,
    restore_items,
)

NOW = "2026-10-14T10:17:00.000000Z"
NOW2 = "2026-10-15T10:17:00.000000Z"
NOW3 = "2026-10-16T10:17:00.000000Z"

FR = "cours_fr_a2_g3"
CW_ID = item_id("coursework", "1002")
AN_ID = item_id("announcement", "3001")

PDF = Attachment(
    id=attachment_id(CW_ID, "drive_file", "f_pdf"),
    item_id=CW_ID,
    kind="drive_file",
    external_id="f_pdf",
    title="Leçon 1",
    url="https://drive.google.com/f_pdf",
    mime_type=None,
)
LINK = Attachment(
    id=attachment_id(CW_ID, "link", "https://example.org/conjugaison"),
    item_id=CW_ID,
    kind="link",
    external_id="https://example.org/conjugaison",
    title="Conjugaison",
    url="https://example.org/conjugaison",
    mime_type=None,
)


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:  # type: ignore[no-untyped-def]
    store = Store.open(tmp_path / "repo.db")
    store.conn.row_factory = sqlite3.Row
    c = store.conn
    c.execute(
        "INSERT INTO courses (id, name, section, state, alternate_link,"
        " update_time, included, raw_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (FR, "Français A2", "G3", "ACTIVE", None, NOW, 1, "{}"),
    )
    for iid, kind, cid in ((CW_ID, "coursework", "1002"), (AN_ID, "announcement", "3001")):
        c.execute(
            "INSERT INTO items (id, course_id, kind, classroom_id, topic_id, title,"
            " text, state, alternate_link, creation_time, update_time, due_at,"
            " content_hash, raw_json, first_seen_at, last_seen_at, deleted_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                iid,
                FR,
                kind,
                cid,
                None,
                "T",
                "texte",
                "PUBLISHED",
                None,
                NOW,
                NOW,
                None,
                "hash-" + iid,
                "{}",
                NOW,
                NOW,
                None,
            ),
        )
    an_att = attachment_id(AN_ID, "drive_file", "f_x")
    c.execute(
        "INSERT INTO attachments (id, item_id, kind, external_id, title, url,"
        " mime_type, drive_version, status, updated_at, removed_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (an_att, AN_ID, "drive_file", "f_x", "X", "https://drive.google.com/f_x",
         None, None, "pending", NOW, None),
    )
    return c


def status_of(conn: sqlite3.Connection, att_id: str) -> str | None:
    row = conn.execute("SELECT status FROM attachments WHERE id = ?", (att_id,)).fetchone()
    return str(row[0]) if row else None


def removed_at(conn: sqlite3.Connection, att_id: str) -> str | None:
    row = conn.execute(
        "SELECT removed_at FROM attachments WHERE id = ?", (att_id,)
    ).fetchone()
    return str(row[0]) if row and row[0] is not None else None


def attachments_of(conn: sqlite3.Connection, item: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM attachments WHERE item_id = ?", (item,)).fetchall()


def test_sync_attachments_insert_remove_restore(conn: sqlite3.Connection) -> None:
    assert sync_attachments(conn, CW_ID, [PDF, LINK], NOW) == 2
    assert status_of(conn, PDF.id) == "pending" and status_of(conn, LINK.id) == "reference"
    assert sync_attachments(conn, CW_ID, [PDF], NOW2) == 0
    assert removed_at(conn, LINK.id) == NOW2
    assert sync_attachments(conn, CW_ID, [PDF, LINK], NOW3) == 0
    assert removed_at(conn, LINK.id) is None


def test_set_watermark_never_moves_back(conn: sqlite3.Connection) -> None:
    set_watermark(conn, FR, "coursework", "2026-10-02T00:00:00.000000Z", NOW)
    set_watermark(conn, FR, "coursework", "2026-10-01T00:00:00.000000Z", NOW2)
    assert get_watermark(conn, FR, "coursework") == "2026-10-02T00:00:00.000000Z"


def test_tombstone_and_restore_items(conn: sqlite3.Connection) -> None:
    assert AN_ID in live_item_ids(conn, FR, "announcement")
    assert tombstone_items(conn, [AN_ID], NOW) == 1
    row = conn.execute("SELECT deleted_at FROM items WHERE id = ?", (AN_ID,)).fetchone()
    assert row is not None and str(row[0]) == NOW
    for att in attachments_of(conn, AN_ID):
        assert att["removed_at"] == NOW
    assert restore_items(conn, [AN_ID]) == 1
    row = conn.execute("SELECT deleted_at FROM items WHERE id = ?", (AN_ID,)).fetchone()
    assert row is not None and row[0] is None
    for att in attachments_of(conn, AN_ID):
        assert att["removed_at"] is None
