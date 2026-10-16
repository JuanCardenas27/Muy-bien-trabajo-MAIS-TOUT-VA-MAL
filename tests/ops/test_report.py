import json

import pytest
from typer.testing import CliRunner

from frances.cli import app, load_commands
from frances.ops import report
from frances.ops.report import issue_for, render_body, report_failure

load_commands(app)


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


SUMMARY = {
    "changed": False,
    "reports": [
        {"stage": "sync", "status": "ok", "counts": {"items_upserted": 3}},
        {"stage": "fetch", "status": "failed", "counts": {}, "errors": ["Leçon 3 — Mme Dupont"]},
    ],
}
RUN = "https://github.com/o/repo/actions/runs/1"


class FakeGh:
    def __init__(self, open_numbers: list[int]) -> None:
        self.open, self.calls = open_numbers, []

    def __call__(self, args: list[str], stdin: str | None = None) -> str:
        self.calls.append((args, stdin))
        if args[:2] == ["issue", "list"]:
            return json.dumps([{"number": n} for n in self.open])
        return ""


def test_creates_issue_when_none_open() -> None:
    assert issue_for(3) == ("reauth-google", "Re-autoriza Google Classroom")
    assert issue_for(1) == ("pipeline-failure", "El pipeline diario falló")
    gh = FakeGh([])
    assert report_failure(SUMMARY, RUN, 1, "o/repo", gh) == "created"
    assert gh.calls[0][0][:6] == [
        "label",
        "create",
        "pipeline-failure",
        "--force",
        "--repo",
        "o/repo",
    ]
    create = next(a for a, _ in gh.calls if a[:2] == ["issue", "create"])
    assert "--title" in create and "El pipeline diario falló" in create and "--body-file" in create


def test_comments_existing_open_issue() -> None:
    gh = FakeGh([42])
    assert report_failure(SUMMARY, RUN, 3, "o/repo", gh) == "commented"
    assert any(a[:3] == ["issue", "comment", "42"] for a, _ in gh.calls)
    assert not any(a[:2] == ["issue", "create"] for a, _ in gh.calls)


def test_issue_body_has_only_stage_status_and_counts() -> None:
    body = render_body(SUMMARY, RUN, 1)
    assert "| sync | ok | items_upserted=3 |" in body and "| fetch | failed |  |" in body
    assert RUN in body and "Exit code: 1" in body
    assert "Leçon" not in body and "Dupont" not in body


def test_body_rejects_non_slug_stage_and_non_int_counts() -> None:
    body = render_body(
        {"reports": [{"stage": "Mme Dupont", "status": "ok", "counts": {"x": "Leçon"}}]}, RUN, 1
    )
    assert "Dupont" not in body and "Leçon" not in body and "| ? | ok |  |" in body


def test_missing_summary_still_reports(tmp_path, cli_runner, monkeypatch) -> None:
    monkeypatch.setattr(report, "run_gh", FakeGh([]))
    r = cli_runner.invoke(app, ["report-failure", "--run-url", RUN, "--data", str(tmp_path)])
    assert r.exit_code == 0 and "Sin resumen del pipeline" in render_body(None, RUN, 1)
