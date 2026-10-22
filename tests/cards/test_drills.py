"""Tests de los mazos de taladro curados y automáticos (CRD-07)."""

import json
import sqlite3

import pytest

from frances.cards.drills import (
    AUTO_MAX_CARDS,
    AUTO_MIN_CARDS,
    TARGETS,
    SeedTarget,
    build_drill_decks,
    load_seed,
    seed_drills,
)
from frances.cards.phoneme_map import ESPEAK_TO_AZURE
from frances.cards.phonemes import espeak_ipa, to_azure_phonemes
from frances.models import card_id

T1 = "2026-10-10T00:00:00Z"
T2 = "2026-10-11T00:00:00Z"
T3 = "2026-10-12T00:00:00Z"


def _cards_with_phoneme(
    conn: sqlite3.Connection, phoneme: str, n: int, *, stale: int = 0
) -> list[str]:
    """Inserta `n` tarjetas `vocab` con `phonemes=[phoneme]`; devuelve sus ids."""
    base = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    ids: list[str] = []
    for index in range(n):
        front = f"mot{base + index}-{phoneme}"
        cid = card_id(front, "vocab")
        conn.execute(
            "INSERT INTO cards (id, kind, front_fr, back_es, phonemes, tags, generator,"
            " generator_version, stale, created_at, updated_at)"
            " VALUES (?, 'vocab', ?, '', ?, '[]', 'rules', '1', ?, ?, ?)",
            (cid, front, json.dumps([phoneme], ensure_ascii=False), stale, T1, T1),
        )
        ids.append(cid)
    return ids


def test_seed_has_15_entries_per_target() -> None:
    seed = load_seed()
    assert set(seed) == set(TARGETS)
    assert all(len(target.entries) >= 15 for target in seed.values())


def test_seed_idempotent(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    total = sum(len(t.entries) for t in load_seed().values())
    assert seed_drills(conn, T1) == total
    assert seed_drills(conn, T2) == 0
    row = conn.execute(
        "SELECT * FROM cards WHERE id = ?", (card_id("le vent", "drill"),)
    ).fetchone()
    assert (
        row["kind"],
        row["generator"],
        row["generator_version"],
        row["created_at"],
    ) == ("drill", "seed", "1", T1)
    assert row["updated_at"] == T1  # sin cambios no se toca updated_at (R-13)
    assert json.loads(row["tags"]) == ["taladro", "an"]


def test_seed_unchanged_keeps_updated_at_changed_refreshes(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    seed_drills(conn, T1)
    vent = card_id("le vent", "drill")
    conn.execute("UPDATE cards SET back_es = 'otra cosa' WHERE id = ?", (vent,))
    assert seed_drills(conn, T3) == 0
    rows = {row["id"]: row for row in conn.execute("SELECT * FROM cards WHERE generator = 'seed'")}
    assert rows[vent]["updated_at"] == T3
    assert rows[vent]["back_es"] != "otra cosa"
    assert rows[vent]["created_at"] == T1
    assert {row["updated_at"] for cid, row in rows.items() if cid != vent} == {T1}


def test_seed_drills_loads_seed_once(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def _counting() -> dict[str, SeedTarget]:
        nonlocal calls
        calls += 1
        return load_seed()

    monkeypatch.setattr("frances.cards.drills.load_seed", _counting)
    seed_drills(conn, T1)
    assert calls == 1


@pytest.mark.parametrize(
    ("target", "front"),
    [(t, e.front_fr) for t, s in load_seed().items() for e in s.entries],
)
def test_seed_entry_contains_target_phoneme(target: str, front: str) -> None:
    labels = set(to_azure_phonemes(espeak_ipa([front])[0]))
    assert labels & {ESPEAK_TO_AZURE[c] for c in load_seed()[target].check}


def test_curated_decks(conn: sqlite3.Connection) -> None:
    seed_drills(conn, T1)
    decks = {d.id: d for d in build_drill_decks(conn)}
    assert set(decks) >= {f"drill-{t}" for t in TARGETS}
    an = decks["drill-an"]
    assert an.curated
    assert an.phoneme == ESPEAK_TO_AZURE["ɑ̃"]  # noqa: RUF001
    assert an.title_es == "Nasal /ɑ̃/ (an, en)"  # noqa: RUF001
    assert an.card_ids[0] == card_id("le vent", "drill")


def test_curated_deck_order_follows_yaml(conn: sqlite3.Connection) -> None:
    seed_drills(conn, T1)
    r = next(d for d in build_drill_decks(conn) if d.id == "drill-r")
    assert r.card_ids == [card_id(e.front_fr, "drill") for e in load_seed()["r"].entries]


def test_auto_deck_threshold(conn: sqlite3.Connection) -> None:
    _cards_with_phoneme(conn, "ʒ", AUTO_MIN_CARDS - 1)
    assert "auto-ʒ" not in {d.id for d in build_drill_decks(conn)}
    _cards_with_phoneme(conn, "ʒ", 1)
    deck = next(d for d in build_drill_decks(conn) if d.id == "auto-ʒ")
    assert not deck.curated
    assert deck.phoneme == "ʒ"
    assert deck.title_es == "Fonema /ʒ/"
    assert len(deck.card_ids) == AUTO_MIN_CARDS


def test_auto_deck_excludes_stale_shortest_first_max_50(conn: sqlite3.Connection) -> None:
    created: list[tuple[str, str, int]] = []
    for index in range(60):
        front = "é" * ((index % 5) + 1) + f"-{index:02d}"
        cid = card_id(front, "vocab")
        stale = 1 if index < 3 else 0
        conn.execute(
            "INSERT INTO cards (id, kind, front_fr, back_es, phonemes, tags, generator,"
            " generator_version, stale, created_at, updated_at)"
            " VALUES (?, 'vocab', ?, '', ?, '[]', 'rules', '1', ?, ?, ?)",
            (cid, front, json.dumps(["ʒ"], ensure_ascii=False), stale, T1, T1),
        )
        created.append((front, cid, stale))
    deck = next(d for d in build_drill_decks(conn) if d.id == "auto-ʒ")
    assert len(deck.card_ids) == AUTO_MAX_CARDS
    stale_ids = {cid for _, cid, stale in created if stale}
    assert not stale_ids & set(deck.card_ids)
    live = [(len(front), cid) for front, cid, stale in created if not stale]
    expected = [cid for _, cid in sorted(live)[:AUTO_MAX_CARDS]]
    assert deck.card_ids == expected  # orden real: longitud asc y desempate por id
    lengths = [len(front) for front, _, _ in created]
    assert len(set(lengths)) < len(lengths)  # hay empates que resolver por id
