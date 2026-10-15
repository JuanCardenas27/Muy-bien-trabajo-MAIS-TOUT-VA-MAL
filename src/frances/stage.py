"""Contexto y reporte de etapa (R-04)."""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from frances.config import Settings, load_settings
from frances.db.store import Store
from frances.paths import DataPaths
from frances.timeutil import now_utc


@dataclass(frozen=True)
class StageContext:
    settings: Settings
    paths: DataPaths
    store: Store
    env: Mapping[str, str]
    now: Callable[[], datetime]


@dataclass
class StageReport:
    stage: str
    status: Literal["ok", "partial", "failed"]
    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def exit_code(self) -> int:
        """`ok`→0, `partial`→2, `failed`→1."""
        return {"ok": 0, "partial": 2, "failed": 1}[self.status]


def make_context(data_dir: Path, env: Mapping[str, str] | None = None) -> StageContext:
    """Arma el contexto de etapa desde `--data DIR` (`env None` → `os.environ`)."""
    resolved_env: Mapping[str, str] = dict(os.environ) if env is None else dict(env)
    paths = DataPaths(data_dir)
    paths.ensure_dirs()
    settings = load_settings(paths.config, resolved_env)
    store = Store.open(paths.state_db)
    return StageContext(settings=settings, paths=paths, store=store, env=resolved_env, now=now_utc)
