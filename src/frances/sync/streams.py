"""Sync incremental por stream con watermark normalizado (SYN-04).

La red pagina dentro de una única transacción ``store.tx()``
(``BEGIN IMMEDIATE`` de un solo proceso): si la red falla a mitad del
stream, la transacción revierte y el watermark no avanza. Excepción
aceptada por R-26.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from frances.config import Settings
from frances.db.store import Store
from frances.models.classroom import Course, ItemKind
from frances.sync.attachments import extract_attachments
from frances.sync.classroom import ClassroomClient, parse_item
from frances.sync.repo import (
    get_watermark,
    set_watermark,
    sync_attachments,
    upsert_item,
)
from frances.timeutil import format_ts, norm_ts, parse_ts


@dataclass
class StreamResult:
    """Resultado de sincronizar un stream."""

    seen: int
    upserted: int
    stopped_at_watermark: bool
    max_update_time: str | None


def select_courses(courses: list[Course], settings: Settings) -> list[Course]:
    """Cursos ``ACTIVE`` que pasan el filtro (ids explícitos o regex de nombre)."""
    wanted = settings.classroom.include_course_ids
    pattern = settings.classroom.include_name_regex
    selected: list[Course] = []
    for course in courses:
        if course.state != "ACTIVE":
            continue
        if wanted:
            if course.id in wanted:
                selected.append(course)
        elif re.search(pattern, course.name):
            selected.append(course)
    return selected


def sync_stream(
    store: Store,
    client: ClassroomClient,
    course_id: str,
    stream: ItemKind,
    now: str,
    overlap: timedelta = timedelta(minutes=10),
    full: bool = False,
) -> StreamResult:
    """Sincroniza un stream hasta el watermark (menos ``overlap``).

    Umbral = ``format_ts(parse_ts(watermark) - overlap)``; por cada raw,
    ``ut = norm_ts(raw["updateTime"])``; si no es ``full`` y hay umbral y
    ``ut < threshold``: ``stopped_at_watermark=True`` y ``break`` sin pedir
    la página siguiente. El watermark avanza al final solo si se vio algo.
    """
    seen = 0
    upserted = 0
    stopped = False
    max_update_time: str | None = None
    with store.tx() as conn:
        watermark = get_watermark(conn, course_id, stream)
        threshold: str | None = None
        if watermark is not None:
            threshold = format_ts(parse_ts(watermark) - overlap)
        for raw in client.iter_stream(course_id, stream):
            update_time = norm_ts(str(raw["updateTime"]))
            if not full and threshold is not None and update_time < threshold:
                stopped = True
                break
            seen += 1
            if max_update_time is None or update_time > max_update_time:
                max_update_time = update_time
            item = parse_item(raw, stream, course_id)
            if upsert_item(conn, item, now):
                upserted += 1
            atts = extract_attachments(raw, item.id)
            sync_attachments(conn, item.id, atts, now)
        if max_update_time is not None:
            set_watermark(conn, course_id, stream, max_update_time, now)
    return StreamResult(
        seen=seen,
        upserted=upserted,
        stopped_at_watermark=stopped,
        max_update_time=max_update_time,
    )
