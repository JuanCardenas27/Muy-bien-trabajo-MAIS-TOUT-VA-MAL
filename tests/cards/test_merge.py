"""Tests de merge por `card_id`, orígenes, stale y reintento de traducción (CRD-05)."""

import sqlite3

from frances.cards.merge import merge_output, recompute_stale, retranslate_pending
from frances.cards.rules import PENDING_NOTE
from frances.db.store import Store
from frances.models import CardDraft, GenerationOutput, SheetDraft, StudySheet, card_id
from tests.cards.conftest import _mark_deleted

T1 = "2026-10-01T10:00:00.000000Z"
T2 = "2026-10-02T10:00:00.000000Z"


def _out(*fronts: str, back: str = "b", notes: str | None = None) -> GenerationOutput:
    """Salida de generación con tarjetas vocab y ficha mínima."""
    return GenerationOutput(
        cards=[
            CardDraft(kind="vocab", front_fr=front, back_es=back, notes=notes) for front in fronts
        ],
        sheet=SheetDraft(
            summary_es="resumen",
            vocab_fronts=list(fronts),
            grammar=[],
            key_phrases=[],
        ),
    )


def _cards(store: Store, kind: str | None = None) -> list[sqlite3.Row]:
    """Filas de `cards`, opcionalmente filtradas por `kind`, ordenadas por `id`."""
    store.conn.row_factory = sqlite3.Row
    if kind is None:
        rows = store.conn.execute("SELECT * FROM cards ORDER BY id").fetchall()
    else:
        rows = store.conn.execute(
            "SELECT * FROM cards WHERE kind = ? ORDER BY id", (kind,)
        ).fetchall()
    return list(rows)


def _sources(store: Store, cid: str) -> set[str]:
    """Ids de las publicaciones que sostienen la tarjeta."""
    rows = store.conn.execute(
        "SELECT item_id FROM card_sources WHERE card_id = ?", (cid,)
    ).fetchall()
    return {str(row[0]) for row in rows}


def _sheet_json(store: Store, item_id: str) -> str:
    """JSON de la ficha guardada para la publicación."""
    row = store.conn.execute("SELECT json FROM sheets WHERE item_id = ?", (item_id,)).fetchone()
    assert row is not None
    return str(row[0])


class _FakeTranslator:
    """Traductor de prueba: prefija `ES:` y registra los lotes."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate(self, texts: list[str], src: str = "fr", dst: str = "es") -> list[str | None]:
        self.calls.append(list(texts))
        return ["ES:" + text for text in texts]


def test_merge_keeps_card_and_adds_source(store: Store) -> None:
    """REVIEW FOCUS 3: tipografías distintas de la misma palabra → una tarjeta."""
    merge_output(store, "mt_A", _out("«l’école»"), "rules", "1", T1)  # noqa: RUF001
    merge_output(store, "mt_B", _out("l'école"), "rules", "1", T2)

    rows = _cards(store, kind="vocab")
    assert len(rows) == 1
    assert rows[0]["id"] == card_id("l'école", "vocab")
    assert (rows[0]["created_at"], rows[0]["updated_at"]) == (T1, T2)
    assert _sources(store, rows[0]["id"]) == {"mt_A", "mt_B"}


def test_merge_replaces_only_this_item_sources(store: Store) -> None:
    merge_output(store, "mt_A", _out("le pain", "le vin"), "rules", "1", T1)
    merge_output(store, "mt_A", _out("le pain"), "rules", "1", T2)

    assert _sources(store, card_id("le pain", "vocab")) == {"mt_A"}
    assert _sources(store, card_id("le vin", "vocab")) == set()


def test_lower_rank_does_not_overwrite(store: Store) -> None:
    merge_output(store, "mt_A", _out("le pain", back="pan (llm)"), "llm", "1", T1)
    merge_output(store, "mt_B", _out("le pain", back="pan"), "rules", "1", T2)

    row = _cards(store)[0]
    assert row["back_es"] == "pan (llm)"
    assert row["generator"] == "llm"


def test_lower_rank_fills_empty_back(store: Store) -> None:
    merge_output(store, "mt_A", _out("le pain", back=""), "llm", "1", T1)
    merge_output(store, "mt_B", _out("le pain", back="pan"), "rules", "1", T2)

    assert _cards(store)[0]["back_es"] == "pan"


def test_sheet_resolves_vocab_ids(store: Store) -> None:
    merge_output(store, "mt_A", _out("le pain"), "rules", "1", T1)

    sheet = StudySheet.model_validate_json(_sheet_json(store, "mt_A"))
    assert sheet.vocab_card_ids == [card_id("le pain", "vocab")]


def test_item_deleted_marks_cards_stale_not_deleted(store: Store) -> None:
    merge_output(store, "mt_A", _out("le pain"), "rules", "1", T1)
    _mark_deleted(store, "mt_A")

    assert recompute_stale(store) == 1
    assert _cards(store)[0]["stale"] == 1
    assert _sources(store, card_id("le pain", "vocab")) == {"mt_A"}


def test_stale_card_revives_with_live_source(store: Store) -> None:
    merge_output(store, "mt_A", _out("le pain"), "rules", "1", T1)
    _mark_deleted(store, "mt_A")
    assert recompute_stale(store) == 1

    merge_output(store, "mt_B", _out("le pain"), "rules", "1", T2)
    assert recompute_stale(store) == 0
    assert _cards(store)[0]["stale"] == 0


def test_seed_drill_never_stale(store: Store) -> None:
    cid = card_id("le vent", "drill")
    store.conn.execute(
        "INSERT INTO cards (id, kind, front_fr, back_es, phonemes, tags, generator,"
        " generator_version, stale, created_at, updated_at)"
        " VALUES (?, 'drill', 'le vent', '', '[]', '[]', 'seed', '1', 0, ?, ?)",
        (cid, T1, T1),
    )

    assert recompute_stale(store) == 0
    assert _cards(store)[0]["stale"] == 0


def test_retranslate_pending(store: Store) -> None:
    merge_output(store, "mt_A", _out("le pain", back="", notes=PENDING_NOTE), "rules", "1", T1)
    translator = _FakeTranslator()

    assert retranslate_pending(store, translator, T2) == 1
    row = _cards(store)[0]
    assert (row["back_es"], row["notes"], row["updated_at"]) == ("ES:le pain", None, T2)
