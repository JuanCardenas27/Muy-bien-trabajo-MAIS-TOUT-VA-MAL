"""Tests de la etapa extract idempotente por (blob, versión) (EXT-04)."""

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from frances.extract import run
from frances.extract.pdf import PageText
from frances.extract.run import run_extract
from frances.fetch.blobs import BlobStore
from frances.models import Extraction
from frances.stage import StageContext, make_context

FIXED = datetime(2026, 10, 14, 10, 17, tzinfo=UTC)
NOW = "2026-10-14T10:17:00.000000Z"
FAKE_ENV = {
    "GOOGLE_CLIENT_ID": "cid",
    "GOOGLE_CLIENT_SECRET": "csecret",
    "GOOGLE_REFRESH_TOKEN": "rt",
}
NATIVE_PREFIX = "application/vnd.google-apps."
PDF_TEXT = "Je suis étudiant à l'université de Bogotá."
OCR_TEXT = "Les enfants chantent une chanson."

ATT_COLUMNS = (
    "INSERT INTO attachments (id, item_id, kind, external_id, title, url, mime_type,"
    " drive_version, blob_sha256, export_pdf_sha256, export_text_sha256, status, error,"
    " attempts, updated_at, removed_at)"
)


class _Fakes:
    """Dobles de `extract_pdf` y `ocr_file` con contadores de llamadas."""

    def __init__(self) -> None:
        self.pdf_calls = 0
        self.ocr_calls = 0
        self.pdf_raises: Exception | None = None

    def extract_pdf(self, path: Path, ocr: object, min_chars: int = 40, dpi: int = 200) -> list:
        self.pdf_calls += 1
        if self.pdf_raises is not None:
            raise self.pdf_raises
        return [PageText(1, PDF_TEXT, "pdf_text")]

    def ocr_file(self, path: Path) -> str:
        self.ocr_calls += 1
        return OCR_TEXT


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> _Fakes:
    doubles = _Fakes()
    monkeypatch.setattr(run, "extract_pdf", doubles.extract_pdf)
    monkeypatch.setattr(run, "ocr_file", doubles.ocr_file)
    return doubles


def make_ctx(tmp_path: Path) -> StageContext:
    ctx = make_context(tmp_path, FAKE_ENV)
    return replace(ctx, now=lambda: FIXED)


def ctx_with_blobs(tmp_path: Path, mime_by_key: dict[str, str]) -> StageContext:
    """Contexto con un ítem y adjuntos `downloaded` cuyos blobs ya están en el almacén."""
    ctx = make_ctx(tmp_path)
    ctx.store.conn.row_factory = sqlite3.Row
    with ctx.store.tx() as conn:
        conn.execute(
            "INSERT INTO courses (id, name, section, state, alternate_link, update_time,"
            " included, raw_json) VALUES ('c1', 'Cours', NULL, 'ACTIVE', NULL, ?, 1, '{}')",
            (NOW,),
        )
        conn.execute(
            "INSERT INTO items (id, course_id, kind, classroom_id, topic_id, title, text, state,"
            " alternate_link, creation_time, update_time, due_at, content_hash, raw_json,"
            " first_seen_at, last_seen_at, deleted_at)"
            " VALUES ('i1', 'c1', 'coursework', 'cw1', NULL, NULL, '', 'PUBLISHED', NULL,"
            " ?, ?, NULL, 'h', '{}', ?, ?, NULL)",
            (NOW, NOW, NOW, NOW),
        )
    blobs = BlobStore(ctx.paths)
    for key, mime in mime_by_key.items():
        native = mime.startswith(NATIVE_PREFIX)
        blob_sha = None if native else blobs.put_bytes(f"contenido {key}".encode("utf-8"))[0]
        export_text = blobs.put_bytes(f"texte exporté {key}".encode("utf-8"))[0] if native else None
        with ctx.store.tx() as conn:
            conn.execute(
                f"{ATT_COLUMNS} VALUES (?, 'i1', 'drive_file', ?, 'Titre',"
                f" 'https://drive.example/f{key}', ?, '1', ?, NULL, ?, 'downloaded', NULL, 0, ?,"
                " NULL)",
                (f"att_{key}", f"file_{key}", mime, blob_sha, export_text, NOW),
            )
    return ctx


def attachment_of(ctx: StageContext, key: str) -> str:
    row = ctx.store.conn.execute(
        "SELECT id FROM attachments WHERE external_id = ?", (f"file_{key}",)
    ).fetchone()
    assert row is not None
    return str(row[0])


def sha_of(ctx: StageContext, key: str) -> str:
    row = ctx.store.conn.execute(
        "SELECT mime_type, blob_sha256, export_text_sha256 FROM attachments WHERE external_id = ?",
        (f"file_{key}",),
    ).fetchone()
    assert row is not None
    mime, blob_sha, export_text = row
    native = str(mime).startswith(NATIVE_PREFIX)
    sha = export_text if native else blob_sha
    assert sha is not None
    return str(sha)


def extraction_row(ctx: StageContext, key: str) -> sqlite3.Row:
    row = ctx.store.conn.execute(
        "SELECT * FROM extractions WHERE blob_sha256 = ?", (sha_of(ctx, key),)
    ).fetchone()
    assert row is not None
    return row


def methods(ctx: StageContext) -> dict[str, str]:
    rows = ctx.store.conn.execute(
        "SELECT a.external_id, e.method FROM attachments a"
        " JOIN extractions e ON e.blob_sha256 = COALESCE(a.export_text_sha256, a.blob_sha256)"
    ).fetchall()
    return {str(external).removeprefix("file_"): str(method) for external, method in rows}


def test_dispatch_by_mime(tmp_path: Path, fakes: _Fakes) -> None:
    ctx = ctx_with_blobs(
        tmp_path,
        {
            "pdf": "application/pdf",
            "png": "image/png",
            "txt": "text/plain",
            "doc": "application/vnd.google-apps.document",
        },
    )
    rep = run_extract(ctx)
    assert rep.exit_code() == 0 and rep.counts["extract.extracted"] == 4
    assert methods(ctx) == {
        "pdf": "pdf_text",
        "png": "image_ocr",
        "txt": "plain",
        "doc": "export_text",
    }
    assert (fakes.pdf_calls, fakes.ocr_calls) == (1, 1)


def test_row_and_file_agree(tmp_path: Path, fakes: _Fakes) -> None:
    ctx = ctx_with_blobs(tmp_path, {"pdf": "application/pdf"})
    run_extract(ctx)
    row = extraction_row(ctx, "pdf")
    path = ctx.paths.extraction_path(row["blob_sha256"], "1")
    ex = Extraction.model_validate_json(path.read_text(encoding="utf-8"))
    assert row["path"] == str(path.relative_to(ctx.paths.root))
    assert row["extractor_version"] == "1"
    assert ex.char_count == row["char_count"] == sum(len(b.text) for b in ex.blocks)
    assert row["lang"] == "fr"
    assert ex.blocks[0].source == attachment_of(ctx, "pdf") and ex.blocks[0].page == 1
    assert path.read_text(encoding="utf-8") == json.dumps(
        ex.model_dump(), sort_keys=True, indent=0, ensure_ascii=False
    )


def test_extractor_error_is_partial_and_redacted(tmp_path: Path, fakes: _Fakes) -> None:
    fakes.pdf_raises = RuntimeError(f"boom en {tmp_path}/secret.pdf")
    ctx = ctx_with_blobs(tmp_path, {"pdf": "application/pdf", "txt": "text/plain"})
    rep = run_extract(ctx)
    assert rep.status == "partial" and rep.exit_code() == 2
    assert rep.counts["extract.extracted"] == 1
    assert str(tmp_path) not in " ".join(rep.errors)


def test_extract_idempotent(tmp_path: Path, fakes: _Fakes) -> None:
    ctx = ctx_with_blobs(tmp_path, {"pdf": "application/pdf"})
    rep1 = run_extract(ctx)
    assert rep1.counts["extract.extracted"] == 1
    rep2 = run_extract(ctx)
    assert rep2.counts["extract.extracted"] == 0 and fakes.pdf_calls == 1


def test_same_blob_in_two_attachments_extracted_once(tmp_path: Path, fakes: _Fakes) -> None:
    ctx = ctx_with_blobs(tmp_path, {"pdf": "application/pdf"})
    sha = sha_of(ctx, "pdf")
    with ctx.store.tx() as conn:
        conn.execute(
            f"{ATT_COLUMNS} VALUES ('att_pdf2', 'i1', 'drive_file', 'file_pdf2', 'Titre',"
            " 'https://drive.example/f2', 'application/pdf', '1', ?, NULL, NULL, 'downloaded',"
            " NULL, 0, ?, NULL)",
            (sha, NOW),
        )
    rep = run_extract(ctx)
    assert rep.counts["extract.extracted"] == 1 and fakes.pdf_calls == 1


def test_unsupported_mime_is_skipped_not_partial(tmp_path: Path, fakes: _Fakes) -> None:
    ctx = ctx_with_blobs(tmp_path, {"zip": "application/zip", "txt": "text/plain"})
    rep = run_extract(ctx)
    assert rep.status == "ok" and rep.exit_code() == 0
    assert rep.counts["extract.skipped_unsupported"] == 1
    assert rep.counts["extract.extracted"] == 1
