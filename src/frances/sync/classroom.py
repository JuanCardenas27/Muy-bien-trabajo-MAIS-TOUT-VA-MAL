"""Cliente de Google Classroom: cursos, temas y streams por updateTime desc."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

from frances.models.classroom import Course, Item, ItemKind, Topic
from frances.models.ids import content_hash, item_id
from frances.sync.google_http import GoogleApi
from frances.timeutil import BOGOTA, format_ts, norm_ts

CLASSROOM_BASE_URL = "https://classroom.googleapis.com/v1"

STREAM_PATHS: dict[ItemKind, tuple[str, str]] = {
    "coursework": ("courseWork", "courseWork"),
    "material": ("courseWorkMaterials", "courseWorkMaterial"),
    "announcement": ("announcements", "announcements"),
}

_STREAM_STATE_PARAMS: dict[ItemKind, str] = {
    "coursework": "courseWorkStates",
    "material": "courseWorkMaterialStates",
    "announcement": "announcementStates",
}


def _material_key(material: Mapping[str, Any]) -> str:
    """Clave estable de un material: id de Drive, de YouTube, URL o URL de form."""
    drive = material.get("driveFile")
    if isinstance(drive, Mapping):
        inner = drive.get("driveFile")
        if isinstance(inner, Mapping) and inner.get("id") is not None:
            return str(inner["id"])
    youtube = material.get("youtubeVideo")
    if isinstance(youtube, Mapping) and youtube.get("id") is not None:
        return str(youtube["id"])
    link = material.get("link")
    if isinstance(link, Mapping) and link.get("url") is not None:
        return str(link["url"])
    form = material.get("form")
    if isinstance(form, Mapping) and form.get("formUrl") is not None:
        return str(form["formUrl"])
    return json.dumps(dict(material), sort_keys=True, ensure_ascii=False)


def _parse_due_at(raw: Mapping[str, Any]) -> str | None:
    """Convierte dueDate/dueTime (UTC en la API) a marca normalizada o None.

    Sin ``dueTime`` se asumen las 23:59 en America/Bogota. Horas o minutos
    ausentes valen 0.
    """
    due_date = raw.get("dueDate")
    if not isinstance(due_date, Mapping):
        return None
    year = int(due_date["year"])
    month = int(due_date["month"])
    day = int(due_date["day"])
    due_time = raw.get("dueTime")
    if isinstance(due_time, Mapping):
        hours = int(due_time.get("hours", 0))
        minutes = int(due_time.get("minutes", 0))
        return format_ts(datetime(year, month, day, hours, minutes, tzinfo=UTC))
    return format_ts(datetime(year, month, day, 23, 59, tzinfo=BOGOTA))


def parse_course(raw: dict[str, Any]) -> Course:
    """Convierte el dict crudo de courses.list en un :class:`Course`."""
    return Course(
        id=str(raw["id"]),
        name=str(raw["name"]),
        section=raw.get("section"),
        state=str(raw.get("courseState", "")),
        alternate_link=raw.get("alternateLink"),
        update_time=norm_ts(str(raw["updateTime"])),
    )


def parse_item(raw: dict[str, Any], kind: ItemKind, course_id: str) -> Item:
    """Convierte el dict crudo de un stream en un :class:`Item`."""
    title: str | None = None if kind == "announcement" else raw.get("title")
    text = str(raw.get("text", "")) if kind == "announcement" else str(raw.get("description", ""))
    materials = raw.get("materials", [])
    keys = sorted(_material_key(m) for m in materials if isinstance(m, Mapping))
    return Item(
        id=item_id(kind, str(raw["id"])),
        course_id=course_id,
        kind=kind,
        classroom_id=str(raw["id"]),
        topic_id=raw.get("topicId"),
        title=title,
        text=text,
        state=str(raw.get("state", "")),
        alternate_link=raw.get("alternateLink"),
        creation_time=norm_ts(str(raw["creationTime"])),
        update_time=norm_ts(str(raw["updateTime"])),
        due_at=_parse_due_at(raw),
        content_hash=content_hash(title or "", text, *keys),
        raw_json=json.dumps(raw, sort_keys=True, ensure_ascii=False),
    )


class ClassroomClient:
    """Lectura de cursos, temas y publicaciones sobre un :class:`GoogleApi`."""

    def __init__(self, api: GoogleApi) -> None:
        self._api = api

    def list_courses(self) -> list[Course]:
        """Cursos activos visibles como estudiante."""
        return [
            parse_course(raw)
            for raw in self._api.paginate(
                "courses", {"studentId": "me", "courseStates": "ACTIVE"}, "courses"
            )
        ]

    def list_topics(self, course_id: str) -> list[Topic]:
        """Temas de un curso."""
        return [
            Topic(
                id=str(raw["topicId"]),
                course_id=course_id,
                name=str(raw["name"]),
                update_time=norm_ts(str(raw["updateTime"])),
            )
            for raw in self._api.paginate(f"courses/{course_id}/topics", {"pageSize": 100}, "topic")
        ]

    def iter_stream(self, course_id: str, stream: ItemKind) -> Iterator[dict[str, Any]]:
        """Itera un stream ordenado por updateTime descendente (solo publicados)."""
        suffix, items_key = STREAM_PATHS[stream]
        params: dict[str, object] = {
            "pageSize": 100,
            "orderBy": "updateTime desc",
            _STREAM_STATE_PARAMS[stream]: "PUBLISHED",
        }
        yield from self._api.paginate(f"courses/{course_id}/{suffix}", params, items_key)
