"""Contratos del bundle publicado: manifiesto e índice (plan maestro)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from frances.models.audio import VoiceAge
from frances.models.classroom import AttachmentKind, AttachmentStatus, ItemKind
from frances.models.content import CardKind, Lang, StudySheet


class FileRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    size: int
    mime: str
    sha256: str


class KdfParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["PBKDF2"]
    hash: Literal["SHA-256"]
    iterations: int
    salt: str


class BundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["FRB1"]
    kdf: KdfParams
    check: str
    index: FileRef
    created_at: str


class CourseOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    section: str | None


class TopicOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    course_id: str
    name: str


class ItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    course_id: str
    kind: ItemKind
    topic_id: str | None
    title: str | None
    text: str
    text_lang: Lang
    created_at: str
    updated_at: str
    first_seen_at: str
    due_at: str | None
    alternate_link: str | None
    attachment_ids: list[str]
    card_ids: list[str]
    has_sheet: bool


class AttachmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    item_id: str
    kind: AttachmentKind
    title: str | None
    url: str | None
    mime_type: str | None
    status: AttachmentStatus
    file: FileRef | None
    view_pdf: FileRef | None


class AudioRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: Literal["front", "example"]
    voice_id: str
    file: FileRef


class AudioPending(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: Literal["front", "example"]
    voice_id: str


class CardOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: CardKind
    front_fr: str
    back_es: str
    example_fr: str | None
    example_es: str | None
    notes: str | None
    ipa: str | None
    phonemes: list[str]
    tags: list[str]
    stale: bool
    source_item_ids: list[str]
    audio: list[AudioRef]
    audio_pending: list[AudioPending]


class VoiceOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    age: VoiceAge
    gender: Literal["female", "male"]
    accent: str


class DrillDeck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    phoneme: str
    title_es: str
    card_ids: list[str]
    curated: bool


class SpeechCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    region: str
    key: str
    locale: Literal["fr-FR"] = "fr-FR"


class ContentIndex(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    generated_at: str
    courses: list[CourseOut]
    topics: list[TopicOut]
    items: list[ItemOut]
    attachments: list[AttachmentOut]
    cards: list[CardOut]
    sheets: list[StudySheet]
    voices: list[VoiceOut]
    drills: list[DrillDeck]
    speech: SpeechCredentials | None
