"""Merge de ``GenerationOutput`` en el Store, stale y pendientes (CRD-05).

Las tarjetas se identifican por :func:`card_id` y nunca se borran: pierden
orígenes y quedan ``stale=1``. ``created_at`` jamás se reescribe y un generador
de rango menor no pisa el contenido de uno mayor (salvo que ``back_es`` esté
vacío).
"""

import json
from dataclasses import dataclass
from typing import Any, cast

from frances.cards.input import input_hash_for
from frances.cards.repo import (
    CardRow,
    get_card,
    pending_translation_cards,
    replace_item_sources,
    set_translation,
    upsert_card,
    upsert_generation,
    upsert_sheet,
)
from frances.cards.translate import Translator
from frances.db.store import Store
from frances.models import CardDraft, GenerationOutput, StudySheet, card_id
from frances.textnorm import display_clean

GENERATOR_RANK = {"seed": 0, "rules": 1, "llm": 2}


@dataclass
class MergeStats:
    """Cambios hechos por un :func:`merge_output`."""

    cards_created: int = 0
    cards_updated: int = 0
    sources_added: int = 0
    sources_removed: int = 0


def merge_output(
    store: Store,
    item_id: str,
    output: GenerationOutput,
    generator: str,
    version: str,
    now: str,
) -> MergeStats:
    """Funde la salida del generador en el Store, en una sola transacción."""
    stats = MergeStats()
    with store.tx() as conn:
        seen: set[str] = set()
        for draft in output.cards:
            cid = card_id(draft.front_fr, draft.kind)
            if cid in seen:  # drafts repetidos: gana el primero
                continue
            seen.add(cid)
            existing = get_card(conn, cid)
            if existing is None:
                row = CardRow(
                    id=cid,
                    kind=draft.kind,
                    front_fr=display_clean(draft.front_fr),
                    back_es=draft.back_es,
                    example_fr=draft.example_fr,
                    example_es=draft.example_es,
                    notes=draft.notes,
                    tags=_tags_json(draft.tags),
                    generator=generator,
                    generator_version=version,
                    stale=0,
                    created_at=now,
                )
                stats.cards_created += 1
            else:
                row = _merge_card(existing, draft, generator, version)
                stats.cards_updated += 1
            upsert_card(conn, row, updated_at=now)

        added, removed = replace_item_sources(conn, item_id, seen)
        stats.sources_added += added
        stats.sources_removed += removed

        sheet = StudySheet(
            item_id=item_id,
            summary_es=output.sheet.summary_es,
            vocab_card_ids=_vocab_card_ids(conn, output),
            grammar=output.sheet.grammar,
            key_phrases=output.sheet.key_phrases,
        )
        upsert_sheet(conn, sheet, generator, version, now)
        upsert_generation(conn, item_id, input_hash_for(conn, item_id), generator, version, now)
    return stats


def recompute_stale(store: Store) -> int:
    """Marca ``stale=1`` las tarjetas sin orígenes vivos; devuelve las nuevas.

    Una tarjeta sigue viva si algún ``card_sources`` apunta a un ítem con
    ``deleted_at IS NULL``; las de ``kind='drill'`` sembradas nunca caducan.
    """
    with store.tx() as conn:
        rows = conn.execute(
            "SELECT c.id, c.stale,"
            " EXISTS(SELECT 1 FROM card_sources s JOIN items i ON i.id = s.item_id"
            "        WHERE s.card_id = c.id AND i.deleted_at IS NULL),"
            " (c.kind = 'drill' AND c.generator = 'seed')"
            " FROM cards c"
        ).fetchall()
        to_stale: list[tuple[str]] = []
        to_live: list[tuple[str]] = []
        for cid, stale, live, seed in rows:
            desired = 0 if (live or seed) else 1
            if desired == stale:
                continue
            if desired == 1:
                to_stale.append((str(cid),))
            else:
                to_live.append((str(cid),))
        conn.executemany("UPDATE cards SET stale = 1 WHERE id = ?", to_stale)
        conn.executemany("UPDATE cards SET stale = 0 WHERE id = ?", to_live)
    return len(to_stale)


def retranslate_pending(store: Store, translator: Translator, now: str) -> int:
    """Traduce en un lote las tarjetas con ``PENDING_NOTE``; devuelve las resueltas."""
    pending = pending_translation_cards(store.conn)
    if not pending:
        return 0
    translated = translator.translate([front for _, front in pending])
    updated = 0
    with store.tx() as conn:
        for (cid, _), text in zip(pending, translated, strict=False):
            if text is None:
                continue
            set_translation(conn, cid, text, now)
            updated += 1
    return updated


def _merge_card(existing: CardRow, draft: CardDraft, generator: str, version: str) -> CardRow:
    """Combina la tarjeta existente con el draft sin perder ``created_at``."""
    new_rank = GENERATOR_RANK.get(generator, -1)
    old_rank = GENERATOR_RANK.get(existing.generator, -1)
    replaces = new_rank >= old_rank or existing.back_es == ""
    return CardRow(
        id=existing.id,
        kind=existing.kind,
        front_fr=existing.front_fr,
        back_es=draft.back_es if replaces else existing.back_es,
        example_fr=draft.example_fr if replaces else existing.example_fr,
        example_es=draft.example_es if replaces else existing.example_es,
        notes=draft.notes if replaces else existing.notes,
        tags=_union_tags(existing.tags, draft.tags),
        generator=generator if replaces else existing.generator,
        generator_version=version if replaces else existing.generator_version,
        stale=0,
        created_at=existing.created_at,
    )


def _tags_json(tags: list[str]) -> str:
    """JSON determinista de las etiquetas (sin repetir)."""
    return json.dumps(sorted(set(tags)), ensure_ascii=False, separators=(",", ":"))


def _union_tags(stored: str, new_tags: list[str]) -> str:
    """Unión ordenada de las etiquetas guardadas y las del draft."""
    current = cast("list[str]", json.loads(stored))
    return _tags_json([*current, *new_tags])


def _vocab_card_ids(conn: Any, output: GenerationOutput) -> list[str]:
    """Ids de vocab de la ficha que existen como tarjeta, sin repetir."""
    ids: list[str] = []
    for front in output.sheet.vocab_fronts:
        cid = card_id(front, "vocab")
        if cid not in ids and get_card(conn, cid) is not None:
            ids.append(cid)
    return ids
