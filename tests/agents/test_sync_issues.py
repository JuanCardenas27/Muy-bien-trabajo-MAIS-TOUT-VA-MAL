"""Tests de la sincronización con GitHub Issues (scripts/sync_issues.py). [AGT-01]"""

import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_tasks_check import REPO_ROOT, SCRIPTS


def load_script(name: str) -> types.ModuleType:
    path = SCRIPTS / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


tc = load_script("tasks_check")  # sync_issues hace `from tasks_check import ...`
si = load_script("sync_issues")

PLANS = {"P01": "docs/superpowers/plans/2026-10-14-01-spikes-foundation.md"}


def syn_tasks() -> list[Any]:
    return [
        tc.Task(
            id="FND-01",
            plan="P01",
            human=False,
            deps=(),
            title="Scaffold del monorepo",
            owns=("pyproject.toml",),
        ),
        tc.Task(
            id="FND-02",
            plan="P01",
            human=False,
            deps=("FND-01",),
            title="Contratos y tipos",
            owns=("src/frances/models/",),
        ),
        tc.Task(
            id="SPK-02",
            plan="P01",
            human=True,
            deps=(),
            title="Voces jóvenes: escuchar y decidir",
            owns=("docs/decisions/ADR-002-child-voices.md",),
        ),
    ]


def write_tasks_yaml(tmp_path: Path, tasks: list[Any], name: str = "tasks.yaml") -> Path:
    data = {
        "plans": dict(PLANS),
        "tasks": [
            {
                "id": t.id,
                "plan": t.plan,
                "human": t.human,
                "deps": list(t.deps),
                "title": t.title,
                "owns": list(t.owns),
                "placeholders": list(t.placeholders),
            }
            for t in tasks
        ],
    }
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "calls.jsonl"
    calls.write_text("", encoding="utf-8")
    existing = tmp_path / "existing.json"
    existing.write_text("[]", encoding="utf-8")
    gh = bindir / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        'with open(os.environ["FAKE_GH_CALLS"], "a", encoding="utf-8") as f:\n'
        "    f.write(json.dumps(args) + chr(10))\n"
        'if args[:2] == ["issue", "list"]:\n'
        '    with open(os.environ["FAKE_GH_EXISTING"], encoding="utf-8") as f:\n'
        "        sys.stdout.write(f.read())\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_GH_CALLS", str(calls))
    monkeypatch.setenv("FAKE_GH_EXISTING", str(existing))
    monkeypatch.chdir(REPO_ROOT)
    return types.SimpleNamespace(calls=calls, existing=existing)


def read_calls(calls_path: Path) -> list[list[str]]:
    text = calls_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def label_values(cmd: list[str], flag: str) -> list[str]:
    return [cmd[i + 1] for i, a in enumerate(cmd[:-1]) if a == flag]


def test_issue_title_and_labels() -> None:
    t1, t2, spk = syn_tasks()
    assert si.issue_title(t1) == "[FND-01] Scaffold del monorepo"
    assert si.issue_labels(t1, 0) == ["task", "wave:0", "plan:P01"]
    assert si.issue_labels(t2, 1) == ["task", "wave:1", "plan:P01"]
    assert si.issue_labels(spk, 0) == ["task", "wave:0", "plan:P01", "human"]
    body = si.issue_body(t2, PLANS)
    assert PLANS["P01"] in body
    assert "- FND-01" in body
    assert "- src/frances/models/" in body


def test_dry_run_lists_but_creates_nothing(fake_gh: Any, tmp_path: Path, capsys: Any) -> None:
    path = write_tasks_yaml(tmp_path, syn_tasks())
    assert si.main(["--repo", "o/r", "--tasks", str(path)]) == 0
    calls = read_calls(fake_gh.calls)
    assert len(calls) == 1 and calls[0][:2] == ["issue", "list"]
    out = capsys.readouterr().out
    assert "issue create" in out and "[FND-01]" in out


def test_apply_creates_then_edits_idempotently(fake_gh: Any, tmp_path: Path) -> None:
    path = write_tasks_yaml(tmp_path, syn_tasks())
    assert si.main(["--repo", "o/r", "--tasks", str(path), "--apply"]) == 0
    first = read_calls(fake_gh.calls)
    assert first[0][:2] == ["issue", "list"]
    assert first[1][:2] == ["label", "create"]  # labels antes que los issues
    creates = [c for c in first if c[:2] == ["issue", "create"]]
    assert len(creates) == 3
    c1 = next(c for c in creates if "[FND-01] Scaffold del monorepo" in c)
    assert c1[:6] == [
        "issue",
        "create",
        "--repo",
        "o/r",
        "--title",
        "[FND-01] Scaffold del monorepo",
    ]
    assert label_values(c1, "--label") == ["task", "wave:0", "plan:P01"]
    assert '"close"' not in json.dumps(first)

    fake_gh.existing.write_text(
        json.dumps(
            [
                {"number": 7, "title": "[FND-01] Scaffold del monorepo"},
                {"number": 8, "title": "[FND-02] Contratos y tipos"},
            ]
        ),
        encoding="utf-8",
    )
    fake_gh.calls.write_text("", encoding="utf-8")
    assert si.main(["--repo", "o/r", "--tasks", str(path), "--apply"]) == 0
    second = read_calls(fake_gh.calls)
    edits = [c for c in second if c[:2] == ["issue", "edit"]]
    assert len(edits) == 2
    e7 = next(c for c in edits if "7" in c)
    assert e7[:6] == ["issue", "edit", "7", "--repo", "o/r", "--body"]
    assert label_values(e7, "--add-label") == ["task", "wave:0", "plan:P01"]
    spur = [c for c in second if c[:2] == ["issue", "create"]]
    assert len(spur) == 1 and "[SPK-02]" in " ".join(spur[0])
    assert '"close"' not in json.dumps(second)
