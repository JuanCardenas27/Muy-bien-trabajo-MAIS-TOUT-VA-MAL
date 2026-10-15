"""Normalización de adjuntos: materials de Classroom → Attachment (SYN-05)."""

import logging
from typing import Any

from frances.models.classroom import Attachment, AttachmentKind
from frances.models.ids import attachment_id

logger = logging.getLogger(__name__)


def _drive_file_parts(material: dict[str, Any]) -> tuple[str, str | None, str | None] | None:
    """Devuelve (external_id, title, url) del adjunto driveFile, o None si incompleto."""
    inner = material.get("driveFile")
    if not isinstance(inner, dict):
        return None
    nested = inner.get("driveFile")
    if not isinstance(nested, dict):
        return None
    external_id = nested.get("id")
    if not external_id or not isinstance(external_id, str):
        return None
    title = nested.get("title")
    url = nested.get("alternateLink")
    return (
        external_id,
        title if isinstance(title, str) else None,
        url if isinstance(url, str) else None,
    )


def _flat_parts(
    material: dict[str, Any], key: str, id_field: str, url_field: str
) -> tuple[str, str | None, str | None] | None:
    """Devuelve (external_id, title, url) de un adjunto plano, o None si incompleto."""
    inner = material.get(key)
    if not isinstance(inner, dict):
        return None
    external_id = inner.get(id_field)
    if not external_id or not isinstance(external_id, str):
        return None
    title = inner.get("title")
    url = inner.get(url_field)
    return (
        external_id,
        title if isinstance(title, str) else None,
        url if isinstance(url, str) else None,
    )


def extract_attachments(raw: dict[str, Any], item_id: str) -> list[Attachment]:
    """Normaliza ``raw["materials"]`` a una lista de Attachment sin duplicados.

    Deduplica por (kind, external_id) conservando el orden de aparición.
    Los materiales desconocidos se ignoran con un WARNING que nombra solo
    sus claves, nunca su contenido. ``mime_type`` queda siempre en None:
    el MIME real de Drive lo resuelve FET-01 (DriveClient).
    """
    materials = raw.get("materials")
    if not isinstance(materials, list):
        return []
    attachments: list[Attachment] = []
    seen: set[tuple[str, str]] = set()
    for material in materials:
        if not isinstance(material, dict):
            logger.warning("material desconocido ignorado: claves=%s", "")
            continue
        kind: AttachmentKind | None = None
        parts: tuple[str, str | None, str | None] | None = None
        if "driveFile" in material:
            kind = "drive_file"
            parts = _drive_file_parts(material)
        elif "youtubeVideo" in material:
            kind = "youtube"
            parts = _flat_parts(material, "youtubeVideo", "id", "alternateLink")
        elif "link" in material:
            kind = "link"
            parts = _flat_parts(material, "link", "url", "url")
        elif "form" in material:
            kind = "form"
            parts = _flat_parts(material, "form", "formUrl", "formUrl")
        if kind is None or parts is None:
            logger.warning("material desconocido ignorado: claves=%s", ",".join(sorted(material)))
            continue
        external_id, title, url = parts
        if (kind, external_id) in seen:
            continue
        seen.add((kind, external_id))
        attachments.append(
            Attachment(
                id=attachment_id(item_id, kind, external_id),
                item_id=item_id,
                kind=kind,
                external_id=external_id,
                title=title,
                url=url,
                mime_type=None,
            )
        )
    return attachments
