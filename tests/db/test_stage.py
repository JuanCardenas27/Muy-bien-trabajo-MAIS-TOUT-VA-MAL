"""Tests de StageContext / StageReport / make_context."""

from datetime import datetime
from pathlib import Path

from frances.stage import StageContext, StageReport, make_context


def test_stage_report_exit_code() -> None:
    assert [StageReport("x", s).exit_code() for s in ("ok", "partial", "failed")] == [
        0,
        2,
        1,
    ]


def test_make_context_opens_state_db(tmp_path: Path) -> None:
    ctx = make_context(tmp_path, {})
    try:
        assert isinstance(ctx, StageContext)
        assert (tmp_path / ".cache" / "state.db").exists()
        assert ctx.paths.root == tmp_path
        assert ctx.settings.cards.llm == "auto"
        assert ctx.env == {}
        assert isinstance(ctx.now(), datetime)
    finally:
        ctx.store.close()
