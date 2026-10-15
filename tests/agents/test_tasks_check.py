"""Tests del validador del grafo (scripts/tasks_check.py). [AGT-01]"""

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
REAL_YAML = REPO_ROOT / "docs/superpowers/plans/tasks.yaml"
REAL_PLAN = "docs/superpowers/plans/2026-10-14-01-spikes-foundation.md"


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


tc = load_script("tasks_check")


def make_task(
    id: str,
    deps: list[str] | None = None,
    owns: list[str] | None = None,
    plan: str = "P01",
    human: bool = False,
    title: str = "t",
    placeholders: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "plan": plan,
        "human": human,
        "deps": deps or [],
        "title": title,
        "owns": owns or [],
        "placeholders": placeholders or [],
    }


def write_yaml(
    tmp_path: Path,
    tasks: list[dict[str, Any]],
    plans: dict[str, str] | None = None,
    name: str = "tasks.yaml",
) -> Path:
    data = {"plans": plans if plans is not None else {"P01": REAL_PLAN}, "tasks": tasks}
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def validate_file(path: Path, root: Path, check_plans: bool = False) -> list[str]:
    plans, tasks = tc.load_graph(path)
    return tc.validate(plans, tasks, root, check_plans)


def test_cycle_detected(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path,
        [make_task("A-01", deps=["B-01"]), make_task("B-01", deps=["A-01"])],
    )
    errs = validate_file(path, tmp_path)
    assert any("ciclo" in e for e in errs), errs


def test_missing_dep_detected(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, [make_task("A-01", deps=["X-99"])])
    errs = validate_file(path, tmp_path)
    assert any("dep inexistente: X-99" in e for e in errs), errs


def test_duplicate_id_detected(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, [make_task("A-01"), make_task("A-01")])
    errs = validate_file(path, tmp_path)
    assert any("id duplicado: A-01" in e for e in errs), errs


def test_owns_overlap_prefix(tmp_path: Path) -> None:
    bad = write_yaml(
        tmp_path,
        [make_task("A-01", owns=["src/a/"]), make_task("B-01", owns=["src/a/b.py"])],
        name="bad.yaml",
    )
    assert validate_file(bad, tmp_path) != []
    good = write_yaml(
        tmp_path,
        [make_task("A-01", owns=["web/App.tsx"]), make_task("B-01", owns=["web/App.test.tsx"])],
        name="good.yaml",
    )
    assert validate_file(good, tmp_path) == []


def test_missing_plan_file(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, [make_task("A-01")], plans={"P01": "docs/no-existe.md"})
    plans, tasks = tc.load_graph(path)
    assert tc.validate(plans, tasks, tmp_path, True) != []
    assert tc.validate(plans, tasks, tmp_path, False) == []


def test_placeholder_requires_transitive_dep(tmp_path: Path) -> None:
    good = write_yaml(
        tmp_path,
        [
            make_task("A-01", owns=["a.py"], placeholders=["gen/x.py"]),
            make_task("B-01", deps=["A-01"], owns=["gen/x.py"]),
        ],
        name="good.yaml",
    )
    assert validate_file(good, tmp_path) == []
    bad = write_yaml(
        tmp_path,
        [
            make_task("A-01", owns=["a.py"], placeholders=["gen/x.py"]),
            make_task("C-01", owns=["gen/x.py"]),
        ],
        name="bad.yaml",
    )
    errs = validate_file(bad, tmp_path)
    assert any("placeholder" in e for e in errs), errs


def test_real_graph_is_valid_and_waves() -> None:
    plans, tasks = tc.load_graph(REAL_YAML)
    assert tc.validate(plans, tasks, REPO_ROOT, False) == []
    assert tc.validate(plans, tasks, REPO_ROOT, True) == []
    ws = tc.waves(tasks)
    assert [len(w) for w in ws] == [6, 7, 16, 14, 12, 7, 4, 2, 2, 2, 1]
    assert all(w == sorted(w) for w in ws)
    assert "AGT-01" in ws[1]


def test_ready_from_git_subjects() -> None:
    _, tasks = tc.load_graph(REAL_YAML)
    merged = tc.merged_ids(["build: scaffold [FND-01]", "feat(core): núcleo [FND-04]", "chore: x"])
    assert merged == {"FND-01", "FND-04"}
    got = tc.ready(tasks, merged)
    assert "FND-02" in got and "FND-05" in got and "AGT-01" in got
    assert "FND-03" not in got  # FND-03 espera a FND-02


def test_main_waves_reports_all_waves(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.chdir(REPO_ROOT)
    assert tc.main(["--tasks", str(REAL_YAML), "--waves"]) == 0
    out = capsys.readouterr().out
    assert "Ola 0 (6)" in out
    assert "AGT-01" in out


def test_main_returns_1_on_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    path = write_yaml(tmp_path, [make_task("A-01", deps=["X-99"])])
    assert tc.main(["--tasks", str(path)]) == 1
    assert "dep inexistente" in capsys.readouterr().out
