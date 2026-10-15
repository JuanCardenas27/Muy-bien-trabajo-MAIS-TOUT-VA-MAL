"""Helpers de siembra compartidos por las tareas CRD-01…07 (plan maestro R-02)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from frances.db.store import Store
from frances.models import Extraction, TextBlock, attachment_id
from frances.paths import DataPaths
from frances.stage import StageContext, make_context

SEED_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

_COURSE_ID = "crd01-course"
_NOW = "2026-10-01T10:00:00Z"


def _stamp(ver: str) -> str:
    """`created_at` determinista que crece con la versión numérica."""
    try:
        minute = int(ver)
    except ValueError:
        minute = 0
    return f"2026-10-01T00:{minute % 60:02d}:00Z"


def _seed(store: Store, paths: DataPaths) -> str:
    """Siembra 1 curso, ítems `mt_A` y `mt_B`, blob `SEED_SHA`, adjunto vivo
    y la extracción v1 en `paths.extraction_path(SEED_SHA, "1")`."""
    conn = store.conn
    conn.execute(
        "INSERT INTO courses (id, name, state, update_time, raw_json)"
        " VALUES (?, 'Français 1', 'ACTIVE', ?, '{}')",
        (_COURSE_ID, _NOW),
    )
    for item, classroom_ref, title, text, seen in (
        ("mt_A", "a-1", "Leçon 1", "Bonjour à tous.", "2026-10-01T10:00:00Z"),
        ("mt_B", "b-1", "Leçon 2", "Salut la classe.", "2026-10-02T10:00:00Z"),
    ):
        conn.execute(
            "INSERT INTO items (id, course_id, kind, classroom_id, title, text, state,"
            " creation_time, update_time, content_hash, raw_json, first_seen_at, last_seen_at)"
            " VALUES (?, ?, 'material', ?, ?, ?, 'PUBLISHED', ?, ?, ?, '{}', ?, ?)",
            (item, _COURSE_ID, classroom_ref, title, text, seen, seen, f"{item}-content", seen, seen),
        )
    conn.execute(
        "INSERT INTO blobs (sha256, size, mime_type, created_at) VALUES (?, 15, 'text/plain', ?)",
        (SEED_SHA, _NOW),
    )
    conn.execute(
        "INSERT INTO attachments (id, item_id, kind, external_id, title, blob_sha256, status,"
        " updated_at) VALUES (?, 'mt_A', 'drive_file', 'file-1', 'Leçon 1.txt', ?,"
        " 'downloaded', ?)",
        (attachment_id("mt_A", "drive_file", "file-1"), SEED_SHA, _NOW),
    )
    _add_extraction(store, paths, SEED_SHA, "1")
    return SEED_SHA


def _add_extraction(store: Store, paths: DataPaths, sha: str, ver: str) -> None:
    """Inserta la fila `extractions` (sha, ver) y escribe su JSON de un bloque fr."""
    block = TextBlock(text="Bonjour le monde.", lang="fr", source=f"at_{sha[:12]}")
    extraction = Extraction(
        blob_sha256=sha,
        extractor_version=ver,
        method="export_text",
        blocks=[block],
        char_count=len(block.text),
    )
    store.conn.execute(
        "INSERT INTO extractions (blob_sha256, extractor_version, method, lang, char_count,"
        " path, created_at) VALUES (?, ?, 'export_text', 'fr', ?, ?, ?)",
        (sha, ver, extraction.char_count, f"extractions/{sha}.{ver}.json", _stamp(ver)),
    )
    paths.extraction_path(sha, ver).write_text(extraction.model_dump_json(), encoding="utf-8")


def _mark_deleted(store: Store, item_id: str) -> None:
    """Marca el ítem como borrado (`deleted_at` no NULL)."""
    store.conn.execute(
        "UPDATE items SET deleted_at = ? WHERE id = ?", ("2026-10-03T00:00:00Z", item_id)
    )


def _gen(store: Store, item_id: str, input_hash: str, generator: str, version: str) -> None:
    """Inserta una fila `generations` para el ítem."""
    store.conn.execute(
        "INSERT INTO generations (item_id, input_hash, generator, generator_version, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (item_id, input_hash, generator, version, "2026-10-03T00:00:00Z"),
    )


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[StageContext]:
    """Contexto de etapa con la siembra de `_seed` aplicada."""
    context = make_context(tmp_path, {})
    try:
        _seed(context.store, context.paths)
        yield context
    finally:
        context.store.close()


@pytest.fixture
def store(ctx: StageContext) -> Store:
    return ctx.store


@pytest.fixture
def paths(ctx: StageContext) -> DataPaths:
    return ctx.paths


@pytest.fixture
def conn(store: Store) -> sqlite3.Connection:
    return store.conn
