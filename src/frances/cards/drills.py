"""Mazos de taladro curados (semilla) y automáticos por fonema (CRD-07).

``seed_drills`` siembra el mazo curado de ``drills_seed.yaml`` como tarjetas de
``kind='drill'`` de forma idempotente; ``build_drill_decks`` construye los
``DrillDeck`` que consume el bundle: uno curado por objetivo y uno automático por
cada etiqueta de fonema con suficientes tarjetas vivas. El SQL vive en funciones
privadas ``_q_*`` (Global Constraints): ``drills.py`` es el dueño del módulo.
"""

import importlib.resources
import json
import sqlite3
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from frances.cards.phoneme_map import ESPEAK_TO_AZURE
from frances.models import DrillDeck, card_id

#: Orden de los mazos curados (coincide con las claves de ``drills_seed.yaml``).
TARGETS: tuple[str, ...] = ("an", "on", "in", "e_vs_ɛ", "r")
#: Mínimo de tarjetas vivas con una etiqueta para generar un mazo automático.
AUTO_MIN_CARDS = 5
#: Tope de tarjetas por mazo automático.
AUTO_MAX_CARDS = 50

_SEED_FILE = "drills_seed.yaml"


class SeedEntry(BaseModel):
    """Una entrada curada: frente, traducción y par mínimo opcional."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    front_fr: str
    back_es: str
    notes: str | None = None


class SeedTarget(BaseModel):
    """Objetivo curado: fonema de espeak, etiquetas a comprobar y entradas."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phoneme: str
    check: list[str]
    title_es: str
    entries: list[SeedEntry]


def load_seed() -> dict[str, SeedTarget]:
    """Lee y valida ``drills_seed.yaml`` del paquete, preservando el orden."""
    text = (
        importlib.resources.files("frances.cards")
        .joinpath(_SEED_FILE)
        .read_text(encoding="utf-8")
    )
    document: Any = yaml.safe_load(text)
    targets: Any = document["targets"]
    return {name: SeedTarget.model_validate(raw) for name, raw in targets.items()}


def seed_drills(conn: sqlite3.Connection, now: str) -> int:
    """Siembra las tarjetas curadas y devuelve solo las filas nuevas.

    No abre transacción: la abren ``run_daily`` y ``run_bundle`` (R-13). Es
    idempotente: ``ON CONFLICT`` actualiza las tarjetas ``generator='seed'`` sin
    reescribir ``created_at`` ni pisar tarjetas de otro generador.
    """
    inserted = 0
    for target in TARGETS:
        for entry in load_seed()[target].entries:
            cid = card_id(entry.front_fr, "drill")
            if not _q_card_exists(conn, cid):
                inserted += 1
            _q_upsert_seed_card(conn, cid, entry, target, now)
    return inserted


def build_drill_decks(conn: sqlite3.Connection) -> list[DrillDeck]:
    """Mazos curados (en orden de ``TARGETS``) y automáticos (por etiqueta)."""
    seed = load_seed()
    decks: list[DrillDeck] = []
    for target in TARGETS:
        spec = seed[target]
        candidates = [card_id(entry.front_fr, "drill") for entry in spec.entries]
        decks.append(
            DrillDeck(
                id=f"drill-{target}",
                phoneme=ESPEAK_TO_AZURE[spec.phoneme],
                title_es=spec.title_es,
                card_ids=_q_existing_cards(conn, candidates),
                curated=True,
            )
        )
    decks.extend(_auto_decks(conn))
    return decks


def _auto_decks(conn: sqlite3.Connection) -> list[DrillDeck]:
    """Un mazo por etiqueta con al menos ``AUTO_MIN_CARDS`` tarjetas vivas."""
    groups: dict[str, list[tuple[int, str]]] = {}
    for cid, front, phonemes_json in _q_live_cards_with_phonemes(conn):
        labels = _parse_labels(phonemes_json)
        for label in dict.fromkeys(labels):
            groups.setdefault(label, []).append((len(front), cid))
    decks: list[DrillDeck] = []
    for label in sorted(groups):
        cards = groups[label]
        if len(cards) < AUTO_MIN_CARDS:
            continue
        ordered = sorted(cards)[:AUTO_MAX_CARDS]
        decks.append(
            DrillDeck(
                id=f"auto-{label}",
                phoneme=label,
                title_es=f"Fonema /{label}/",
                card_ids=[cid for _, cid in ordered],
                curated=False,
            )
        )
    return decks


def _parse_labels(raw: object) -> list[str]:
    """Etiquetas de la columna ``phonemes``; una fila corrupta no corta la etapa."""
    if not isinstance(raw, str):
        return []
    try:
        labels = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(labels, list):
        return []
    return [label for label in labels if isinstance(label, str)]


def _q_card_exists(conn: sqlite3.Connection, cid: str) -> bool:
    """¿Existe ya la tarjeta con ese id?"""
    return conn.execute("SELECT 1 FROM cards WHERE id = ?", (cid,)).fetchone() is not None


def _q_upsert_seed_card(
    conn: sqlite3.Connection, cid: str, entry: SeedEntry, target: str, now: str
) -> None:
    """Inserta o refresca una tarjeta curada sin tocar las de otro generador."""
    tags = json.dumps(["taladro", target], ensure_ascii=False)
    conn.execute(
        "INSERT INTO cards (id, kind, front_fr, back_es, notes, tags, generator,"
        " generator_version, created_at, updated_at)"
        " VALUES (?, 'drill', ?, ?, ?, ?, 'seed', '1', ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET back_es = excluded.back_es, notes = excluded.notes,"
        " tags = excluded.tags, updated_at = excluded.updated_at"
        " WHERE cards.generator = 'seed'",
        (cid, entry.front_fr, entry.back_es, entry.notes, tags, now, now),
    )


def _q_existing_cards(conn: sqlite3.Connection, candidates: list[str]) -> list[str]:
    """Subconjunto de ``candidates`` que existe, en el mismo orden."""
    if not candidates:
        return []
    placeholders = ",".join("?" for _ in candidates)
    rows = conn.execute(
        f"SELECT id FROM cards WHERE id IN ({placeholders})", candidates
    ).fetchall()
    present = {row[0] for row in rows}
    return [cid for cid in candidates if cid in present]


def _q_live_cards_with_phonemes(conn: sqlite3.Connection) -> list[tuple[str, str, object]]:
    """Id, frente y ``phonemes`` en crudo de las tarjetas no ``stale``."""
    rows = conn.execute("SELECT id, front_fr, phonemes FROM cards WHERE stale = 0").fetchall()
    return [(str(row[0]), str(row[1]), row[2]) for row in rows]
