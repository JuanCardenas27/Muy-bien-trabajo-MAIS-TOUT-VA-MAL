"""Tests del repositorio de audio: pending, enlaces, cola y estados (AUD-02)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from frances.audio.cachekey import audio_request
from frances.audio.repo import (
    insert_pending,
    link_card_audio,
    mark_attempt_failed,
    mark_done,
    prune_card_audio,
    select_work,
)
from frances.db.store import Store
from frances.models.audio import Voice

NOW = "2026-10-14T15:20:24.000000Z"
NOW2 = "2026-10-15T10:00:00.000000Z"


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    s = Store.open(tmp_path / "audio.db")
    yield s
    s.close()


def _voice(voice_id: str = "fr-FR-DeniseNeural") -> Voice:
    return Voice(
        id=voice_id,
        label=voice_id,
        engine="edge",
        age="adult",
        gender="female",
        accent="Francia",
    )


def _insert_card(
    conn: sqlite3.Connection,
    card_id: str,
    created_at: str = NOW,
    front: str = "Bonjour",
) -> None:
    conn.execute(
        "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            card_id,
            "vocab",
            front,
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
            created_at,
            created_at,
        ),
    )


def _pending_row(
    conn: sqlite3.Connection,
    text: str,
    voice_id: str,
    card_id: str,
    created_at: str = NOW,
    **extra: Any,
) -> str:
    _insert_card(conn, card_id, created_at=created_at, front=text)
    req = audio_request(text, _voice(voice_id))
    insert_pending(conn, req, NOW)
    link_card_audio(conn, card_id, "front", req.cache_key)
    for key, value in extra.items():
        conn.execute(f"UPDATE audio SET {key} = ? WHERE cache_key = ?", (value, req.cache_key))
    return req.cache_key


def test_insert_pending_is_new_then_exists(store: Store) -> None:
    req = audio_request("Bonjour", _voice())
    with store.tx() as conn:
        assert insert_pending(conn, req, NOW) is True
        assert insert_pending(conn, req, NOW2) is False
        row = conn.execute(
            "SELECT text, text_norm, voice_id, status, attempts, updated_at FROM audio"
            " WHERE cache_key = ?",
            (req.cache_key,),
        ).fetchone()
    assert row[0] == "Bonjour"
    assert row[3] == "pending" and row[4] == 0 and row[5] == NOW


def test_link_card_audio_is_idempotent(store: Store) -> None:
    req = audio_request("Bonjour", _voice())
    with store.tx() as conn:
        _insert_card(conn, "c_link1")
        assert insert_pending(conn, req, NOW) is True
        link_card_audio(conn, "c_link1", "front", req.cache_key)
        link_card_audio(conn, "c_link1", "front", req.cache_key)
        count = conn.execute("SELECT count(*) FROM card_audio").fetchone()[0]
    assert count == 1


def test_prune_card_audio_removes_only_links(store: Store) -> None:
    v = _voice()
    req_a = audio_request("Bonjour", v)
    req_b = audio_request("Au revoir", v)
    with store.tx() as conn:
        _insert_card(conn, "c_prune1")
        insert_pending(conn, req_a, NOW)
        insert_pending(conn, req_b, NOW)
        link_card_audio(conn, "c_prune1", "front", req_a.cache_key)
        link_card_audio(conn, "c_prune1", "front", req_b.cache_key)
        removed = prune_card_audio(conn, "c_prune1", "front", {req_a.cache_key})
    assert removed == 1
    with store.tx():
        rows = store.conn.execute("SELECT count(*) FROM card_audio").fetchone()[0]
        audio_rows = store.conn.execute("SELECT count(*) FROM audio").fetchone()[0]
    assert rows == 1
    assert audio_rows == 2


def test_select_work_orders_newest_card_first(store: Store) -> None:
    with store.tx() as conn:
        old_key = _pending_row(
            conn, "Bonjour", "fr-FR-DeniseNeural", "c_old", created_at="2026-10-13T10:00:00.000000Z"
        )
        new_key = _pending_row(
            conn,
            "Au revoir",
            "fr-FR-DeniseNeural",
            "c_new",
            created_at="2026-10-15T10:00:00.000000Z",
        )
        rows = select_work(conn, ["ms-neural"], ["pending"], 5, None)
    assert [r.cache_key for r in rows] == [new_key, old_key]
    assert rows[0].text == "Au revoir" and rows[0].attempts == 0


def test_select_work_filters_family_status_attempts(store: Store) -> None:
    with store.tx() as conn:
        keep = _pending_row(conn, "Bonjour", "fr-FR-DeniseNeural", "c_f1")
        _pending_row(conn, "Salut", "fr-FR-DeniseNeural", "c_f2")
        _pending_row(conn, "Merci", "fr-FR-DeniseNeural", "c_f3")
        conn.execute("UPDATE audio SET status = 'done' WHERE cache_key = ?", (keep,))
        conn.execute("UPDATE audio SET attempts = 5 WHERE cache_key != ?", (keep,))
        # Sin enlace: nunca se devuelve aunque coincida familia/estado.
        lonely = audio_request("Sans lien", _voice())
        insert_pending(conn, lonely, NOW)
        rows = select_work(conn, ["ms-neural"], ["pending"], 5, None)
    assert rows == []


def test_select_work_limit(store: Store) -> None:
    with store.tx() as conn:
        _pending_row(conn, "Bonjour", "fr-FR-DeniseNeural", "c_l1", created_at=NOW)
        _pending_row(conn, "Au revoir", "fr-FR-DeniseNeural", "c_l2", created_at=NOW2)
        rows = select_work(conn, ["ms-neural"], ["pending"], 5, 1)
    assert len(rows) == 1


def test_mark_attempt_failed_reaches_terminal(store: Store) -> None:
    req = audio_request("Bonjour", _voice())
    with store.tx() as conn:
        _insert_card(conn, "c_fail1")
        insert_pending(conn, req, NOW)
    with store.tx() as conn:
        assert mark_attempt_failed(conn, req.cache_key, "boom", 3, "failed", NOW) == "pending"
    with store.tx() as conn:
        assert mark_attempt_failed(conn, req.cache_key, "boom", 3, "failed", NOW) == "pending"
    with store.tx() as conn:
        assert mark_attempt_failed(conn, req.cache_key, "boom", 3, "failed", NOW) == "failed"
        row = conn.execute(
            "SELECT attempts, status, error FROM audio WHERE cache_key = ?", (req.cache_key,)
        ).fetchone()
    assert row[0] == 3 and row[1] == "failed" and row[2] == "boom"


def test_mark_done_sets_fields(store: Store) -> None:
    req = audio_request("Bonjour", _voice())
    with store.tx() as conn:
        _insert_card(conn, "c_done1")
        insert_pending(conn, req, NOW)
        mark_done(conn, req.cache_key, "edge", "audio/abc.mp3", 1200, NOW2)
        row = conn.execute(
            "SELECT status, engine_used, path, duration_ms, updated_at FROM audio"
            " WHERE cache_key = ?",
            (req.cache_key,),
        ).fetchone()
    assert row[0] == "done"
    assert row[1] == "edge" and row[2] == "audio/abc.mp3" and row[3] == 1200
    assert row[4] == NOW2
