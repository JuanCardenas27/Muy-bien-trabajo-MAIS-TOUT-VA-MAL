"""Etapa fetch: descarga/export de adjuntos de Drive al BlobStore."""

from pathlib import Path

import httpx
import typer

from frances.cli import DataOpt, exit_with
from frances.db.usage import record_run
from frances.errors import FrancesError
from frances.fetch.blobs import BlobStore, BlobTooLargeError
from frances.fetch.drive import (
    DRIVE_BASE_URL,
    GOOGLE_NATIVE_EXPORTS,
    NATIVE_PREFIX,
    DriveClient,
    DriveMeta,
    ExportTooLargeError,
    TooLargeError,
)
from frances.fetch.repo import (
    FetchCandidate,
    insert_blob,
    list_fetch_candidates,
    mark_downloaded,
    mark_status,
)
from frances.log import redact
from frances.models.classroom import AttachmentStatus
from frances.stage import StageContext, StageReport, make_context
from frances.sync.auth import build_credentials
from frances.sync.google_http import ForbiddenError, GoogleApi, NotFoundError
from frances.timeutil import format_ts

_COUNT_KEYS = (
    "fetch.checked",
    "fetch.downloaded",
    "fetch.unchanged",
    "fetch.forbidden",
    "fetch.not_found",
    "fetch.skipped_too_large",
    "fetch.error",
    "fetch.export_pdf_skipped",
)


def _set_status(
    ctx: StageContext,
    attachment_id: str,
    status: AttachmentStatus,
    message: str | None,
    now: str,
    counts: dict[str, int],
    key: str,
    bump_attempts: bool = False,
) -> None:
    with ctx.store.tx() as conn:
        mark_status(conn, attachment_id, status, message, now, bump_attempts=bump_attempts)
    counts[key] += 1


def _fetch_binary(
    ctx: StageContext,
    drive: DriveClient,
    blobs: BlobStore,
    cand: FetchCandidate,
    meta: DriveMeta,
    max_bytes: int,
    now: str,
    counts: dict[str, int],
    errors: list[str],
) -> None:
    if meta.size is not None and meta.size > max_bytes:
        mb = ctx.settings.classroom.max_download_mb
        _set_status(
            ctx, cand.id, "skipped_too_large", f"supera el tope de {mb} MB", now, counts,
            "fetch.skipped_too_large",
        )
        return
    try:
        sha, size = blobs.put_stream(
            lambda f: drive.download(cand.external_id, f, max_bytes), max_bytes
        )
    except (TooLargeError, BlobTooLargeError):
        mb = ctx.settings.classroom.max_download_mb
        _set_status(
            ctx, cand.id, "skipped_too_large", f"supera el tope de {mb} MB", now, counts,
            "fetch.skipped_too_large",
        )
    except NotFoundError:
        _set_status(
            ctx, cand.id, "not_found", "archivo de Drive no encontrado", now, counts,
            "fetch.not_found",
        )
    except ForbiddenError:
        _set_status(
            ctx, cand.id, "forbidden", "descarga no permitida en Drive", now, counts,
            "fetch.forbidden",
        )
    except (FrancesError, httpx.HTTPError) as exc:
        message = redact(str(exc), ctx.env)
        errors.append(message)
        _set_status(ctx, cand.id, "error", message, now, counts, "fetch.error", bump_attempts=True)
    else:
        with ctx.store.tx() as conn:
            insert_blob(conn, sha, size, meta.mime_type, now)
            mark_downloaded(
                conn, cand.id, blob_sha256=sha, export_pdf_sha256=None,
                export_text_sha256=None, mime_type=meta.mime_type, title=meta.name,
                drive_version=meta.version, now=now,
            )
        counts["fetch.downloaded"] += 1


def _fetch_native(
    ctx: StageContext,
    drive: DriveClient,
    blobs: BlobStore,
    cand: FetchCandidate,
    meta: DriveMeta,
    max_bytes: int,
    now: str,
    counts: dict[str, int],
    errors: list[str],
) -> None:
    table = GOOGLE_NATIVE_EXPORTS.get(meta.mime_type)
    if table is None:
        message = f"export no soportado para {meta.mime_type}"
        errors.append(message)
        _set_status(ctx, cand.id, "error", message, now, counts, "fetch.error", bump_attempts=True)
        return
    pdf_sha: str | None = None
    text_sha: str | None = None
    for exp_mime, role in table:
        try:
            sha, size = blobs.put_stream(
                lambda f, mime=exp_mime: drive.export(cand.external_id, mime, f, max_bytes),
                max_bytes,
            )
        except ExportTooLargeError:
            if role == "view":
                counts["fetch.export_pdf_skipped"] += 1
                errors.append(f"exportación PDF demasiado grande: {cand.external_id}")
                continue
            message = f"exportación de texto demasiado grande: {cand.external_id}"
            errors.append(message)
            _set_status(
                ctx, cand.id, "error", message, now, counts, "fetch.error", bump_attempts=True
            )
            return
        except (TooLargeError, BlobTooLargeError):
            mb = ctx.settings.classroom.max_download_mb
            _set_status(
                ctx, cand.id, "skipped_too_large", f"supera el tope de {mb} MB", now, counts,
                "fetch.skipped_too_large",
            )
            return
        except NotFoundError:
            _set_status(
                ctx, cand.id, "not_found", "archivo de Drive no encontrado", now, counts,
                "fetch.not_found",
            )
            return
        except ForbiddenError:
            _set_status(
                ctx, cand.id, "forbidden", "descarga no permitida en Drive", now, counts,
                "fetch.forbidden",
            )
            return
        except (FrancesError, httpx.HTTPError) as exc:
            message = redact(str(exc), ctx.env)
            errors.append(message)
            _set_status(
                ctx, cand.id, "error", message, now, counts, "fetch.error", bump_attempts=True
            )
            return
        with ctx.store.tx() as conn:
            insert_blob(conn, sha, size, exp_mime, now)
        if role == "view":
            pdf_sha = sha
        else:
            text_sha = sha
    with ctx.store.tx() as conn:
        mark_downloaded(
            conn, cand.id, blob_sha256=None, export_pdf_sha256=pdf_sha,
            export_text_sha256=text_sha, mime_type=meta.mime_type, title=meta.name,
            drive_version=meta.version, now=now,
        )
    counts["fetch.downloaded"] += 1


def _fetch_one(
    ctx: StageContext,
    drive: DriveClient,
    blobs: BlobStore,
    cand: FetchCandidate,
    max_bytes: int,
    now: str,
    counts: dict[str, int],
    errors: list[str],
) -> None:
    counts["fetch.checked"] += 1
    try:
        meta = drive.get_metadata(cand.external_id)
    except NotFoundError:
        _set_status(
            ctx, cand.id, "not_found", "archivo de Drive no encontrado", now, counts,
            "fetch.not_found",
        )
        return
    except ForbiddenError:
        _set_status(
            ctx, cand.id, "forbidden", "descarga no permitida en Drive", now, counts,
            "fetch.forbidden",
        )
        return
    except (FrancesError, httpx.HTTPError) as exc:
        message = redact(str(exc), ctx.env)
        errors.append(message)
        _set_status(ctx, cand.id, "error", message, now, counts, "fetch.error", bump_attempts=True)
        return
    if not meta.can_download:
        _set_status(
            ctx, cand.id, "forbidden", "descarga no permitida en Drive", now, counts,
            "fetch.forbidden",
        )
        return
    if cand.status == "downloaded" and cand.drive_version == meta.version:
        counts["fetch.unchanged"] += 1
        return
    if meta.mime_type.startswith(NATIVE_PREFIX):
        _fetch_native(ctx, drive, blobs, cand, meta, max_bytes, now, counts, errors)
    else:
        _fetch_binary(ctx, drive, blobs, cand, meta, max_bytes, now, counts, errors)


def run_fetch(ctx: StageContext) -> StageReport:
    """Descarga o exporta los adjuntos pendientes; re-descarga si cambió `version`."""
    started_at = format_ts(ctx.now())
    counts = dict.fromkeys(_COUNT_KEYS, 0)
    errors: list[str] = []
    api = GoogleApi(build_credentials(ctx.env), DRIVE_BASE_URL)
    api.refresh()
    drive = DriveClient(api)
    blobs = BlobStore(ctx.paths)
    max_bytes = ctx.settings.classroom.max_download_mb * 1024 * 1024
    now = format_ts(ctx.now())
    with ctx.store.tx() as conn:
        candidates = list_fetch_candidates(conn)
    for cand in candidates:
        _fetch_one(ctx, drive, blobs, cand, max_bytes, now, counts, errors)
    partial = (
        counts["fetch.forbidden"]
        + counts["fetch.not_found"]
        + counts["fetch.skipped_too_large"]
        + counts["fetch.error"]
        + counts["fetch.export_pdf_skipped"]
    )
    report = StageReport(stage="fetch", status="partial" if partial else "ok", counts=counts,
                         errors=errors)
    with ctx.store.tx() as conn:
        record_run(conn, report, started_at, format_ts(ctx.now()))
    return report


def register(app: typer.Typer) -> None:
    """Registra `frances fetch [--data DIR]`."""

    @app.command("fetch")
    def fetch(data: DataOpt = Path(".")) -> None:
        exit_with(lambda: run_fetch(make_context(data)))
