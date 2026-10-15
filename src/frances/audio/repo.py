"""Persistencia de la cola de audio: `audio` + `card_audio` (AUD-02)."""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from frances.models.audio import AudioRequest, EngineFamily


@dataclass(frozen=True)
class AudioRow:
    cache_key: str
    text: str
    text_norm: str
    voice_id: str
    family: EngineFamily
    family_version: str
    status: str
    attempts: int


def insert_pending(conn: sqlite3.Connection, req: AudioRequest, now: str) -> bool:
    """Inserta una fila `pending`; si la clave ya existe no la toca."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO audio"
        " (cache_key, text, text_norm, voice_id, family, family_version,"
        " status, attempts, updated_at)"
        " VALUES (?,?,?,?,?,?, 'pending', 0, ?)",
        (
            req.cache_key,
            req.text,
            req.text_norm,
            req.voice_id,
            req.family,
            req.family_version,
            now,
        ),
    )
    return cur.rowcount == 1


def link_card_audio(conn: sqlite3.Connection, card_id: str, field: str, cache_key: str) -> None:
    """Enlaza tarjeta→clip; idempotente."""
    conn.execute(
        "INSERT OR IGNORE INTO card_audio (card_id, field, cache_key) VALUES (?,?,?)",
        (card_id, field, cache_key),
    )


def prune_card_audio(conn: sqlite3.Connection, card_id: str, field: str, keep: set[str]) -> int:
    """Borra los enlaces fuera de `keep`; nunca borra filas `audio`."""
    if not keep:
        cur = conn.execute(
            "DELETE FROM card_audio WHERE card_id = ? AND field = ?", (card_id, field)
        )
        return cur.rowcount
    placeholders = ",".join("?" for _ in keep)
    cur = conn.execute(
        f"DELETE FROM card_audio WHERE card_id = ? AND field = ?"
        f" AND cache_key NOT IN ({placeholders})",
        (card_id, field, *sorted(keep)),
    )
    return cur.rowcount


def select_work(
    conn: sqlite3.Connection,
    families: Sequence[EngineFamily],
    statuses: Sequence[str],
    max_attempts: int,
    limit: int | None,
) -> list[AudioRow]:
    """Cola de trabajo: solo filas con enlace, newest-card-first."""
    if not families or not statuses:
        return []
    fam_ph = ",".join("?" for _ in families)
    st_ph = ",".join("?" for _ in statuses)
    sql = (
        "SELECT audio.cache_key, audio.text, audio.text_norm, audio.voice_id,"
        " audio.family, audio.family_version, audio.status, audio.attempts"
        " FROM audio"
        " JOIN card_audio ON card_audio.cache_key = audio.cache_key"
        " JOIN cards ON cards.id = card_audio.card_id"
        f" WHERE audio.family IN ({fam_ph}) AND audio.status IN ({st_ph})"
        " AND audio.attempts < ?"
        " GROUP BY audio.cache_key"
        " ORDER BY MAX(cards.created_at) DESC, audio.cache_key ASC"
    )
    params: list[str | int] = [*families, *statuses, max_attempts]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [
        AudioRow(
            cache_key=r[0],
            text=r[1],
            text_norm=r[2],
            voice_id=r[3],
            family=r[4],
            family_version=r[5],
            status=r[6],
            attempts=r[7],
        )
        for r in rows
    ]


def mark_done(
    conn: sqlite3.Connection,
    cache_key: str,
    engine_used: str,
    path: str,
    duration_ms: int,
    now: str,
) -> None:
    """Marca un clip como sintetizado y post-procesado."""
    conn.execute(
        "UPDATE audio SET status = 'done', engine_used = ?, path = ?,"
        " duration_ms = ?, updated_at = ? WHERE cache_key = ?",
        (engine_used, path, duration_ms, now, cache_key),
    )


def mark_attempt_failed(
    conn: sqlite3.Connection,
    cache_key: str,
    error: str,
    max_attempts: int,
    terminal: Literal["failed"],
    now: str,
) -> str:
    """Suma un intento; devuelve `terminal` si llegó al tope, si no `pending`."""
    row = conn.execute("SELECT attempts FROM audio WHERE cache_key = ?", (cache_key,)).fetchone()
    current = int(row[0]) if row is not None else 0
    new_attempts = current + 1
    new_status = terminal if new_attempts >= max_attempts else "pending"
    conn.execute(
        "UPDATE audio SET attempts = ?, status = ?, error = ?, updated_at = ? WHERE cache_key = ?",
        (new_attempts, new_status, error, now, cache_key),
    )
    return new_status
