"""Contratos de Google Classroom (plan maestro, «Modelos Python»)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

ItemKind = Literal["coursework", "material", "announcement"]
AttachmentKind = Literal["drive_file", "link", "youtube", "form"]
AttachmentStatus = Literal[
    "pending",
    "downloaded",
    "reference",
    "skipped_too_large",
    "forbidden",
    "not_found",
    "error",
]


class Course(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    section: str | None
    state: str
    alternate_link: str | None
    update_time: str


class Topic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    course_id: str
    name: str
    update_time: str


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    course_id: str
    kind: ItemKind
    classroom_id: str
    topic_id: str | None
    title: str | None
    text: str
    state: str
    alternate_link: str | None
    creation_time: str
    update_time: str
    due_at: str | None
    content_hash: str
    raw_json: str


class Attachment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    item_id: str
    kind: AttachmentKind
    external_id: str
    title: str | None
    url: str | None
    mime_type: str | None
