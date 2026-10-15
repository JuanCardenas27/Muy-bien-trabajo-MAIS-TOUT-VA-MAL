"""Persistencia de la etapa fetch (solo SQL de fetch; DDL en migrations)."""

import sqlite3
from dataclasses import dataclass

from frances.models.classroom import AttachmentStatus


@dataclass
class FetchCandidate:
    """Adjunto drive_file pendiente de descarga, export o reintento."""

    id: str
    external_id: str
    status: AttachmentStatus
    drive_version: str | None
    attempts: int


def list_fetch_candidates(conn: sqlite3.Connection) -> list[FetchCandidate]:
    """Adjuntos `drive_file` vivos cuyo archivo hay que traer o reintentar.

    Vivos = `removed_at IS NULL` con ítem no borrado. Se incluyen `pending`,
    `downloaded` (re-fetch por `version`) y `error` con menos de 5 intentos.
    """
    rows = conn.execute(
        "SELECT a.id, a.external_id, a.status, a.drive_version, a.attempts"
        " FROM attachments AS a JOIN items AS i ON a.item_id = i.id"
        " WHERE a.kind = 'drive_file' AND a.removed_at IS NULL AND i.deleted_at IS NULL"
        " AND (a.status IN ('pending', 'downloaded')"
        " OR (a.status = 'error' AND a.attempts < 5))"
        " ORDER BY a.id"
    ).fetchall()
    return [FetchCandidate(*row) for row in rows]


def insert_blob(conn: sqlite3.Connection, sha256: str, size: int, mime_type: str, now: str) -> None:
    """Registra un blob; si el sha ya existe no hace nada."""
    conn.execute(
        "INSERT OR IGNORE INTO blobs (sha256, size, mime_type, created_at) VALUES (?, ?, ?, ?)",
        (sha256, size, mime_type, now),
    )


def mark_downloaded(
    conn: sqlite3.Connection,
    attachment_id: str,
    *,
    blob_sha256: str | None,
    export_pdf_sha256: str | None,
    export_text_sha256: str | None,
    mime_type: str,
    title: str,
    drive_version: str,
    now: str,
) -> None:
    """Marca el adjunto como descargado con sus blobs y la versión de Drive."""
    conn.execute(
        "UPDATE attachments SET status = 'downloaded', blob_sha256 = ?,"
        " export_pdf_sha256 = ?, export_text_sha256 = ?, mime_type = ?, title = ?,"
        " drive_version = ?, error = NULL, updated_at = ? WHERE id = ?",
        (
            blob_sha256,
            export_pdf_sha256,
            export_text_sha256,
            mime_type,
            title,
            drive_version,
            now,
            attachment_id,
        ),
    )


def mark_status(
    conn: sqlite3.Connection,
    attachment_id: str,
    status: AttachmentStatus,
    error: str | None,
    now: str,
    bump_attempts: bool = False,
) -> None:
    """Cambia el estado del adjunto; con `bump_attempts` suma un intento."""
    if bump_attempts:
        conn.execute(
            "UPDATE attachments SET status = ?, error = ?, updated_at = ?,"
            " attempts = attempts + 1 WHERE id = ?",
            (status, error, now, attachment_id),
        )
    else:
        conn.execute(
            "UPDATE attachments SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, error, now, attachment_id),
        )
