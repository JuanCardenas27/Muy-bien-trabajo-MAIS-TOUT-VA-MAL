"""Tests de frances.bundle.index (Task BND-02)."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from frances.bundle.index import build_index
from frances.db.store import Store
from frances.models.audio import Voice
from frances.models.bundle import ContentIndex, FileRef
from frances.paths import DataPaths

NOW = "2026-10-15T00:00:00.000000Z"

SHA_PDF = hashlib.sha256(b"%PDF-1.4 lecon").hexdigest()
SHA_PDF_EXPORT = hashlib.sha256(b"%PDF-1.4 export").hexdigest()
SHA_FORBIDDEN_EXPORT = hashlib.sha256(b"%PDF-1.4 forbidden").hexdigest()

SHEET_JSON = json.dumps(
    {
        "summary_es": "Saludos en frances.",
        "vocab_card_ids": ["c_audio"],
        "grammar": [],
        "key_phrases": [],
    }
)

VOICES = [
    Voice(
        id="fr-FR-DeniseNeural",
        label="Denise",
        engine="edge",
        age="adult",
        gender="female",
        accent="fr-FR",
    ),
    Voice(
        id="fr-FR-HenriNeural",
        label="Henri",
        engine="edge",
        age="adult",
        gender="male",
        accent="fr-FR",
    ),
    Voice(
        id="fr-FR-EloiseNeural",
        label="Eloise",
        engine="edge",
        age="child",
        gender="female",
        accent="fr-FR",
    ),
    Voice(
        id="fr-FR-Disabled",
        label="Disabled",
        engine="edge",
        age="adult",
        gender="female",
        accent="fr-FR",
        enabled=False,
    ),
]


class FakePacker:
    """Duck-typing de Packer: devuelve FileRef y anota cada ruta pedida."""

    def __init__(self) -> None:
        self.requested: list[Path] = []

    def add_file(self, path: Path, mime: str) -> FileRef:
        self.requested.append(path)
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        return FileRef(id=sha[:32], size=len(data), mime=mime, sha256=sha)


def _blob_file(root: Path, sha: str, content: bytes) -> None:
    path = root / "blobs" / sha[:2] / sha
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _seed(conn: sqlite3.Connection, root: Path) -> None:
    _blob_file(root, SHA_PDF, b"%PDF-1.4 lecon")
    _blob_file(root, SHA_PDF_EXPORT, b"%PDF-1.4 export")
    _blob_file(root, SHA_FORBIDDEN_EXPORT, b"%PDF-1.4 forbidden")
    for key in ("k-denise", "k-henri", "k-eloise"):
        audio_dir = root / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / f"{key}.mp3").write_bytes(f"mp3-{key}".encode())

    conn.execute(
        "INSERT INTO courses VALUES (?,?,?,?,?,?,?,?)",
        ("c1", "Français 1", "A1", "ACTIVE", None, NOW, 1, "{}"),
    )
    conn.execute(
        "INSERT INTO courses VALUES (?,?,?,?,?,?,?,?)",
        ("c2", "Otro curso", None, "ACTIVE", None, NOW, 0, "{}"),
    )
    conn.execute("INSERT INTO topics VALUES (?,?,?,?)", ("t1", "c1", "Salutations", NOW))
    conn.execute(
        "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "mt_new",
            "c1",
            "material",
            "cl_mt_new",
            "t1",
            "Leçon 1",
            "Bonjour à tous, voici la leçon de français.",
            "ACTIVE",
            "https://example.com/mt_new",
            "2026-10-01T00:00:00.000000Z",
            "2026-10-10T00:00:00.000000Z",
            None,
            "hash_mt",
            "{}",
            NOW,
            NOW,
            None,
        ),
    )
    conn.execute(
        "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "cw_old",
            "c1",
            "coursework",
            "cl_cw_old",
            "t1",
            "Devoir",
            "Devoir maison pour vendredi.",
            "ACTIVE",
            "https://example.com/cw_old",
            "2026-09-01T00:00:00.000000Z",
            "2026-09-05T00:00:00.000000Z",
            None,
            "hash_cw",
            "{}",
            NOW,
            NOW,
            None,
        ),
    )
    conn.execute(
        "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "cw_deleted",
            "c1",
            "coursework",
            "cl_cw_del",
            "t1",
            "Borrado",
            "Élément supprimé.",
            "ACTIVE",
            None,
            "2026-08-01T00:00:00.000000Z",
            "2026-08-02T00:00:00.000000Z",
            None,
            "hash_del",
            "{}",
            NOW,
            NOW,
            NOW,
        ),
    )
    conn.execute("INSERT INTO blobs VALUES (?,?,?,?)", (SHA_PDF, 14, "application/pdf", NOW))
    conn.execute(
        "INSERT INTO blobs VALUES (?,?,?,?)",
        (SHA_PDF_EXPORT, 15, "application/pdf", NOW),
    )
    conn.execute(
        "INSERT INTO blobs VALUES (?,?,?,?)",
        (SHA_FORBIDDEN_EXPORT, 19, "application/pdf", NOW),
    )
    conn.execute(
        "INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "at_doc",
            "mt_new",
            "drive_file",
            "ext-doc",
            "Doc Google",
            None,
            "application/vnd.google-apps.document",
            "1",
            None,
            SHA_PDF_EXPORT,
            None,
            "downloaded",
            None,
            1,
            NOW,
            None,
        ),
    )
    conn.execute(
        "INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "at_forbidden",
            "mt_new",
            "drive_file",
            "ext-forb",
            "Prohibido",
            "https://example.com/forb",
            "application/vnd.google-apps.spreadsheet",
            "1",
            None,
            SHA_FORBIDDEN_EXPORT,
            None,
            "forbidden",
            None,
            1,
            NOW,
            None,
        ),
    )
    conn.execute(
        "INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "at_pdf",
            "mt_new",
            "drive_file",
            "ext-pdf",
            "PDF Leçon",
            None,
            "application/pdf",
            "1",
            SHA_PDF,
            None,
            None,
            "downloaded",
            None,
            1,
            NOW,
            None,
        ),
    )
    conn.execute(
        "INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "at_removed",
            "mt_new",
            "drive_file",
            "ext-rem",
            "Borrado",
            None,
            "application/pdf",
            "1",
            None,
            None,
            None,
            "downloaded",
            None,
            1,
            NOW,
            NOW,
        ),
    )
    conn.execute(
        "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "c_audio",
            "vocab",
            "Bonjour",
            "Hola",
            "Bonjour, ça va ?",
            "Hola, ¿qué tal?",
            None,
            "v1|bɔ̃ʒuʁ",
            '["b", "ɔ̃", "ʒ", "u", "ʁ"]',
            '["salutations"]',
            "rules",
            "1",
            0,
            NOW,
            NOW,
        ),
    )
    conn.execute(
        "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "c_stale",
            "vocab",
            "Salut",
            "Chau",
            None,
            None,
            None,
            None,
            "[]",
            "[]",
            "rules",
            "1",
            1,
            NOW,
            NOW,
        ),
    )
    conn.execute("INSERT INTO card_sources VALUES (?,?)", ("c_audio", "mt_new"))
    conn.execute("INSERT INTO card_sources VALUES (?,?)", ("c_stale", "mt_new"))
    conn.execute("INSERT INTO sheets VALUES (?,?,?,?,?)", ("mt_new", SHEET_JSON, "llm", "1", NOW))
    conn.execute(
        "INSERT INTO audio VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "k-denise",
            "Bonjour",
            "bonjour",
            "fr-FR-DeniseNeural",
            "ms-neural",
            "1",
            "done",
            "edge",
            None,
            None,
            None,
            1,
            None,
            NOW,
        ),
    )
    conn.execute(
        "INSERT INTO audio VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "k-henri",
            "Bonjour",
            "bonjour",
            "fr-FR-HenriNeural",
            "ms-neural",
            "1",
            "done",
            "edge",
            None,
            None,
            None,
            1,
            None,
            NOW,
        ),
    )
    conn.execute(
        "INSERT INTO audio VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "k-eloise",
            "Bonjour",
            "bonjour",
            "fr-FR-EloiseNeural",
            "ms-neural",
            "1",
            "pending",
            None,
            None,
            None,
            None,
            1,
            None,
            NOW,
        ),
    )
    conn.execute("INSERT INTO card_audio VALUES (?,?,?)", ("c_audio", "front", "k-denise"))
    conn.execute("INSERT INTO card_audio VALUES (?,?,?)", ("c_audio", "front", "k-henri"))
    conn.execute("INSERT INTO card_audio VALUES (?,?,?)", ("c_audio", "front", "k-eloise"))


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    return DataPaths(root=tmp_path)


@pytest.fixture
def store(tmp_path: Path, paths: DataPaths) -> Iterator[Store]:
    s = Store.open(tmp_path / "s.db")
    _seed(s.conn, tmp_path)
    yield s
    s.close()


@pytest.fixture
def index(store: Store, paths: DataPaths) -> ContentIndex:
    return build_index(store.conn, paths, FakePacker(), VOICES, [], None, NOW)


def test_forbidden_attachment_has_no_file(index: ContentIndex) -> None:
    at = next(a for a in index.attachments if a.status == "forbidden")
    assert at.file is None and at.view_pdf is None


def test_downloaded_pdf_has_file_and_google_doc_has_view_pdf(index: ContentIndex) -> None:
    pdf = next(a for a in index.attachments if a.mime_type == "application/pdf")
    doc = next(
        a for a in index.attachments if a.mime_type == "application/vnd.google-apps.document"
    )
    assert pdf.file is not None and pdf.file.mime == "application/pdf"
    assert doc.file is None and doc.view_pdf is not None


def test_removed_attachment_excluded(index: ContentIndex) -> None:
    assert "at_removed" not in {a.id for a in index.attachments}


def test_card_audio_done_and_pending(index: ContentIndex) -> None:
    card = next(c for c in index.cards if c.id == "c_audio")
    assert [(a.field, a.voice_id) for a in card.audio] == [
        ("front", "fr-FR-DeniseNeural"),
        ("front", "fr-FR-HenriNeural"),
    ]
    assert [(p.field, p.voice_id) for p in card.audio_pending] == [("front", "fr-FR-EloiseNeural")]
    assert card.audio[0].file.mime == "audio/mpeg"


def test_deleted_item_excluded(index: ContentIndex) -> None:
    assert "cw_deleted" not in {i.id for i in index.items}


def test_excluded_course_not_in_index(index: ContentIndex) -> None:
    assert [c.id for c in index.courses] == ["c1"]


def test_items_sorted_by_update_time_desc_with_cards_and_sheet(index: ContentIndex) -> None:
    assert [i.id for i in index.items] == ["mt_new", "cw_old"]
    assert index.items[0].card_ids == ["c_audio", "c_stale"]
    assert index.items[0].has_sheet is True


def test_stale_card_included_with_flag(index: ContentIndex) -> None:
    assert next(c for c in index.cards if c.id == "c_stale").stale is True


def test_ipa_strips_version_prefix_and_parses_phonemes(index: ContentIndex) -> None:
    card = next(c for c in index.cards if c.id == "c_audio")
    assert card.ipa == "bɔ̃ʒuʁ"
    assert card.phonemes == ["b", "ɔ̃", "ʒ", "u", "ʁ"]


def test_french_item_text_lang_is_fr(index: ContentIndex) -> None:
    assert next(i for i in index.items if i.id == "mt_new").text_lang == "fr"


def test_only_enabled_voices(index: ContentIndex) -> None:
    assert "fr-FR-Disabled" not in {v.id for v in index.voices}
    assert {v.id for v in index.voices} == {
        "fr-FR-DeniseNeural",
        "fr-FR-HenriNeural",
        "fr-FR-EloiseNeural",
    }


def test_build_is_deterministic(store: Store, paths: DataPaths) -> None:
    a = build_index(store.conn, paths, FakePacker(), VOICES, [], None, NOW)
    b = build_index(store.conn, paths, FakePacker(), VOICES, [], None, NOW)
    assert a.model_dump_json() == b.model_dump_json()
