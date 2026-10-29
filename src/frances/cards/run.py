"""Etapa cards: generación, upgrade a LLM, stale y pendientes (CRD-05).

Genera las publicaciones que cambiaron con el generador de reglas, sube a LLM
las que ya estaban en reglas mientras quede cupo diario (R-14), cae a reglas si
el proveedor falla y, al final, recalcula ``stale`` y reintenta traducciones
pendientes.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import typer

from frances.cards.input import build_input, items_needing_generation
from frances.cards.llm import LlmUnavailable, llm_from_env
from frances.cards.merge import merge_output, recompute_stale, retranslate_pending
from frances.cards.repo import llm_items_since
from frances.cards.rules import CardGenerator, RulesGenerator
from frances.cards.translate import Translator, translator_from_env
from frances.cli import DataOpt, exit_with
from frances.db.usage import current_month, record_run, usage_add
from frances.errors import ConfigError
from frances.log import get_logger, redact
from frances.models import GenerationInput, GenerationOutput
from frances.stage import StageContext, StageReport, make_context
from frances.timeutil import BOGOTA, format_ts, norm_ts

#: Fallos seguidos de LLM tras los que se apaga para el resto del run.
LLM_BREAKER_THRESHOLD = 2

_COUNTER_KEYS = (
    "cards.generated",
    "cards.retranslated",
    "cards.stale",
    "cards.llm",
    "cards.rules",
    "cards.llm_fallback",
)

logger = get_logger(__name__)


@dataclass
class _LlmState:
    """Estado del generador LLM durante un run (cupo y breaker)."""

    generator: CardGenerator | None
    active: bool
    consecutive_failures: int = 0


def run_cards_with(
    ctx: StageContext,
    rules: CardGenerator,
    llm: CardGenerator | None,
    translator: Translator,
) -> StageReport:
    """Corre la etapa con generadores inyectados (tests y ``run_cards``)."""
    report = StageReport(stage="cards", status="ok")
    report.counts = dict.fromkeys(_COUNTER_KEYS, 0)
    versions = {"rules": rules.version, "llm": llm.version if llm else "1"}
    must = items_needing_generation(ctx.store, False, versions)
    upgrades = [
        item
        for item in items_needing_generation(ctx.store, llm is not None, versions)
        if item not in must
    ]

    now_dt = ctx.now()
    now = format_ts(now_dt)
    month = current_month(now_dt)
    since = _midnight_bogota_utc(now_dt)
    limit = ctx.settings.cards.llm_daily_item_limit
    state = _LlmState(generator=llm, active=llm is not None)

    for item_id in must:
        inp = _build_input(ctx, item_id, report)
        if inp is None:
            continue
        generated = _generate_must(ctx, item_id, inp, rules, state, since, limit, report)
        if generated is None:
            continue
        output, generator = generated
        _persist(ctx, item_id, output, generator, versions[generator], now, month, report)

    for item_id in upgrades:
        if not state.active or state.generator is None:
            break
        if not _llm_has_room(ctx, since, limit):
            break
        inp = _build_input(ctx, item_id, report)
        if inp is None:
            continue
        try:
            output = state.generator.generate(inp)
        except LlmUnavailable as exc:
            state.consecutive_failures += 1
            logger.warning("cards llm %s: %s", item_id, redact(str(exc), ctx.env))
            if state.consecutive_failures >= LLM_BREAKER_THRESHOLD:
                state.active = False
            continue
        except Exception as exc:  # un ítem roto no corta la etapa
            _record_error(report, ctx, item_id, exc)
            continue
        state.consecutive_failures = 0
        _persist(ctx, item_id, output, "llm", state.generator.version, now, month, report)

    report.counts["cards.stale"] = recompute_stale(ctx.store)
    report.counts["cards.retranslated"] = retranslate_pending(
        ctx.store, translator, format_ts(ctx.now())
    )
    if report.errors:
        report.status = "partial"
    return report


def run_cards(ctx: StageContext, llm: bool) -> StageReport:
    """Etapa cards con el traductor y los generadores reales del entorno."""
    translator = translator_from_env(ctx.env, ctx.store, ctx.settings.translator.monthly_char_cap)
    rules = RulesGenerator(translator, vocab_max=ctx.settings.cards.vocab_per_item_max)
    llm_generator = llm_from_env(ctx.env) if llm else None
    return run_cards_with(ctx, rules, llm_generator, translator)


def _generate_must(
    ctx: StageContext,
    item_id: str,
    inp: GenerationInput,
    rules: CardGenerator,
    state: _LlmState,
    since: str,
    limit: int,
    report: StageReport,
) -> tuple[GenerationOutput, str] | None:
    """Genera un ítem obligatorio: LLM si hay cupo, si no reglas como respaldo."""
    if state.active and state.generator is not None and _llm_has_room(ctx, since, limit):
        try:
            output = state.generator.generate(inp)
        except LlmUnavailable as exc:
            report.counts["cards.llm_fallback"] += 1
            state.consecutive_failures += 1
            if state.consecutive_failures >= LLM_BREAKER_THRESHOLD:
                state.active = False
            logger.warning("cards llm %s: %s", item_id, redact(str(exc), ctx.env))
        except Exception as exc:  # un ítem roto no corta la etapa
            _record_error(report, ctx, item_id, exc)
            return None
        else:
            state.consecutive_failures = 0
            return output, "llm"
    try:
        return rules.generate(inp), "rules"
    except Exception as exc:
        _record_error(report, ctx, item_id, exc)
        return None


def _persist(
    ctx: StageContext,
    item_id: str,
    output: GenerationOutput,
    generator: str,
    version: str,
    now: str,
    month: str,
    report: StageReport,
) -> None:
    """Funde la salida en el Store, cuenta y suma la cuota ``llm_items``."""
    merge_output(ctx.store, item_id, output, generator, version, now)
    report.counts["cards.generated"] += 1
    report.counts[f"cards.{generator}"] += 1
    if generator == "llm":
        with ctx.store.tx() as conn:
            usage_add(conn, month, "llm_items", 1)


def _build_input(ctx: StageContext, item_id: str, report: StageReport) -> GenerationInput | None:
    """``build_input`` con un error por ítem que deja la etapa en ``partial``."""
    try:
        return build_input(ctx.store, ctx.paths, item_id)
    except Exception as exc:
        _record_error(report, ctx, item_id, exc)
        return None


def _record_error(report: StageReport, ctx: StageContext, item_id: str, exc: Exception) -> None:
    """Anota el ítem con error sin volcar texto del curso al reporte."""
    report.errors.append(f"{item_id}: {type(exc).__name__}")
    logger.warning("cards %s: %s", item_id, redact(str(exc), ctx.env))


def _llm_has_room(ctx: StageContext, since: str, limit: int) -> bool:
    """Queda cupo diario de LLM (R-14: se cuenta desde ``generations``)."""
    return llm_items_since(ctx.store.conn, since) < limit


def _midnight_bogota_utc(now: datetime) -> str:
    """Medianoche de hoy en America/Bogota, normalizada a UTC."""
    local = now.astimezone(BOGOTA)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return norm_ts(midnight.isoformat())


def _resolve_llm(ctx: StageContext, llm: bool | None) -> bool:
    """Resuelve ``--llm/--no-llm``; ``None`` = automático según config y entorno."""
    if llm is None:
        return ctx.settings.cards.llm == "auto" and llm_from_env(ctx.env) is not None
    if llm and llm_from_env(ctx.env) is None:
        raise ConfigError("--llm requiere LLM_BASE_URL, LLM_API_KEY y LLM_MODEL")
    return llm


def _cards_cmd(data: Path, llm: bool | None) -> StageReport:
    """Comando ``frances cards``: contexto, resolución de LLM y ``runs``."""
    ctx = make_context(data)
    try:
        enabled = _resolve_llm(ctx, llm)
        started_at = format_ts(ctx.now())
        report = run_cards(ctx, enabled)
        with ctx.store.tx() as conn:
            record_run(conn, report, started_at, format_ts(ctx.now()))
        return report
    finally:
        ctx.store.close()


def register(app: typer.Typer) -> None:
    """Registra ``frances cards [--data DIR] [--llm/--no-llm]`` (R-05)."""

    @app.command()
    def cards(
        data: DataOpt = Path("."),
        llm: bool | None = typer.Option(None, "--llm/--no-llm"),
    ) -> None:
        """Genera tarjetas y fichas de las publicaciones pendientes."""
        exit_with(lambda: _cards_cmd(data, llm))
