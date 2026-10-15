"""Tests de la etapa fetch: descarga/export, re-fetch por versión y estados (FET-03)."""

import contextlib
import dataclasses
import hashlib
import json
import sqlite3
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import respx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

from google_mock import FRENCH_COURSE_ID, install_google_mocks  # noqa: E402

from frances.fetch.drive import NATIVE_PREFIX, DriveClient  # noqa: E402
from frances.fetch.run import run_fetch  # noqa: E402
from frances.models.ids import attachment_id, item_id  # noqa: E402
from frances.stage import StageContext, make_context  # noqa: E402
from frances.timeutil import format_ts, norm_ts  # noqa: E402

FAKE_ENV = {
    "GOOGLE_CLIENT_ID": "cid",
    "GOOGLE_CLIENT_SECRET": "csecret",
    "GOOGLE_REFRESH_TOKEN": "rt",
}
FIXED = datetime(2026, 10, 14, 10, 17, tzinfo=UTC)
NOW = format_ts(FIXED)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
KINDS = ("coursework", "material", "announcement")


def make_ctx(tmp_path: Path) -> StageContext:
    return dataclasses.replace(make_context(tmp_path, FAKE_ENV), now=lambda: FIXED)


def raws(scenario: str, kind: str) -> list[dict[str, Any]]:
    base = FIXTURES / "classroom" / scenario
    if kind == "coursework":
        pages: list[dict[str, Any]] = []
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
    for kind in KINDS:
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


def slides_ids(meta: dict[str, dict[str, Any] | None]) -> list[str]:
    return [
        i for i, m in meta.items() if m and m["mimeType"] == "application/vnd.google-apps.presentation"
    ]


def expected_status(m: dict[str, Any] | None) -> str:
    if m is None:
        return "not_found"
    if m["capabilities"]["canDownload"] is False:
        return "forbidden"
    if int(m.get("size", 0)) > 50 * 1024 * 1024:
        return "skipped_too_large"
    return "downloaded"


@contextlib.contextmanager
def mocks(scenario: str) -> Iterator[respx.Router]:
    with respx.mock(assert_all_called=False) as router:
        install_google_mocks(router, scenario)
        yield router


def _row_dict(conn: sqlite3.Connection, table: str, where: str, args: tuple[object, ...]) -> dict[str, Any]:
    cur = conn.execute(f"SELECT * FROM {table} WHERE {where}", args)
    names = [d[0] for d in cur.description]
    row = cur.fetchone()
    assert row is not None
    return dict(zip(names, row, strict=True))


def synced_ctx(tmp_path: Path, scenario: str) -> StageContext:
    """Contexto con curso, ítems y adjuntos drive_file sembrados desde los fixtures."""
    ctx = make_ctx(tmp_path)
    fr_raw = next(c for c in courses(scenario) if c["id"] == FRENCH_COURSE_ID)
    with ctx.store.tx() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO courses"
            " (id, name, section, state, alternate_link, update_time, included, raw_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fr_raw["id"],
                fr_raw["name"],
                fr_raw.get("section"),
                fr_raw["courseState"],
                fr_raw.get("alternateLink"),
                norm_ts(fr_raw["updateTime"]),
                1,
                json.dumps(fr_raw, sort_keys=True, ensure_ascii=False),
            ),
        )
        for kind in KINDS:
            for raw in raws(scenario, kind):
                iid = item_id(kind, str(raw["id"]))  # type: ignore[arg-type]
                text = str(raw.get("description", raw.get("text", "")))
                conn.execute(
                    "INSERT OR IGNORE INTO items"
                    " (id, course_id, kind, classroom_id, topic_id, title, text, state,"
                    " alternate_link, creation_time, update_time, due_at, content_hash,"
                    " raw_json, first_seen_at, last_seen_at, deleted_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                    (
                        iid,
                        FRENCH_COURSE_ID,
                        kind,
                        str(raw["id"]),
                        raw.get("topicId"),
                        raw.get("title"),
                        text,
                        str(raw.get("state", "PUBLISHED")),
                        raw.get("alternateLink"),
                        norm_ts(str(raw["creationTime"])),
                        norm_ts(str(raw["updateTime"])),
                        None,
                        hashlib.sha256(iid.encode()).hexdigest(),
                        json.dumps(raw, sort_keys=True, ensure_ascii=False),
                        NOW,
                        NOW,
                    ),
                )
                for material in raw.get("materials", []):
                    entry = material.get("driveFile", {}).get("driveFile", {})
                    file_id = entry.get("id")
                    if not file_id:
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO attachments"
                        " (id, item_id, kind, external_id, title, url, mime_type, drive_version,"
                        " blob_sha256, export_pdf_sha256, export_text_sha256,"
                        " status, error, attempts, updated_at, removed_at)"
                        " VALUES (?, ?, 'drive_file', ?, ?, ?, NULL, NULL,"
                        " NULL, NULL, NULL, 'pending', NULL, 0, ?, NULL)",
                        (
                            attachment_id(iid, "drive_file", str(file_id)),
                            iid,
                            str(file_id),
                            entry.get("title"),
                            f"https://drive.google.com/file/d/{file_id}/view",
                            NOW,
                        ),
                    )
    return ctx


def atts(ctx: StageContext, file_id: str) -> list[dict[str, Any]]:
    cur = ctx.store.conn.execute(
        "SELECT * FROM attachments WHERE external_id = ? ORDER BY id", (file_id,)
    )
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def item_row(ctx: StageContext, item_id_: str) -> dict[str, Any]:
    return _row_dict(ctx.store.conn, "items", "id = ?", (item_id_,))


def blob_rows(ctx: StageContext) -> int:
    row = ctx.store.conn.execute("SELECT COUNT(*) FROM blobs").fetchone()
    assert row is not None
    return int(row[0])


def with_max_download_mb(ctx: StageContext, n: int) -> StageContext:
    classroom = ctx.settings.classroom.model_copy(update={"max_download_mb": n})
    return dataclasses.replace(ctx, settings=ctx.settings.model_copy(update={"classroom": classroom}))


def item_without(ctx: StageContext, _file_id: str) -> str:
    """Siembra un ítem nuevo sin adjuntos y devuelve su id."""
    iid = item_id("coursework", "extra_same_blob")
    with ctx.store.tx() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO items"
            " (id, course_id, kind, classroom_id, topic_id, title, text, state,"
            " alternate_link, creation_time, update_time, due_at, content_hash,"
            " raw_json, first_seen_at, last_seen_at, deleted_at)"
            " VALUES (?, ?, 'coursework', 'extra_same_blob', NULL, 'Extra', '',"
            " 'PUBLISHED', NULL, ?, ?, NULL, ?, '{}', ?, ?, NULL)",
            (iid, FRENCH_COURSE_ID, NOW, NOW, hashlib.sha256(iid.encode()).hexdigest(), NOW, NOW),
        )
    return iid


def add_drive_attachment(ctx: StageContext, item_id_: str, file_id: str) -> None:
    with ctx.store.tx() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO attachments"
            " (id, item_id, kind, external_id, title, url, mime_type, drive_version,"
            " blob_sha256, export_pdf_sha256, export_text_sha256,"
            " status, error, attempts, updated_at, removed_at)"
            " VALUES (?, ?, 'drive_file', ?, 'Extra', ?, NULL, NULL,"
            " NULL, NULL, NULL, 'pending', NULL, 0, ?, NULL)",
            (
                attachment_id(item_id_, "drive_file", file_id),
                item_id_,
                file_id,
                f"https://drive.google.com/file/d/{file_id}/view",
                NOW,
            ),
        )


def test_fetch_v1_outcomes_match_fixture(tmp_path: Path) -> None:
    meta = drive_meta("v1")
    ctx = synced_ctx(tmp_path, "v1")
    with mocks("v1"):
        rep = run_fetch(ctx)
    want = {i: expected_status(m) for i, m in meta.items()}
    assert {i: {a["status"] for a in atts(ctx, i)} for i in meta} == {i: {s} for i, s in want.items()}
    assert rep.counts["fetch.checked"] == sum(len(atts(ctx, i)) for i in meta)
    assert rep.counts["fetch.downloaded"] == sum(
        len(atts(ctx, i)) for i, s in want.items() if s == "downloaded"
    )
    for i, m in meta.items():
        for a in atts(ctx, i) if want[i] == "downloaded" else []:
            assert a["drive_version"] == m["version"]
            assert (a["blob_sha256"] is None) == m["mimeType"].startswith(NATIVE_PREFIX)
    assert rep.exit_code() == (2 if set(want.values()) != {"downloaded"} or slides_ids(meta) else 0)


def test_refetch_when_drive_version_changes(tmp_path: Path) -> None:  # REVIEW FOCUS 2
    v1, v2 = drive_meta("v1"), drive_meta("v2")
    changed = {
        i
        for i in v1
        if v1[i] and v2.get(i) and v1[i]["version"] != v2[i]["version"]  # type: ignore[index]
        and expected_status(v1[i]) == "downloaded"
    }
    pdf = next(i for i in changed if v1[i]["mimeType"] == "application/pdf")  # type: ignore[index]
    ctx = synced_ctx(tmp_path, "v1")
    with mocks("v1"):
        rep1 = run_fetch(ctx)
    old = {a["id"]: a["blob_sha256"] for a in atts(ctx, pdf)}
    with mocks("v2") as r:
        rep = run_fetch(ctx)
        media = [
            c
            for c in r.calls
            if c.request.url.path.endswith(f"/files/{pdf}")
            and c.request.url.params.get("alt") == "media"
        ]
    # El mock sirve los mismos bytes en v1 y v2: el sha se conserva (content-addressed),
    # pero la versión cambia y hubo una descarga nueva por adjunto.
    assert len(media) == len(old) > 0
    assert all(
        a["blob_sha256"] is not None
        and a["blob_sha256"] == old[a["id"]]
        and a["drive_version"] == v2[pdf]["version"]  # type: ignore[index]
        for a in atts(ctx, pdf)
    )
    assert rep.counts["fetch.downloaded"] == sum(len(atts(ctx, i)) for i in changed)
    assert rep.counts["fetch.unchanged"] == rep1.counts["fetch.downloaded"] - rep.counts["fetch.downloaded"]


def test_forbidden_download_is_partial(tmp_path: Path) -> None:  # REVIEW FOCUS 4
    locked = first_id(drive_meta("v1"), can_download=False)
    ctx = synced_ctx(tmp_path, "v1")
    with mocks("v1"):
        assert run_fetch(ctx).exit_code() == 2
    assert {a["status"] for a in atts(ctx, locked)} == {"forbidden"}
    assert all(item_row(ctx, a["item_id"])["deleted_at"] is None for a in atts(ctx, locked))
    with mocks("v1") as r:
        assert run_fetch(ctx).exit_code() == 0
        assert not any(c.request.url.path.endswith(f"/files/{locked}") for c in r.calls)


def test_export_too_large_falls_back_to_text(tmp_path: Path) -> None:  # REVIEW FOCUS 4
    meta = drive_meta("v1")
    slides = first_id(meta, mime="application/vnd.google-apps.presentation")
    ctx = synced_ctx(tmp_path, "v1")
    with mocks("v1"):
        rep = run_fetch(ctx)
    rows = atts(ctx, slides)
    assert rows and all(
        a["status"] == "downloaded"
        and a["export_pdf_sha256"] is None
        and a["export_text_sha256"]
        for a in rows
    )
    # El mock rechaza todo export a PDF: cada nativo descargable pierde el PDF y suma uno.
    native_dl = [
        i
        for i, m in meta.items()
        if m and m["mimeType"].startswith(NATIVE_PREFIX) and m["capabilities"]["canDownload"]
    ]
    assert rep.exit_code() == 2
    assert rep.counts["fetch.export_pdf_skipped"] == sum(len(atts(ctx, i)) for i in native_dl)
    with mocks("v1"):
        assert run_fetch(ctx).exit_code() == 0


def test_too_large_skipped_with_link(tmp_path: Path) -> None:  # REVIEW FOCUS 4
    ctx = with_max_download_mb(synced_ctx(tmp_path, "v1"), 0)
    with mocks("v1"):
        rep = run_fetch(ctx)
    binaries = [
        a
        for i, m in drive_meta("v1").items()
        if expected_status(m) == "downloaded" and not m["mimeType"].startswith(NATIVE_PREFIX)  # type: ignore[index,union-attr]  # noqa: E501
        for a in atts(ctx, i)
    ]
    assert binaries and all(
        a["status"] == "skipped_too_large" and a["blob_sha256"] is None and a["url"].startswith("https://")
        for a in binaries
    )
    skipped = ctx.store.conn.execute(
        "SELECT COUNT(*) FROM attachments WHERE status = 'skipped_too_large'"
    ).fetchone()
    assert skipped is not None
    assert rep.exit_code() == 2 and rep.counts["fetch.skipped_too_large"] == int(skipped[0])


def test_same_file_in_two_posts_single_blob(tmp_path: Path) -> None:
    ctx = synced_ctx(tmp_path, "v1")
    b = first_id(drive_meta("v1"), mime="application/pdf", can_download=True)
    add_drive_attachment(ctx, item_without(ctx, b), b)  # segundo adjunto con el mismo fileId
    with mocks("v1"):
        run_fetch(ctx)
    rows = atts(ctx, b)
    assert len(rows) >= 2 and len({a["blob_sha256"] for a in rows}) == 1
    assert len([p for p in (tmp_path / "blobs").rglob("*") if p.is_file()]) == blob_rows(ctx)


def test_unexpected_error_bumps_attempts_and_redacts(
    tmp_path: Path, monkeypatch: Any
) -> None:
    ctx = synced_ctx(tmp_path, "v1")
    meta = drive_meta("v1")

    def _boom(self: DriveClient, file_id: str, dest: Any, max_bytes: int) -> int:
        raise httpx.ReadError("ya29.fixture boom")

    monkeypatch.setattr(DriveClient, "download", _boom)
    with mocks("v1"):
        rep = run_fetch(ctx)
    binaries = [
        a
        for i, m in meta.items()
        if m and not m["mimeType"].startswith(NATIVE_PREFIX) and m["capabilities"]["canDownload"]
        for a in atts(ctx, i)
    ]
    assert binaries and {(a["status"], a["attempts"]) for a in binaries} == {("error", 1)}
    assert rep.exit_code() == 2
    assert "ya29.fixture" not in " ".join(rep.errors)
