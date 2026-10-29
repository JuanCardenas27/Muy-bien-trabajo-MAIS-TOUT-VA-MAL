"""`frances run-daily`: orquestación del día y detección de cambios (OPS-02).

Corre las etapas en el orden de ``DAILY_STAGES`` (R-13). Un ``AuthError`` corta
el pipeline de inmediato y deja el resumen con ``changed`` en ``False``
(Review Focus 1 de P07); cualquier otra excepción marca su etapa como
``failed`` y el pipeline continúa. ``frances run-daily`` escribe
``.cache/daily_summary.json`` y sale con el exit code agregado: 3 si falló la
auth, 1 si alguna etapa falló, 2 si hubo parciales y 0 si todo salió bien.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import typer

from frances.cli import DataOpt, exit_with
from frances.db.store import Store  # noqa: F401  (rompe el ciclo de import stage↔db.usage)
from frances.errors import AuthError
from frances.log import get_logger, redact
from frances.stage import StageContext, StageReport, make_context
from frances.timeutil import format_ts

StageFn = Callable[[StageContext], StageReport]

DAILY_STAGES: tuple[str, ...] = (
    "sync",
    "fetch",
    "extract",
    "cards",
    "seed_drills",
    "phonemize",
    "audio",
)

CHANGE_COUNTERS: tuple[tuple[str, str], ...] = (
    ("sync", "items_upserted"),
    ("sync", "attachments_new"),
    ("fetch", "downloaded"),
    ("extract", "extracted"),
    ("cards", "generated"),
    ("cards", "retranslated"),
    ("phonemize", "updated"),
    ("audio", "done"),
)

logger = get_logger(__name__)


def default_stages() -> list[tuple[str, StageFn]]:
    """Etapas reales del día, con imports perezosos para no cargar la CLI entera."""
    from frances.audio.run import run_audio
    from frances.cards.drills import seed_drills
    from frances.cards.phonemes import run_phonemize
    from frances.cards.run import run_cards
    from frances.extract.run import run_extract
    from frances.fetch.run import run_fetch
    from frances.sync.run import run_sync

    def cards(ctx: StageContext) -> StageReport:
        llm = ctx.settings.cards.llm == "auto" and bool(ctx.env.get("LLM_BASE_URL"))
        return run_cards(ctx, llm)

    def drills(ctx: StageContext) -> StageReport:
        with ctx.store.tx() as conn:
            seeded = seed_drills(conn, format_ts(ctx.now()))
        return StageReport(stage="seed_drills", status="ok", counts={"seeded": seeded})

    def audio(ctx: StageContext) -> StageReport:
        return run_audio(ctx, max_clips=None)

    return [
        ("sync", run_sync),
        ("fetch", run_fetch),
        ("extract", run_extract),
        ("cards", cards),
        ("seed_drills", drills),
        ("phonemize", run_phonemize),
        ("audio", audio),
    ]


def run_daily(ctx: StageContext) -> list[StageReport]:
    """Corre las etapas en orden; un ``AuthError`` corta, el resto continúa."""
    reports: list[StageReport] = []
    for name, fn in default_stages():
        try:
            reports.append(fn(ctx))
        except AuthError:
            logger.warning("daily %s: AuthError", name)
            reports.append(
                StageReport(
                    stage=name, status="failed", counts={"auth_failed": 1}, errors=["AuthError"]
                )
            )
            break
        except Exception as exc:  # una etapa rota no detiene el resto
            logger.warning("daily %s: %s", name, redact(str(exc), ctx.env))
            reports.append(StageReport(stage=name, status="failed", errors=[type(exc).__name__]))
    return reports


def daily_exit_code(reports: list[StageReport]) -> int:
    """3 auth, 1 failed, 2 partial, 0 ok (en ese orden de precedencia)."""
    if any(report.counts.get("auth_failed") for report in reports):
        return 3
    if any(report.status == "failed" for report in reports):
        return 1
    if any(report.status == "partial" for report in reports):
        return 2
    return 0


def is_changed(reports: list[StageReport]) -> bool:
    """¿Hubo cambios que justifiquen un bundle nuevo? (R-09).

    Suma los contadores de ``CHANGE_COUNTERS``, que se identifican por
    ``(etapa, clave)``. Acepta la clave suelta y la calificada
    ``<etapa>.<clave>`` que publican las etapas reales (R-09). Un fallo de
    auth siempre deja el resumen en ``False``.
    """
    if any(report.counts.get("auth_failed") for report in reports):
        return False
    total = 0
    for stage, key in CHANGE_COUNTERS:
        for report in reports:
            if report.stage == stage:
                total += report.counts.get(f"{stage}.{key}", report.counts.get(key, 0))
    return total > 0


def write_summary(path: Path, reports: list[StageReport]) -> dict[str, object]:
    """Escribe el resumen JSON (sin ``errors``) de forma atómica y lo devuelve."""
    summary: dict[str, object] = {
        "changed": is_changed(reports),
        "reports": [
            {"stage": report.stage, "status": report.status, "counts": dict(report.counts)}
            for report in reports
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return summary


def _run_daily_cmd(data: Path) -> None:
    """Contexto, pipeline, resumen en ``.cache`` y exit code agregado."""
    ctx = make_context(data)
    try:
        reports = run_daily(ctx)
        write_summary(ctx.paths.cache / "daily_summary.json", reports)
    finally:
        ctx.store.close()
    raise typer.Exit(daily_exit_code(reports))


def register(app: typer.Typer) -> None:
    """Registra ``frances run-daily [--data DIR]`` (R-05)."""

    @app.command("run-daily")
    def run_daily_cmd(data: DataOpt = Path(".")) -> None:
        """Corre el pipeline diario y deja el resumen en `.cache/`."""
        exit_with(lambda: _run_daily_cmd(data))
