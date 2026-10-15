"""CLI ``frances``: cada comando declara su propio ``--data`` (R-05)."""

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, NoReturn, Protocol

import typer

from frances.errors import FrancesError
from frances.log import redact

DataOpt = Annotated[Path, typer.Option("--data", help="Raíz del repo de datos")]

COMMAND_MODULES: tuple[str, ...] = (
    "frances.models.schema_cli",
    "frances.db.cli",
    "frances.sync.auth",
    "frances.sync.run",
    "frances.fetch.run",
    "frances.extract.run",
    "frances.cards.run",
    "frances.cards.phonemes",
    "frances.audio.run",
    "frances.bundle.run",
    "frances.ops.daily",
    "frances.ops.report",
    "frances.ops.doctor",
)

app = typer.Typer()


class SupportsExitCode(Protocol):
    """Lo que ``exit_with`` acepta; ``StageReport`` (FND-03) lo cumple."""

    def exit_code(self) -> int: ...


def exit_with(fn: Callable[[], SupportsExitCode | None]) -> NoReturn:
    """Ejecuta ``fn`` y convierte el resultado en salida de CLI.

    ``FrancesError`` → mensaje redactado en stderr + su ``exit_code``;
    reporte → ``exit_code()`` del reporte; ``None`` → 0.
    """
    try:
        report = fn()
    except FrancesError as exc:
        typer.echo(redact(str(exc)), err=True)
        raise typer.Exit(exc.exit_code) from exc
    if report is None:
        raise typer.Exit(0)
    raise typer.Exit(report.exit_code())


def load_commands(target: typer.Typer) -> None:
    """Importa cada módulo de ``COMMAND_MODULES`` y llama a su ``register(app)``.

    Un módulo que todavía no existe se salta; cualquier otro error revienta.
    """
    for name in COMMAND_MODULES:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name == name:
                continue
            raise
        register: Callable[[typer.Typer], None] = vars(module)["register"]
        register(target)


def main() -> None:
    """Entry point ``frances = "frances.cli:main"``."""
    load_commands(app)
    app()
