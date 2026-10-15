"""Tests de dump_sql / restore_sql deterministas."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from frances.db.dump import dump_sql, restore_sql
from frances.db.store import Store

NOW = "2026-10-14T15:20:24.000000Z"


@pytest.fixture
def populated_store(tmp_path: Path) -> Iterator[Store]:
    s = Store.open(tmp_path / "p.db")
    with s.tx() as conn:
        conn.execute(
            "INSERT INTO courses VALUES (?,?,?,?,?,?,?,?)",
            ("c1", "Français", None, "ACTIVE", None, NOW, 1, "{}"),
        )
        conn.execute(
            "INSERT INTO topics VALUES (?,?,?,?)", ("t1", "c1", "Salutations", NOW)
        )
        conn.execute(
            "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "mt_1",
                "c1",
                "material",
                "1",
                "t1",
                "Leçon",
                "",
                "ACTIVE",
                None,
                NOW,
                NOW,
                None,
                "abc",
                "{}",
                NOW,
                NOW,
                None,
            ),
        )
        conn.execute(
            "INSERT INTO blobs VALUES (?,?,?,?)", ("ab" * 32, 10, "application/pdf", NOW)
        )
        conn.execute(
            "INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "at_1",
                "mt_1",
                "drive_file",
                "abc",
                "doc",
                None,
                "application/pdf",
                "1",
                "ab" * 32,
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
            "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "c_0123456789abcdef",
                "vocab",
                "Bonjour",
                "Hola",
                None,
                None,
                None,
                None,
                "[]",
                "[]",
                "rules",
                "1",
                0,
                NOW,
                NOW,
            ),
        )
        conn.execute(
            "INSERT INTO runs (stage, started_at, finished_at, status, stats)"
            " VALUES (?,?,?,?,?)",
            ("sync", NOW, NOW, "ok", '{"counts":{},"errors":[]}'),
        )
    yield s
    s.close()


def test_dump_is_order_independent(tmp_path: Path) -> None:
    rows = [
        ("2026-10", "llm_items", 3),
        ("2026-09", "azure_tts_chars", 10),
        ("2026-10", "azure_tts_chars", 5),
    ]
    a, b = Store.open(tmp_path / "a.db"), Store.open(tmp_path / "b.db")
    try:
        for s, rs in ((a, rows), (b, list(reversed(rows)))):
            with s.tx() as conn:
                conn.executemany("INSERT INTO usage VALUES (?,?,?)", rs)
        assert dump_sql(a).splitlines()[0] == "-- frances state dump v1"
        assert dump_sql(a) == dump_sql(b) and dump_sql(a).endswith("\n")
    finally:
        a.close()
        b.close()


def test_dump_literals(tmp_path: Path) -> None:
    s = Store.open(tmp_path / "s.db")
    try:
        with s.tx() as conn:
            conn.execute(
                "INSERT INTO audio VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "k1",
                    "l'été",
                    "l'été",
                    "fr-FR-DeniseNeural",
                    "edge",
                    "1",
                    "done",
                    "edge",
                    "audio/k1.mp3",
                    1000,
                    0.1,
                    1,
                    None,
                    NOW,
                ),
            )
        audio_lines = [
            line
            for line in dump_sql(s).splitlines()
            if line.startswith("INSERT INTO audio")
        ]
        assert len(audio_lines) == 1
        assert "NULL" in audio_lines[0]
        assert "0.1" in audio_lines[0]
        assert "'l''été'" in audio_lines[0]
    finally:
        s.close()


def test_restore_roundtrip(tmp_path: Path, populated_store: Store) -> None:
    sql = dump_sql(populated_store)
    restored = restore_sql(sql, tmp_path / "r.db")
    try:
        assert dump_sql(restored) == sql
    finally:
        restored.close()
