"""Etapas sync y reconcile + CLI (SYN-07).

``run_sync`` vuelca cursos, temas, publicaciones y adjuntos con watermark
por stream; ``run_reconcile`` marca tombstones de lo que ya no está en
Classroom. Un fallo de auth no escribe nada (sale con 3 vía ``exit_with``).
"""

from __future__ import annotations

from pathlib import Path

import typer

from frances.cli import DataOpt, exit_with
from frances.db.usage import record_run
from frances.log import redact
from frances.models.classroom import Course, ItemKind
from frances.stage import StageContext, StageReport, make_context
from frances.sync.auth import build_credentials
from frances.sync.classroom import CLASSROOM_BASE_URL, ClassroomClient
from frances.sync.google_http import GoogleApi
from frances.sync.reconcile import STREAMS, reconcile
from frances.sync.repo import count_attachments, upsert_course, upsert_topic
from frances.sync.streams import select_courses, sync_stream
from frances.timeutil import format_ts


def _connect(ctx: StageContext) -> ClassroomClient:
    """Autentica (refresh) y devuelve el cliente; ``AuthError`` sin escribir nada."""
    api = GoogleApi(build_credentials(ctx.env), CLASSROOM_BASE_URL)
    api.refresh()
    return ClassroomClient(api)


def run_sync(ctx: StageContext, full: bool = False) -> StageReport:
    """Sincroniza cursos incluidos y sus tres streams; siempre ``ok`` o excepción."""
    started_at = format_ts(ctx.now())
    client = _connect(ctx)
    courses = client.list_courses()
    selected = select_courses(courses, ctx.settings)
    wanted = {course.id for course in selected}
    now = format_ts(ctx.now())
    with ctx.store.tx() as conn:
        before = count_attachments(conn)
        for course in courses:
            upsert_course(conn, course, course.id in wanted, course.model_dump_json())
    for course in selected:
        topics = client.list_topics(course.id)
        with ctx.store.tx() as conn:
            for topic in topics:
                upsert_topic(conn, topic)
    seen: dict[ItemKind, int] = {stream: 0 for stream in STREAMS}
    items_seen = 0
    items_upserted = 0
    for course in selected:
        for stream in STREAMS:
            result = sync_stream(ctx.store, client, course.id, stream, now, full=full)
            seen[stream] += result.seen
            items_seen += result.seen
            items_upserted += result.upserted
    with ctx.store.tx() as conn:
        attachments_new = count_attachments(conn) - before
    finished_at = format_ts(ctx.now())
    report = StageReport(
        stage="sync",
        status="ok",
        counts={
            "sync.courses": len(selected),
            "sync.items_seen": items_seen,
            "sync.items_upserted": items_upserted,
            "sync.attachments_new": attachments_new,
            **{f"sync.seen.{stream}": seen[stream] for stream in STREAMS},
        },
    )
    with ctx.store.tx() as conn:
        record_run(conn, report, started_at, finished_at)
    return report


def run_reconcile(ctx: StageContext) -> StageReport:
    """Reconcilia el Store con Classroom; anomalías → ``partial`` (salida 2)."""
    started_at = format_ts(ctx.now())
    client = _connect(ctx)
    courses: list[Course] = select_courses(client.list_courses(), ctx.settings)
    result = reconcile(ctx.store, client, courses, format_ts(ctx.now()))
    finished_at = format_ts(ctx.now())
    report = StageReport(
        stage="reconcile",
        status="partial" if result.anomalies else "ok",
        counts={
            "reconcile.deleted": result.deleted,
            "reconcile.restored": result.restored,
            "reconcile.anomalies": len(result.anomalies),
        },
        errors=[redact(anomaly, ctx.env) for anomaly in result.anomalies],
    )
    with ctx.store.tx() as conn:
        record_run(conn, report, started_at, finished_at)
    return report


def register(app: typer.Typer) -> None:
    """Registra ``frances sync [--full]`` y ``frances reconcile``."""

    @app.command("sync")
    def sync(full: bool = typer.Option(False, "--full"), data: DataOpt = Path(".")) -> None:
        exit_with(lambda: run_sync(make_context(data), full))

    @app.command("reconcile")
    def reconcile_cmd(data: DataOpt = Path(".")) -> None:
        exit_with(lambda: run_reconcile(make_context(data)))
