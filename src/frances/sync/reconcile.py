"""Reconciliación completa: tombstones de publicaciones y adjuntos (SYN-06)."""

from __future__ import annotations

from dataclasses import dataclass, field

from frances.db.store import Store
from frances.models.classroom import Course, ItemKind
from frances.models.ids import item_id
from frances.sync.classroom import ClassroomClient
from frances.sync.repo import (
    deleted_item_ids,
    included_course_ids,
    live_item_ids,
    restore_items,
    set_course_included,
    tombstone_items,
)

STREAMS: tuple[ItemKind, ...] = ("coursework", "material", "announcement")


@dataclass
class ReconcileResult:
    """Resultado de una reconciliación completa."""

    deleted: int = 0
    restored: int = 0
    anomalies: list[str] = field(default_factory=list)


def reconcile(
    store: Store, client: ClassroomClient, courses: list[Course], now: str
) -> ReconcileResult:
    """Reconcilia el Store con el listado vivo de Classroom.

    Por curso y stream lista todo con ``iter_stream`` (fuera de la tx),
    y en una tx por stream marca ``tombstone_items(live - listado)`` y
    restaura ``restore_items(deleted & listado)``. Un listado vacío con
    ítems vivos es una anomalía y no marca nada. Al final excluye los
    cursos que ya no están listados.
    """
    result = ReconcileResult()
    for course in courses:
        for stream in STREAMS:
            listed = {
                item_id(stream, str(raw["id"])) for raw in client.iter_stream(course.id, stream)
            }
            with store.tx() as conn:
                live = live_item_ids(conn, course.id, stream)
                tombstoned = deleted_item_ids(conn, course.id, stream)
                if not listed and live:
                    result.anomalies.append(
                        f"{course.id}/{stream}: listado vacío"
                        f" con {len(live)} ítems vivos; no se marcó nada"
                    )
                    continue
                result.deleted += tombstone_items(conn, live - listed, now)
                result.restored += restore_items(conn, tombstoned & listed)
    wanted = {course.id for course in courses}
    with store.tx() as conn:
        for course_id in included_course_ids(conn) - wanted:
            set_course_included(conn, course_id, False)
    return result
