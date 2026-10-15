"""Tests del Store SQLite (migración 0001, tx, FK)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from frances.db.store import Store

NOW = "2026-10-14T15:20:24.000000Z"


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    s = Store.open(tmp_path / "s.db")
    yield s
    s.close()


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


def test_open_applies_migration_and_fk_on(tmp_path: Path) -> None:
    s = Store.open(tmp_path / "s.db")
    assert s.conn.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
    assert s.conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert s.conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    s.close()
    s = Store.open(tmp_path / "s.db")  # reabrir no re-migra
    assert s.conn.execute("SELECT count(*) FROM schema_version").fetchone() == (1,)
    s.close()


def test_tx_rollback_on_exception(store: Store) -> None:
    with pytest.raises(RuntimeError), store.tx():
        store.conn.execute("INSERT INTO usage VALUES ('2026-10','llm_items',1)")
        raise RuntimeError("boom")
    assert store.conn.execute("SELECT count(*) FROM usage").fetchone() == (0,)


def test_fk_violation_rejected(store: Store) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.conn.execute(
            "INSERT INTO topics VALUES (?,?,?,?)",
            ("t_x", "curso_inexistente", "Saludos", NOW),
        )
