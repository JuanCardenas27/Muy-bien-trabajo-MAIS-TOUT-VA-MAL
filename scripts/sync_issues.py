#!/usr/bin/env python3
"""Sincroniza tasks.yaml con GitHub Issues vía `gh`. [AGT-01]

Sin `--apply` imprime los comandos (dry-run); con `--apply` los ejecuta.
Solo stdlib + PyYAML (vía tasks_check).
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

from tasks_check import Task, load_graph, validate, waves

TITLE_RE = re.compile(r"\[([A-Z]+-\d+)\]")


def issue_title(t: Task) -> str:
    return f"[{t.id}] {t.title}"


def issue_labels(t: Task, wave: int) -> list[str]:
    labels = ["task", f"wave:{wave}", f"plan:{t.plan}"]
    if t.human:
        labels.append("human")
    return labels


def issue_body(t: Task, plans: dict[str, str]) -> str:
    lines = [f"Plan: {plans[t.plan]}", "", "Deps:"]
    if t.deps:
        lines.extend(f"- {dep}" for dep in t.deps)
    else:
        lines.append("- (ninguna)")
    lines.extend(["", "Owns:"])
    if t.owns:
        lines.extend(f"- {own}" for own in t.owns)
    else:
        lines.append("- (ninguno)")
    if t.placeholders:
        lines.extend(["", "Placeholders:"])
        lines.extend(f"- {ph}" for ph in t.placeholders)
    lines.extend(["", f"Human: {'sí' if t.human else 'no'}"])
    return "\n".join(lines) + "\n"


def wave_of(tasks: list[Task]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, wave in enumerate(waves(tasks)):
        for tid in wave:
            out[tid] = i
    return out


def plan_commands(
    tasks: list[Task],
    plans: dict[str, str],
    existing: dict[str, int],
    repo: str,
) -> list[list[str]]:
    """Comandos `gh` finales (con `--repo`): labels primero, luego create/edit."""
    waves_by_id = wave_of(tasks)
    labels = sorted(
        {label for t in tasks for label in issue_labels(t, waves_by_id[t.id])}
    )
    cmds = [["gh", "label", "create", label, "--repo", repo, "--force"] for label in labels]
    for t in tasks:
        body = issue_body(t, plans)
        task_labels = issue_labels(t, waves_by_id[t.id])
        if t.id in existing:
            cmd = [
                "gh",
                "issue",
                "edit",
                str(existing[t.id]),
                "--repo",
                repo,
                "--body",
                body,
            ]
            for label in task_labels:
                cmd += ["--add-label", label]
        else:
            cmd = [
                "gh",
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                issue_title(t),
                "--body",
                body,
            ]
            for label in task_labels:
                cmd += ["--label", label]
        cmds.append(cmd)
    return cmds


def load_existing(repo: str) -> dict[str, int]:
    proc = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--limit",
            "500",
            "--search",
            "in:title [",
            "--json",
            "number,title",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    existing: dict[str, int] = {}
    for item in json.loads(proc.stdout or "[]"):
        match = TITLE_RE.match(item.get("title", ""))
        if match and match.group(1) not in existing:
            existing[match.group(1)] = int(item["number"])
    return existing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sync_issues.py",
        description="Sincroniza tasks.yaml con GitHub Issues.",
    )
    parser.add_argument("--repo", required=True, help="repo GitHub (dueño/nombre)")
    parser.add_argument("--tasks", type=Path, default=Path("docs/superpowers/plans/tasks.yaml"))
    parser.add_argument("--apply", action="store_true", help="ejecuta con gh (sin esto: dry-run)")
    args = parser.parse_args(argv)
    plans, tasks = load_graph(args.tasks)
    errors = validate(plans, tasks, Path.cwd(), check_plans=True)
    if errors:
        for err in errors:
            print(err)
        return 1
    cmds = plan_commands(tasks, plans, load_existing(args.repo), args.repo)
    if not args.apply:
        for cmd in cmds:
            print(shlex.join(cmd))
        return 0
    for cmd in cmds:
        subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
