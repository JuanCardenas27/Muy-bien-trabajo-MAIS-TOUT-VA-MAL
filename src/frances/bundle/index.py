"""Constructor del ContentIndex desde el Store (Task BND-02).

Módulo de SQL de solo lectura: ninguna sentencia escribe en la base.
Reglas fijas del plan maestro: cursos incluidos por id, temas por
(course_id, name), ítems vivos por update_time DESC, adjuntos vivos por
(item_id, id), tarjetas por id (incluye stale), audio done/pending por
(field, voice_id), sheets de los ítems vivos, voces habilitadas.
"""

import json
import sqlite3

from frances.bundle.pack import FileRef as PackFileRef
from frances.bundle.pack import Packer
from frances.extract.lang import detect_lang
from frances.models.audio import Voice
from frances.models.bundle import (
    AttachmentOut,
    AudioPending,
    AudioRef,
    CardOut,
    ContentIndex,
    CourseOut,
    DrillDeck,
    FileRef,
    ItemOut,
    SpeechCredentials,
    TopicOut,
    VoiceOut,
)
from frances.models.content import StudySheet
from frances.paths import DataPaths

_AUDIT_MIME = "application/pdf"
_AUDIO_MIME = "audio/mpeg"


def _file_ref(ref: PackFileRef) -> FileRef:
    """Convierte el FileRef provisional de BND-03 al contrato canónico de FND-02."""
    return FileRef(id=ref.id, size=ref.size, mime=ref.mime, sha256=ref.sha256)


def _courses(cur: sqlite3.Cursor) -> list[CourseOut]:
    rows = cur.execute(
        "SELECT id, name, section FROM courses WHERE included = 1 ORDER BY id"
    ).fetchall()
    return [CourseOut(id=r[0], name=r[1], section=r[2]) for r in rows]


def _topics(cur: sqlite3.Cursor) -> list[TopicOut]:
    rows = cur.execute(
        "SELECT t.id, t.course_id, t.name FROM topics t"
        " JOIN courses c ON c.id = t.course_id"
        " WHERE c.included = 1 ORDER BY t.course_id, t.name"
    ).fetchall()
    return [TopicOut(id=r[0], course_id=r[1], name=r[2]) for r in rows]


def _attachments(cur: sqlite3.Cursor, paths: DataPaths, packer: Packer) -> list[AttachmentOut]:
    rows = cur.execute(
        "SELECT a.id, a.item_id, a.kind, a.title, a.url, a.mime_type, a.status,"
        " a.blob_sha256, a.export_pdf_sha256, b.mime_type AS blob_mime"
        " FROM attachments a"
        " JOIN items i ON i.id = a.item_id"
        " JOIN courses c ON c.id = i.course_id"
        " LEFT JOIN blobs b ON b.sha256 = a.blob_sha256"
        " WHERE a.removed_at IS NULL AND i.deleted_at IS NULL AND c.included = 1"
        " ORDER BY a.item_id, a.id"
    ).fetchall()
    out: list[AttachmentOut] = []
    for r in rows:
        file: FileRef | None = None
        view_pdf: FileRef | None = None
        if r[6] == "downloaded":
            if r[7] is not None:
                file = _file_ref(packer.add_file(paths.blob_path(r[7]), r[9]))
            if r[8] is not None:
                view_pdf = _file_ref(packer.add_file(paths.blob_path(r[8]), _AUDIT_MIME))
        out.append(
            AttachmentOut(
                id=r[0],
                item_id=r[1],
                kind=r[2],
                title=r[3],
                url=r[4],
                mime_type=r[5],
                status=r[6],
                file=file,
                view_pdf=view_pdf,
            )
        )
    return out


def _card_audio(
    cur: sqlite3.Cursor, paths: DataPaths, packer: Packer
) -> tuple[dict[str, list[AudioRef]], dict[str, list[AudioPending]]]:
    done: dict[str, list[AudioRef]] = {}
    pending: dict[str, list[AudioPending]] = {}
    rows = cur.execute(
        "SELECT ca.card_id, ca.field, au.voice_id, au.status, au.cache_key"
        " FROM card_audio ca JOIN audio au ON au.cache_key = ca.cache_key"
        " ORDER BY ca.card_id, ca.field, au.voice_id, ca.cache_key"
    ).fetchall()
    for card_id, field, voice_id, status, cache_key in rows:
        if status == "done":
            done.setdefault(card_id, []).append(
                AudioRef(
                    field=field,
                    voice_id=voice_id,
                    file=_file_ref(packer.add_file(paths.audio_path(cache_key), _AUDIO_MIME)),
                )
            )
        else:
            pending.setdefault(card_id, []).append(AudioPending(field=field, voice_id=voice_id))
    for refs in done.values():
        refs.sort(key=lambda a: (a.field, a.voice_id))
    for pendings in pending.values():
        pendings.sort(key=lambda p: (p.field, p.voice_id))
    return done, pending


def build_index(
    conn: sqlite3.Connection,
    paths: DataPaths,
    packer: Packer,
    voices: list[Voice],
    drills: list[DrillDeck],
    speech: SpeechCredentials | None,
    now: str,
) -> ContentIndex:
    """Construye el ContentIndex leyendo el Store y empaquetando blobs vivos."""
    cur = conn.cursor()

    courses = _courses(cur)
    topics = _topics(cur)

    item_rows = cur.execute(
        "SELECT id, course_id, kind, topic_id, title, text, creation_time, update_time,"
        " first_seen_at, due_at, alternate_link FROM items"
        " WHERE deleted_at IS NULL"
        " AND course_id IN (SELECT id FROM courses WHERE included = 1)"
        " ORDER BY update_time DESC, id"
    ).fetchall()
    item_ids = {r[0] for r in item_rows}

    sources = cur.execute(
        "SELECT card_id, item_id FROM card_sources ORDER BY card_id, item_id"
    ).fetchall()
    cards_by_item: dict[str, list[str]] = {}
    items_by_card: dict[str, list[str]] = {}
    for card_id, item_id in sources:
        items_by_card.setdefault(card_id, []).append(item_id)
        if item_id in item_ids:
            cards_by_item.setdefault(item_id, []).append(card_id)

    att_rows = cur.execute(
        "SELECT item_id, id FROM attachments"
        " WHERE removed_at IS NULL"
        " AND item_id IN (SELECT id FROM items WHERE deleted_at IS NULL"
        " AND course_id IN (SELECT id FROM courses WHERE included = 1))"
        " ORDER BY item_id, id"
    ).fetchall()
    att_ids_by_item: dict[str, list[str]] = {}
    for item_id, att_id in att_rows:
        att_ids_by_item.setdefault(item_id, []).append(att_id)

    sheet_ids = {
        r[0]
        for r in cur.execute(
            "SELECT item_id FROM sheets"
            " WHERE item_id IN (SELECT id FROM items WHERE deleted_at IS NULL"
            " AND course_id IN (SELECT id FROM courses WHERE included = 1))"
        ).fetchall()
    }

    attachments = _attachments(cur, paths, packer)
    audio_done, audio_pending = _card_audio(cur, paths, packer)

    items = [
        ItemOut(
            id=r[0],
            course_id=r[1],
            kind=r[2],
            topic_id=r[3],
            title=r[4],
            text=r[5],
            text_lang=detect_lang(r[5]),
            created_at=r[6],
            updated_at=r[7],
            first_seen_at=r[8],
            due_at=r[9],
            alternate_link=r[10],
            attachment_ids=att_ids_by_item.get(r[0], []),
            card_ids=cards_by_item.get(r[0], []),
            has_sheet=r[0] in sheet_ids,
        )
        for r in item_rows
    ]

    cards = [
        CardOut(
            id=r[0],
            kind=r[1],
            front_fr=r[2],
            back_es=r[3],
            example_fr=r[4],
            example_es=r[5],
            notes=r[6],
            ipa=r[7].split("|", 1)[-1] if r[7] is not None else None,
            phonemes=json.loads(r[8]),
            tags=json.loads(r[9]),
            stale=bool(r[10]),
            source_item_ids=items_by_card.get(r[0], []),
            audio=audio_done.get(r[0], []),
            audio_pending=audio_pending.get(r[0], []),
        )
        for r in cur.execute(
            "SELECT id, kind, front_fr, back_es, example_fr, example_es, notes, ipa,"
            " phonemes, tags, stale FROM cards ORDER BY id"
        ).fetchall()
    ]

    sheets = [
        StudySheet(item_id=r[0], **json.loads(r[1]))
        for r in cur.execute(
            "SELECT item_id, json FROM sheets"
            " WHERE item_id IN (SELECT id FROM items WHERE deleted_at IS NULL"
            " AND course_id IN (SELECT id FROM courses WHERE included = 1))"
            " ORDER BY item_id"
        ).fetchall()
    ]

    voices_out = [
        VoiceOut(id=v.id, label=v.label, age=v.age, gender=v.gender, accent=v.accent)
        for v in voices
        if v.enabled
    ]

    return ContentIndex(
        schema_version=1,
        generated_at=now,
        courses=courses,
        topics=topics,
        items=items,
        attachments=attachments,
        cards=cards,
        sheets=sheets,
        voices=voices_out,
        drills=list(drills),
        speech=speech,
    )
