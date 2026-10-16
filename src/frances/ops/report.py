"""``frances report-failure``: issues idempotentes de fallo vía ``gh`` (R-05).

El cuerpo del issue nunca lleva contenido del Classroom: solo nombres de
etapa, estados, conteos enteros, el exit code y el enlace al run (Review
Focus 2 de P07).
"""

import json
import re
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, Literal

import typer

from frances.cli import DataOpt, exit_with
from frances.db.store import Store  # noqa: F401  (rompe el ciclo de import stage↔db.usage)
from frances.errors import FrancesError
from frances.log import get_logger
from frances.stage import make_context

log = get_logger(__name__)

GhRunner = Callable[[list[str], str | None], str]

_SLUG_RE = re.compile(r"^[a-z_]{1,32}$")

_REAUTH_LINE = "Repite LIVE-01 desde `frances auth init`."


def issue_for(exit_code: int) -> tuple[str, str]:
    """Mapea el exit code del pipeline a ``(label, title)`` del issue."""
    if exit_code == 3:
        return "reauth-google", "Re-autoriza Google Classroom"
    return "pipeline-failure", "El pipeline diario falló"


def _slug(value: object) -> str:
    if isinstance(value, str) and _SLUG_RE.fullmatch(value):
        return value
    return "?"


def _counts_cell(counts: object) -> str:
    if not isinstance(counts, Mapping):
        return ""
    keys = sorted(key for key in counts if isinstance(key, str) and _SLUG_RE.fullmatch(key))
    parts = [f"{key}={counts[key]}" for key in keys if type(counts[key]) is int]
    return ", ".join(parts)


def render_body(summary: Mapping[str, object] | None, run_url: str, exit_code: int) -> str:
    """Cuerpo del issue: tabla ``| etapa | estado | conteos |``, exit code y run URL.

    ``stage`` y ``status`` solo si cumplen ``^[a-z_]{1,32}$`` (si no, ``?``);
    conteos solo ``int`` como ``k=v`` ordenados por clave con ``k`` también
    slug; ``errors`` se ignora siempre. Con exit 3 agrega la nota de re-auth.
    """
    lines = [
        "El pipeline diario falló.",
        "",
        f"Exit code: {exit_code}",
        f"Run: {run_url}",
        "",
        "| etapa | estado | conteos |",
        "| --- | --- | --- |",
    ]
    reports = summary.get("reports") if summary is not None else None
    if not isinstance(reports, list):
        lines.append("Sin resumen del pipeline.")
    else:
        for item in reports:
            if not isinstance(item, Mapping):
                continue
            stage = _slug(item.get("stage"))
            status = _slug(item.get("status"))
            lines.append(f"| {stage} | {status} | {_counts_cell(item.get('counts'))} |")
    if exit_code == 3:
        lines += ["", _REAUTH_LINE]
    return "\n".join(lines)


def run_gh(args: list[str], stdin: str | None = None) -> str:
    """Ejecuta ``gh`` con argv (nunca ``shell=True``) y devuelve su stdout."""
    return subprocess.run(
        ["gh", *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _first_open_number(listing: str) -> str | None:
    try:
        data: object = json.loads(listing) if listing else []
    except json.JSONDecodeError as exc:
        raise FrancesError("gh issue list: salida no parseable") from exc
    if not isinstance(data, list):
        raise FrancesError("gh issue list: salida no parseable")
    for entry in data:
        if isinstance(entry, dict) and isinstance(entry.get("number"), int):
            return str(entry["number"])
    return None


def report_failure(
    summary: Mapping[str, object] | None,
    run_url: str,
    exit_code: int,
    repo: str | None,
    gh: GhRunner = run_gh,
) -> Literal["created", "commented"]:
    """Abre o comenta el issue de fallo; idempotente por label.

    Secuencia: ``gh label create <label> --force`` → ``gh issue list`` → si
    hay issue abierto ``gh issue comment N --body-file -``; si no, ``gh issue
    create``. El cuerpo va por stdin. Un fallo de ``gh`` loguea solo el
    subcomando y sale con 1 (``FrancesError``).
    """
    label, title = issue_for(exit_code)
    body = render_body(summary, run_url, exit_code)
    repo_args = ["--repo", repo] if repo else []
    try:
        gh(["label", "create", label, "--force", *repo_args], None)
        listing = gh(
            [
                "issue",
                "list",
                "--label",
                label,
                "--state",
                "open",
                "--json",
                "number",
                "--limit",
                "1",
                *repo_args,
            ],
            None,
        )
        number = _first_open_number(listing)
        if number is not None:
            gh(["issue", "comment", number, "--body-file", "-", *repo_args], body)
            return "commented"
        gh(
            ["issue", "create", "--title", title, "--label", label, "--body-file", "-", *repo_args],
            body,
        )
        return "created"
    except subprocess.CalledProcessError as exc:
        subcommand = " ".join(exc.cmd[1:3])
        log.error("gh %s: falló (exit %s)", subcommand, exc.returncode)
        raise FrancesError(f"gh {subcommand} falló") from exc


def _load_summary(path: Path) -> Mapping[str, object] | None:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("report-failure: resumen del pipeline no disponible")
        return None
    return payload if isinstance(payload, dict) else None


def register(app: typer.Typer) -> None:
    """Registra ``frances report-failure --run-url URL [--summary PATH] [--exit-code N]``."""

    @app.command("report-failure")
    def report_failure_cmd(
        run_url: Annotated[str, typer.Option("--run-url", help="URL del run de Actions fallido")],
        summary: Annotated[
            Path | None, typer.Option("--summary", help="JSON de resumen del pipeline")
        ] = None,
        exit_code_opt: Annotated[
            int, typer.Option("--exit-code", help="Exit code del pipeline")
        ] = 1,
        data: DataOpt = Path("."),
    ) -> None:
        def run() -> None:
            ctx = make_context(data)
            path = summary if summary is not None else ctx.paths.cache / "daily_summary.json"
            result = report_failure(
                _load_summary(path),
                run_url,
                exit_code_opt,
                ctx.env.get("GITHUB_REPOSITORY"),
                run_gh,
            )
            typer.echo(result)

        exit_with(run)
