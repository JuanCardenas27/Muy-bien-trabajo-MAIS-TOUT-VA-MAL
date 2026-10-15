"""Persistencia del sync: watermarks, cursos, temas, ítems y adjuntos (SYN-04).

Todo el SQL del subsistema sync vive aquí. Cada función recibe una
``sqlite3.Connection`` dentro de una transacción abierta por el llamador.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from frances.models.classroom import Attachment, Course, Item, ItemKind, Topic


def get_watermark(conn: sqlite3.Connection, course_id: str, stream: str) -> str | None:
    """Último ``last_update_time`` guardado para (curso, stream), o ``None``."""
    row = conn.execute(
        "SELECT last_update_time FROM watermarks WHERE course_id = ? AND stream = ?",
        (course_id, stream),
    ).fetchone()
    return str(row[0]) if row is not None else None


def set_watermark(
    conn: sqlite3.Connection, course_id: str, stream: str, last_update_time: str, now: str
) -> None:
    """Guarda ``max(actual, nuevo)``; ``last_run_at`` siempre avanza a ``now``."""
    row = conn.execute(
        "SELECT last_update_time FROM watermarks WHERE course_id = ? AND stream = ?",
        (course_id, stream),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO watermarks (course_id, stream, last_update_time, last_run_at)"
            " VALUES (?, ?, ?, ?)",
            (course_id, stream, last_update_time, now),
        )
        return
    current = str(row[0])
    best = current if current >= last_update_time else last_update_time
    conn.execute(
        "UPDATE watermarks SET last_update_time = ?, last_run_at = ?"
        " WHERE course_id = ? AND stream = ?",
        (best, now, course_id, stream),
    )


def upsert_course(conn: sqlite3.Connection, course: Course, included: bool, raw_json: str) -> None:
    """Inserta o actualiza un curso (``included`` como 0/1)."""
    conn.execute(
        "INSERT INTO courses (id, name, section, state, alternate_link,"
        " update_time, included, raw_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET name = excluded.name,"
        " section = excluded.section, state = excluded.state,"
        " alternate_link = excluded.alternate_link,"
        " update_time = excluded.update_time, included = excluded.included,"
        " raw_json = excluded.raw_json",
        (
            course.id,
            course.name,
            course.section,
            course.state,
            course.alternate_link,
            course.update_time,
            int(included),
            raw_json,
        ),
    )


def upsert_topic(conn: sqlite3.Connection, topic: Topic) -> None:
    """Inserta o actualiza un tema."""
    conn.execute(
        "INSERT INTO topics (id, course_id, name, update_time) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET course_id = excluded.course_id,"
        " name = excluded.name, update_time = excluded.update_time",
        (topic.id, topic.course_id, topic.name, topic.update_time),
    )


def upsert_item(conn: sqlite3.Connection, item: Item, now: str) -> bool:
    """Inserta o actualiza un ítem.

    Devuelve ``True`` si es nuevo o cambió ``update_time``/``content_hash``.
    Siempre conserva ``first_seen_at``, pone ``last_seen_at=now`` y limpia
    ``deleted_at``.
    """
    row = conn.execute(
        "SELECT update_time, content_hash FROM items WHERE id = ?", (item.id,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO items (id, course_id, kind, classroom_id, topic_id, title,"
            " text, state, alternate_link, creation_time, update_time, due_at,"
            " content_hash, raw_json, first_seen_at, last_seen_at, deleted_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                item.id,
                item.course_id,
                item.kind,
                item.classroom_id,
                item.topic_id,
                item.title,
                item.text,
                item.state,
                item.alternate_link,
                item.creation_time,
                item.update_time,
                item.due_at,
                item.content_hash,
                item.raw_json,
                now,
                now,
            ),
        )
        return True
    changed = str(row[0]) != item.update_time or str(row[1]) != item.content_hash
    conn.execute(
        "UPDATE items SET course_id = ?, kind = ?, classroom_id = ?, topic_id = ?,"
        " title = ?, text = ?, state = ?, alternate_link = ?, creation_time = ?,"
        " update_time = ?, due_at = ?, content_hash = ?, raw_json = ?,"
        " last_seen_at = ?, deleted_at = NULL WHERE id = ?",
        (
            item.course_id,
            item.kind,
            item.classroom_id,
            item.topic_id,
            item.title,
            item.text,
            item.state,
            item.alternate_link,
            item.creation_time,
            item.update_time,
            item.due_at,
            item.content_hash,
            item.raw_json,
            now,
            item.id,
        ),
    )
    return changed


def sync_attachments(
    conn: sqlite3.Connection, item_id: str, atts: list[Attachment], now: str
) -> int:
    """Sincroniza los adjuntos de un ítem; devuelve los insertados nuevos.

    Los nuevos ``drive_file`` quedan ``pending`` y el resto ``reference``.
    Los ausentes se marcan con ``removed_at=now``; los que reaparecen la
    recuperan a ``NULL``.
    """
    existing = {
        (str(kind), str(external)): str(aid)
        for aid, kind, external in conn.execute(
            "SELECT id, kind, external_id FROM attachments WHERE item_id = ?",
            (item_id,),
        ).fetchall()
    }
    wanted: dict[tuple[str, str], Attachment] = {}
    for att in atts:
        wanted.setdefault((att.kind, att.external_id), att)
    inserted = 0
    for (kind, _external), att in wanted.items():
        if (kind, att.external_id) not in existing:
            status = "pending" if kind == "drive_file" else "reference"
            conn.execute(
                "INSERT INTO attachments (id, item_id, kind, external_id, title,"
                " url, mime_type, drive_version, status, updated_at, removed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL)",
                (
                    att.id,
                    item_id,
                    att.kind,
                    att.external_id,
                    att.title,
                    att.url,
                    att.mime_type,
                    status,
                    now,
                ),
            )
            inserted += 1
        else:
            conn.execute(
                "UPDATE attachments SET title = ?, url = ?, mime_type = ?,"
                " updated_at = ?, removed_at = NULL WHERE id = ?",
                (att.title, att.url, att.mime_type, now, att.id),
            )
    if wanted:
        placeholders = ", ".join("?" for _ in wanted)
        params: list[str] = [now, now, item_id]
        params.extend(att.id for att in wanted.values())
        conn.execute(
            f"UPDATE attachments SET removed_at = ?, updated_at = ?"
            f" WHERE item_id = ? AND removed_at IS NULL AND id NOT IN ({placeholders})",
            params,
        )
    else:
        conn.execute(
            "UPDATE attachments SET removed_at = ?, updated_at = ?"
            " WHERE item_id = ? AND removed_at IS NULL",
            (now, now, item_id),
        )
    return inserted


def count_attachments(conn: sqlite3.Connection) -> int:
    """Número total de filas en ``attachments``."""
    row = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()
    assert row is not None
    return int(row[0])


def live_item_ids(conn: sqlite3.Connection, course_id: str, kind: ItemKind) -> set[str]:
    """Ids de ítems no borrados de (curso, kind)."""
    return {
        str(r[0])
        for r in conn.execute(
            "SELECT id FROM items WHERE course_id = ? AND kind = ? AND deleted_at IS NULL",
            (course_id, kind),
        ).fetchall()
    }


def deleted_item_ids(conn: sqlite3.Connection, course_id: str, kind: ItemKind) -> set[str]:
    """Ids de ítems borrados de (curso, kind)."""
    return {
        str(r[0])
        for r in conn.execute(
            "SELECT id FROM items WHERE course_id = ? AND kind = ? AND deleted_at IS NOT NULL",
            (course_id, kind),
        ).fetchall()
    }


def tombstone_items(conn: sqlite3.Connection, item_ids: Iterable[str], now: str) -> int:
    """Marca ítems como borrados y sus adjuntos vivos con ``removed_at=now``."""
    ids = list(item_ids)
    if not ids:
        return 0
    placeholders = ", ".join("?" for _ in ids)
    cur = conn.execute(
        f"UPDATE items SET deleted_at = ? WHERE id IN ({placeholders}) AND deleted_at IS NULL",
        [now, *ids],
    )
    marked = cur.rowcount if cur.rowcount is not None else 0
    conn.execute(
        f"UPDATE attachments SET removed_at = ?, updated_at = ?"
        f" WHERE item_id IN ({placeholders}) AND removed_at IS NULL",
        [now, now, *ids],
    )
    return int(marked)


def restore_items(conn: sqlite3.Connection, item_ids: Iterable[str]) -> int:
    """Restaura ítems borrados y sus adjuntos marcados con su mismo ``deleted_at``."""
    ids = list(item_ids)
    if not ids:
        return 0
    restored = 0
    for iid in ids:
        row = conn.execute(
            "SELECT deleted_at FROM items WHERE id = ? AND deleted_at IS NOT NULL",
            (iid,),
        ).fetchone()
        if row is None:
            continue
        tomb = row[0]
        conn.execute("UPDATE items SET deleted_at = NULL WHERE id = ?", (iid,))
        conn.execute(
            "UPDATE attachments SET removed_at = NULL WHERE item_id = ? AND removed_at = ?",
            (iid, tomb),
        )
        restored += 1
    return restored


def included_course_ids(conn: sqlite3.Connection) -> set[str]:
    """Ids de cursos con ``included`` distinto de cero."""
    return {
        str(r[0]) for r in conn.execute("SELECT id FROM courses WHERE included != 0").fetchall()
    }


def set_course_included(conn: sqlite3.Connection, course_id: str, included: bool) -> None:
    """Activa o desactiva un curso en el sync."""
    conn.execute("UPDATE courses SET included = ? WHERE id = ?", (int(included), course_id))
