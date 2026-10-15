"""Ensamblado de `GenerationInput` por publicación (CRD-01).

Los bloques del ítem van primero (`source="item"`), luego los de la
extracción vigente de cada adjunto vivo en orden de `attachments.id`.
La versión vigente de un blob es la fila de `extractions` con mayor
`created_at` (empate: mayor `extractor_version`; R-26). El hash del
input se calcula solo desde la DB, así `input_hash_for` y `build_input`
coinciden siempre.
"""

import sqlite3
from collections.abc import Mapping
from typing import Any, cast

from frances.db.store import Store
from frances.extract.lang import split_blocks
from frances.models import Extraction, GenerationInput
from frances.models.ids import content_hash
from frances.paths import DataPaths


def build_input(store: Store, paths: DataPaths, item_id: str) -> GenerationInput:
    """Arma el `GenerationInput` del ítem: bloques del ítem + adjuntos vivos."""
    conn = store.conn
    item = _q_item(conn, item_id)
    if item is None:
        raise KeyError(item_id)
    title: str | None = item[1]
    blocks = split_blocks((title or "") + "\n\n" + str(item[2]), source="item")
    versions = _current_versions(conn, str(item[0]))
    for sha, ver in versions:
        extraction = Extraction.model_validate_json(
            paths.extraction_path(sha, ver).read_text(encoding="utf-8")
        )
        blocks.extend(extraction.blocks)
    parts = [str(item[3])]
    parts.extend(f"{sha}:{ver}" for sha, ver in versions)
    return GenerationInput(
        item_id=item_id, title=title, blocks=blocks, input_hash=content_hash(*parts)
    )


def input_hash_for(conn: sqlite3.Connection, item_id: str) -> str:
    """Huella estable del input del ítem, solo desde la DB (sin leer archivos)."""
    item = _q_item(conn, item_id)
    if item is None:
        raise KeyError(item_id)
    parts = [str(item[3])]
    parts.extend(f"{sha}:{ver}" for sha, ver in _current_versions(conn, str(item[0])))
    return content_hash(*parts)


def items_needing_generation(
    store: Store, llm_available: bool, generator_versions: Mapping[str, str]
) -> list[str]:
    """Ítems vivos que requieren (re)generación, `first_seen_at` descendente.

    Uno necesita si no tiene fila en `generations`, o su `input_hash` difiere
    del vigente, o la versión de su generador difiere de `generator_versions`,
    o hay LLM disponible y su último generador fue `rules`.
    """
    conn = store.conn
    return [
        str(row[0])
        for row in _q_live_items(conn)
        if _needs_generation(conn, str(row[0]), llm_available, generator_versions)
    ]


def _q_item(conn: sqlite3.Connection, item_id: str) -> tuple[Any, ...] | None:
    """Fila del ítem `(id, title, text, content_hash)`, o `None` si no existe."""
    row = conn.execute(
        "SELECT id, title, text, content_hash FROM items WHERE id = ?", (item_id,)
    ).fetchone()
    return cast("tuple[Any, ...] | None", row)


def _q_live_items(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    """Ítems vivos, `first_seen_at` descendente."""
    rows = conn.execute(
        "SELECT id FROM items WHERE deleted_at IS NULL ORDER BY first_seen_at DESC, id"
    ).fetchall()
    return list(rows)


def _q_live_attachments(conn: sqlite3.Connection, item_id: str) -> list[tuple[Any, ...]]:
    """Adjuntos vivos y descargados del ítem `(id, sha)` en orden de `attachments.id`;
    el blob efectivo es `export_text_sha256` si no es NULL, si no `blob_sha256`."""
    rows = conn.execute(
        "SELECT id, COALESCE(export_text_sha256, blob_sha256) AS sha FROM attachments"
        " WHERE item_id = ? AND removed_at IS NULL AND status = 'downloaded' ORDER BY id",
        (item_id,),
    ).fetchall()
    return list(rows)


def _q_current_version(conn: sqlite3.Connection, sha: str) -> str | None:
    """Versión vigente de un blob (R-26): mayor `created_at`, empate por mayor
    `extractor_version`; `None` si el blob no tiene extracción."""
    row = conn.execute(
        "SELECT extractor_version FROM extractions WHERE blob_sha256 = ?"
        " ORDER BY created_at DESC, extractor_version DESC LIMIT 1",
        (sha,),
    ).fetchone()
    return str(row[0]) if row is not None else None


def _q_generation(conn: sqlite3.Connection, item_id: str) -> tuple[Any, ...] | None:
    """Fila `generations` `(input_hash, generator, generator_version)` del ítem,
    o `None` si nunca se generó."""
    row = conn.execute(
        "SELECT input_hash, generator, generator_version FROM generations WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    return cast("tuple[Any, ...] | None", row)


def _current_versions(conn: sqlite3.Connection, item_id: str) -> list[tuple[str, str]]:
    """Pares `(sha, ver)` vigentes de los adjuntos vivos, en orden de `attachments.id`."""
    versions: list[tuple[str, str]] = []
    for row in _q_live_attachments(conn, item_id):
        sha = row[1]
        if sha is None:
            continue
        ver = _q_current_version(conn, str(sha))
        if ver is not None:
            versions.append((str(sha), ver))
    return versions


def _needs_generation(
    conn: sqlite3.Connection,
    item_id: str,
    llm_available: bool,
    generator_versions: Mapping[str, str],
) -> bool:
    """¿La fila `generations` del ítem quedó atrás del input o de las versiones?"""
    generation = _q_generation(conn, item_id)
    if generation is None:
        return True
    if str(generation[0]) != input_hash_for(conn, item_id):
        return True
    generator = str(generation[1])
    expected = generator_versions.get(generator)
    if expected is not None and str(generation[2]) != expected:
        return True
    return llm_available and generator == "rules"
