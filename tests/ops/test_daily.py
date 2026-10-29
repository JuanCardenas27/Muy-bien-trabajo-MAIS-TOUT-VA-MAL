"""Tests de `frances run-daily`: orquestación, exit codes y cambios (OPS-02)."""

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Literal, cast

import pytest

from frances.errors import AuthError
from frances.ops import daily
from frances.ops.daily import (
    DAILY_STAGES,
    daily_exit_code,
    default_stages,
    is_changed,
    run_daily,
    write_summary,
)
from frances.stage import StageContext, StageReport, make_context

Status = Literal["ok", "partial", "failed"]


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[StageContext]:
    """Contexto de etapa sobre un repo de datos vacío."""
    context = make_context(tmp_path, {})
    try:
        yield context
    finally:
        context.store.close()


def stage(
    name: str,
    status: Status = "ok",
    counts: dict[str, int] | None = None,
    exc: Exception | None = None,
    calls: list[str] | None = None,
) -> tuple[str, Callable[[StageContext], StageReport]]:
    """Etapa falsa que anota su nombre y, opcionalmente, falla."""

    def fn(ctx: StageContext) -> StageReport:
        if calls is not None:
            calls.append(name)
        if exc is not None:
            raise exc
        return StageReport(stage=name, status=status, counts=counts or {})

    return (name, fn)


def test_runs_stages_in_order(ctx: StageContext, monkeypatch: pytest.MonkeyPatch) -> None:
    assert DAILY_STAGES == (
        "sync",
        "fetch",
        "extract",
        "cards",
        "seed_drills",
        "phonemize",
        "audio",
    )  # R-13
    calls: list[str] = []
    monkeypatch.setattr(
        daily, "default_stages", lambda: [stage(n, calls=calls) for n in DAILY_STAGES]
    )
    assert [r.stage for r in run_daily(ctx)] == list(DAILY_STAGES) == calls


def test_auth_error_stops_pipeline_and_marks_unchanged(
    ctx: StageContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # REVIEW FOCUS 1
    calls: list[str] = []
    monkeypatch.setattr(
        daily,
        "default_stages",
        lambda: [
            stage("sync", exc=AuthError("x"), calls=calls),
            stage("fetch", counts={"downloaded": 5}, calls=calls),
        ],
    )
    reports = run_daily(ctx)
    assert calls == ["sync"] and reports[0].status == "failed"
    assert reports[0].counts == {"auth_failed": 1}
    assert daily_exit_code(reports) == 3
    assert write_summary(tmp_path / "s.json", reports)["changed"] is False


def test_stage_exception_is_failed_and_pipeline_continues(
    ctx: StageContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        daily,
        "default_stages",
        lambda: [
            stage("sync", calls=calls),
            stage("fetch", exc=RuntimeError("Leçon 3"), calls=calls),
            stage("extract", calls=calls),
        ],
    )
    r = run_daily(ctx)
    assert calls == ["sync", "fetch", "extract"] and r[1].status == "failed"
    assert r[1].errors == ["RuntimeError"]


@pytest.mark.parametrize(
    ("statuses", "auth", "code"),
    [
        (["ok", "ok"], False, 0),
        (["ok", "partial"], False, 2),
        (["partial", "failed"], False, 1),
        (["failed", "partial"], True, 3),
    ],
)
def test_exit_code_precedence(statuses: Sequence[str], auth: bool, code: int) -> None:
    reps = [
        StageReport(
            stage=f"s{i}",
            status=cast(Status, statuses[i]),
            counts={"auth_failed": 1} if auth and i == 0 else {},
        )
        for i in range(len(statuses))
    ]
    assert daily_exit_code(reps) == code


def test_changed_from_stage_qualified_counters() -> None:
    assert is_changed([StageReport(stage="audio", status="ok", counts={"done": 1})]) is True
    assert is_changed([StageReport(stage="phonemize", status="ok", counts={"updated": 2})]) is True
    assert is_changed([StageReport(stage="fetch", status="ok", counts={"done": 1})]) is False
    assert (
        is_changed([StageReport(stage="sync", status="ok", counts={"items_upserted": 0})]) is False
    )


def test_summary_excludes_errors(tmp_path: Path) -> None:
    s = write_summary(
        tmp_path / "s.json", [StageReport(stage="fetch", status="failed", errors=["Leçon"])]
    )
    assert "Leçon" not in (tmp_path / "s.json").read_text() and s["reports"][0] == {
        "stage": "fetch",
        "status": "failed",
        "counts": {},
    }


def test_default_stages_names() -> None:
    assert [n for n, _ in default_stages()] == list(DAILY_STAGES)
