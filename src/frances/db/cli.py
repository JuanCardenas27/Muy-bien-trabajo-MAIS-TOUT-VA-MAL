"""Comandos `frances restore` / `frances dump` (volcado determinista)."""

from pathlib import Path

import typer

from frances.cli import DataOpt, exit_with
from frances.db.dump import dump_sql, restore_sql
from frances.db.store import Store
from frances.paths import DataPaths


def _restore_cmd(data: Path) -> None:
    paths = DataPaths(data)
    paths.ensure_dirs()
    if paths.state_sql.exists():
        store = restore_sql(
            paths.state_sql.read_text(encoding="utf-8"), paths.state_db
        )
        store.close()
    else:
        Store.open(paths.state_db).close()
    return None


def _dump_cmd(data: Path) -> None:
    paths = DataPaths(data)
    paths.ensure_dirs()
    store = Store.open(paths.state_db)
    try:
        text = dump_sql(store)
    finally:
        store.close()
    if paths.state_sql.exists() and paths.state_sql.read_text(encoding="utf-8") == text:
        return None  # sin cambios: no toca el archivo
    paths.state_sql.parent.mkdir(parents=True, exist_ok=True)
    paths.state_sql.write_text(text, encoding="utf-8")
    return None


def register(app: typer.Typer) -> None:
    """Registra `restore` y `dump` en la CLI."""

    @app.command("restore")
    def restore(data: DataOpt = Path(".")) -> None:
        exit_with(lambda: _restore_cmd(data))

    @app.command("dump")
    def dump(data: DataOpt = Path(".")) -> None:
        exit_with(lambda: _dump_cmd(data))
