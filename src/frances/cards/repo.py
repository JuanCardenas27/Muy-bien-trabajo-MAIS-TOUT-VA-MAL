"""SQL de tarjetas, fichas, orígenes y generaciones (CRD-05).

Todo el SQL de las tablas ``cards``, ``card_sources``, ``sheets`` y
``generations`` vive aquí, salvo las lecturas privadas ``_q_*`` de CRD-01,
CRD-06 y CRD-07 (Global Constraints).
"""

import sqlite3
from dataclasses import dataclass
from typing import Any, cast

from frances.cards.rules import PENDING_NOTE
from frances.models import CardKind, StudySheet

_CARD_COLUMNS = (
    "id, kind, front_fr, back_es, example_fr, example_es, notes, tags,"
    " generator, generator_version, stale, created_at"
)


@dataclass(frozen=True)
class CardRow:
    """Estado de una tarjeta tal como vive en la tabla ``cards``."""

    id: str
    kind: CardKind
    front_fr: str
    back_es: str
    example_fr: str | None
    example_es: str | None
    notes: str | None
    tags: str
    generator: str
    generator_version: str
    stale: int
    created_at: str


def _row_to_card(row: tuple[Any, ...]) -> CardRow:
    """Convierte una fila de ``cards`` en :class:`CardRow`."""
    return CardRow(
        id=str(row[0]),
        kind=cast("CardKind", row[1]),
        front_fr=str(row[2]),
        back_es=str(row[3]),
        example_fr=None if row[4] is None else str(row[4]),
        example_es=None if row[5] is None else str(row[5]),
        notes=None if row[6] is None else str(row[6]),
        tags=str(row[7]),
        generator=str(row[8]),
        generator_version=str(row[9]),
        stale=int(row[10]),
        created_at=str(row[11]),
    )


def get_card(conn: sqlite3.Connection, cid: str) -> CardRow | None:
    """Tarjeta por id, o ``None`` si no existe."""
    row = conn.execute(f"SELECT {_CARD_COLUMNS} FROM cards WHERE id = ?", (cid,)).fetchone()
    if row is None:
        return None
    return _row_to_card(cast("tuple[Any, ...]", row))


def upsert_card(conn: sqlite3.Connection, card: CardRow, updated_at: str) -> None:
    """Inserta la tarjeta o actualiza su contenido sin tocar ``created_at``.

    ``front_fr`` y ``kind`` tampoco se reescriben: el id ya los fija.
    """
    conn.execute(
        "INSERT INTO cards (id, kind, front_fr, back_es, example_fr, example_es, notes,"
        " phonemes, tags, generator, generator_version, stale, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET back_es = excluded.back_es,"
        " example_fr = excluded.example_fr, example_es = excluded.example_es,"
        " notes = excluded.notes, tags = excluded.tags, generator = excluded.generator,"
        " generator_version = excluded.generator_version, stale = excluded.stale,"
        " updated_at = excluded.updated_at",
        (
            card.id,
            card.kind,
            card.front_fr,
            card.back_es,
            card.example_fr,
            card.example_es,
            card.notes,
            card.tags,
            card.generator,
            card.generator_version,
            card.stale,
            card.created_at,
            updated_at,
        ),
    )


def replace_item_sources(
    conn: sqlite3.Connection, item_id: str, card_ids: set[str]
) -> tuple[int, int]:
    """Deja los orígenes del ítem exactamente en ``card_ids``.

    Devuelve ``(añadidos, quitados)`` respecto de lo que había.
    """
    current = {
        str(row[0])
        for row in conn.execute("SELECT card_id FROM card_sources WHERE item_id = ?", (item_id,))
    }
    added = len(card_ids - current)
    removed = len(current - card_ids)
    conn.execute("DELETE FROM card_sources WHERE item_id = ?", (item_id,))
    conn.executemany(
        "INSERT INTO card_sources (card_id, item_id) VALUES (?, ?)",
        [(cid, item_id) for cid in sorted(card_ids)],
    )
    return added, removed


def upsert_sheet(
    conn: sqlite3.Connection,
    sheet: StudySheet,
    generator: str,
    generator_version: str,
    now: str,
) -> None:
    """Inserta o reemplaza la ficha de la publicación."""
    conn.execute(
        "INSERT INTO sheets (item_id, json, generator, generator_version, updated_at)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(item_id) DO UPDATE SET json = excluded.json,"
        " generator = excluded.generator, generator_version = excluded.generator_version,"
        " updated_at = excluded.updated_at",
        (sheet.item_id, sheet.model_dump_json(), generator, generator_version, now),
    )


def upsert_generation(
    conn: sqlite3.Connection,
    item_id: str,
    input_hash: str,
    generator: str,
    generator_version: str,
    now: str,
) -> None:
    """Registra la última generación del ítem (una fila por ítem)."""
    conn.execute(
        "INSERT INTO generations (item_id, input_hash, generator, generator_version, created_at)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(item_id) DO UPDATE SET input_hash = excluded.input_hash,"
        " generator = excluded.generator, generator_version = excluded.generator_version,"
        " created_at = excluded.created_at",
        (item_id, input_hash, generator, generator_version, now),
    )


def pending_translation_cards(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Tarjetas ``(id, front_fr)`` con ``back_es`` vacío y nota de pendiente."""
    rows = conn.execute(
        "SELECT id, front_fr FROM cards WHERE back_es = '' AND notes = ? ORDER BY id",
        (PENDING_NOTE,),
    ).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def set_translation(conn: sqlite3.Connection, cid: str, back_es: str, now: str) -> None:
    """Fija la traducción de una tarjeta y borra la nota de pendiente."""
    conn.execute(
        "UPDATE cards SET back_es = ?, notes = NULL, updated_at = ? WHERE id = ?",
        (back_es, now, cid),
    )


def llm_items_since(conn: sqlite3.Connection, since_utc: str) -> int:
    """Ítems generados con LLM desde ``since_utc`` (cuota diaria, R-14)."""
    row = conn.execute(
        "SELECT COUNT(*) FROM generations WHERE generator = 'llm' AND created_at >= ?",
        (since_utc,),
    ).fetchone()
    return int(row[0]) if row is not None else 0
