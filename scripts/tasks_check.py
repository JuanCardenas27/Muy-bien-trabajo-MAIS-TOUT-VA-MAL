#!/usr/bin/env python3
"""Valida docs/superpowers/plans/tasks.yaml (grafo de tareas). [AGT-01]

Sin flags imprime los errores y sale 1 si hay; `--waves` imprime las olas;
`--ready` imprime las tareas listas según `origin/main`. Solo stdlib + PyYAML.
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_TASKS = Path("docs/superpowers/plans/tasks.yaml")
MERGED_RE = re.compile(r"\[([A-Z]+-\d+)\]")


@dataclass(frozen=True)
class Task:
    id: str
    plan: str
    human: bool
    deps: tuple[str, ...] = ()
    title: str = ""
    owns: tuple[str, ...] = ()
    placeholders: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "deps", tuple(self.deps))
        object.__setattr__(self, "owns", tuple(self.owns))
        object.__setattr__(self, "placeholders", tuple(self.placeholders))


def load_graph(path: Path) -> tuple[dict[str, str], list[Task]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    plans = dict(data.get("plans") or {})
    tasks = [
        Task(
            id=t["id"],
            plan=t["plan"],
            human=bool(t.get("human", False)),
            deps=tuple(t.get("deps") or ()),
            title=t.get("title") or "",
            owns=tuple(t.get("owns") or ()),
            placeholders=tuple(t.get("placeholders") or ()),
        )
        for t in (data.get("tasks") or [])
    ]
    return plans, tasks


def _find_cycles(by_id: dict[str, Task]) -> list[list[str]]:
    color: dict[str, int] = dict.fromkeys(by_id, 0)  # 0 blanca, 1 gris, 2 negra
    cycles: list[list[str]] = []

    def visit(node: str, stack: list[str]) -> None:
        color[node] = 1
        stack.append(node)
        for dep in by_id[node].deps:
            if dep not in by_id:
                continue
            if color[dep] == 1:
                cycles.append(stack[stack.index(dep):] + [dep])
            elif color[dep] == 0:
                visit(dep, stack)
        stack.pop()
        color[node] = 2

    for tid in sorted(by_id):
        if color[tid] == 0:
            visit(tid, [])
    return cycles


def _transitive_deps(task: Task, by_id: dict[str, Task]) -> set[str]:
    seen: set[str] = set()
    stack = list(task.deps)
    while stack:
        dep = stack.pop()
        if dep in seen or dep not in by_id:
            continue
        seen.add(dep)
        stack.extend(by_id[dep].deps)
    return seen


def validate(
    plans: dict[str, str],
    tasks: list[Task],
    repo_root: Path,
    check_plans: bool = True,
) -> list[str]:
    errors: list[str] = []
    seen: dict[str, int] = {}
    for t in tasks:
        seen[t.id] = seen.get(t.id, 0) + 1
    for tid in sorted(seen):
        if seen[tid] > 1:
            errors.append(f"id duplicado: {tid}")
    by_id = {t.id: t for t in tasks}
    for t in tasks:
        if t.plan not in plans:
            errors.append(f"plan desconocido: {t.plan} (tarea {t.id})")
        for dep in t.deps:
            if dep not in by_id:
                errors.append(f"dep inexistente: {dep} (tarea {t.id})")
    for cycle in _find_cycles(by_id):
        errors.append(f"ciclo detectado: {' -> '.join(cycle)}")
    for i, a in enumerate(tasks):
        for b in tasks[i + 1:]:
            for o1 in a.owns:
                for o2 in b.owns:
                    if o1 == o2 or (o1.endswith("/") and o2.startswith(o1)):
                        errors.append(f"owns solapados: {a.id} ({o1}) y {b.id} ({o2})")
                    elif o2.endswith("/") and o1.startswith(o2):
                        errors.append(f"owns solapados: {b.id} ({o2}) y {a.id} ({o1})")
    for owner in tasks:
        for ph in owner.placeholders:
            for other in tasks:
                if other.id == owner.id or ph not in other.owns:
                    continue
                if owner.id not in _transitive_deps(other, by_id):
                    errors.append(
                        f"placeholder sin dependencia: {ph} "
                        f"(de {owner.id}) en owns de {other.id}"
                    )
    if check_plans:
        root = Path(repo_root)
        for t in tasks:
            rel = plans.get(t.plan)
            if rel is None or (root / rel).exists():
                continue
            errors.append(f"plan inexistente: {t.plan} -> {rel} (tarea {t.id})")
    return errors


def waves(tasks: list[Task]) -> list[list[str]]:
    by_id = {t.id: t for t in tasks}
    memo: dict[str, int] = {}

    def depth(tid: str, stack: tuple[str, ...] = ()) -> int:
        if tid in memo:
            return memo[tid]
        if tid in stack:
            raise ValueError(f"ciclo detectado: {' -> '.join((*stack, tid))}")
        task = by_id.get(tid)
        known = [d for d in (task.deps if task else ()) if d in by_id]
        level = 0 if not known else 1 + max(depth(d, (*stack, tid)) for d in known)
        memo[tid] = level
        return level

    grouped: dict[int, list[str]] = {}
    for t in tasks:
        grouped.setdefault(depth(t.id), []).append(t.id)
    return [sorted(grouped[i]) for i in range(max(grouped) + 1)] if grouped else []


def merged_ids(log_subjects: list[str]) -> set[str]:
    found: set[str] = set()
    for subject in log_subjects:
        found.update(MERGED_RE.findall(subject))
    return found


def ready(tasks: list[Task], merged: set[str]) -> list[str]:
    return sorted(
        t.id for t in tasks if t.id not in merged and all(d in merged for d in t.deps)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tasks_check.py",
        description="Valida docs/superpowers/plans/tasks.yaml.",
    )
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--waves", action="store_true", help="imprime las olas del grafo")
    parser.add_argument(
        "--ready", action="store_true", help="imprime las tareas listas según origin/main"
    )
    args = parser.parse_args(argv)
    plans, tasks = load_graph(args.tasks)
    errors = validate(plans, tasks, Path.cwd(), check_plans=True)
    if errors:
        for err in errors:
            print(err)
        return 1
    if args.waves:
        for i, wave in enumerate(waves(tasks)):
            print(f"Ola {i} ({len(wave)}): {' '.join(wave)}")
        return 0
    if args.ready:
        proc = subprocess.run(
            ["git", "log", "origin/main", "--format=%s"],
            check=True,
            capture_output=True,
            text=True,
        )
        pending = ready(tasks, merged_ids(proc.stdout.splitlines()))
        print(f"Listas ({len(pending)}): {' '.join(pending)}")
        return 0
    print(f"OK: {len(tasks)} tareas, {len(waves(tasks))} olas, sin errores")
    return 0


if __name__ == "__main__":
    sys.exit(main())
