"""Repositorio SQLite de la etapa extract (SQL solo aquí; EXT-04)."""

import sqlite3
from dataclasses import dataclass

from frances.models import Extraction, Lang

_NATIVE_PREFIX = "application/vnd.google-apps."


@dataclass(frozen=True)
class ExtractCandidate:
    """Blob pendiente de extracción para una versión del extractor."""

    attachment_id: str
    sha256: str
    mime_type: str
    native: bool


def list_extract_candidates(
    conn: sqlite3.Connection, extractor_version: str
) -> list[ExtractCandidate]:
    """Adjuntos `downloaded` vivos sin fila en `extractions` para (sha, versión).

    Nativo → `export_text_sha256`; si no → `blob_sha256`. Un sha repetido
    aparece una sola vez.
    """
    rows = conn.execute(
        "SELECT a.id, a.mime_type, a.blob_sha256, a.export_text_sha256"
        " FROM attachments a JOIN items i ON i.id = a.item_id"
        " WHERE a.status = 'downloaded' AND a.removed_at IS NULL AND i.deleted_at IS NULL"
        " ORDER BY a.id"
    ).fetchall()
    done = {
        str(row[0])
        for row in conn.execute(
            "SELECT blob_sha256 FROM extractions WHERE extractor_version = ?",
            (extractor_version,),
        ).fetchall()
    }
    candidates: list[ExtractCandidate] = []
    seen: set[str] = set()
    for row in rows:
        mime_type = str(row[1])
        blob_sha = None if row[2] is None else str(row[2])
        export_text_sha = None if row[3] is None else str(row[3])
        native = mime_type.startswith(_NATIVE_PREFIX)
        sha = export_text_sha if native else blob_sha
        if sha is None or sha in done or sha in seen:
            continue
        seen.add(sha)
        candidates.append(
            ExtractCandidate(
                attachment_id=str(row[0]), sha256=sha, mime_type=mime_type, native=native
            )
        )
    return candidates


def insert_extraction(
    conn: sqlite3.Connection, ex: Extraction, lang: Lang, path: str, now: str
) -> None:
    """Inserta la fila de `extractions` para (blob_sha256, extractor_version)."""
    conn.execute(
        "INSERT INTO extractions (blob_sha256, extractor_version, method, lang, char_count,"
        " path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ex.blob_sha256, ex.extractor_version, ex.method, lang, ex.char_count, path, now),
    )
