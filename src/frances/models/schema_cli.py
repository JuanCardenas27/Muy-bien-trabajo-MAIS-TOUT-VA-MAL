"""Comando ``frances schema export DIR``: vuelca los contratos a JSON Schema."""

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel

from frances.models.bundle import BundleManifest, ContentIndex
from frances.models.pron import PronResult

SCHEMAS: dict[str, type[BaseModel]] = {
    "content-index": ContentIndex,
    "bundle-manifest": BundleManifest,
    "pron-result": PronResult,
}


def export_schemas(out_dir: Path) -> list[Path]:
    """Escribe los tres JSON Schema en ``out_dir`` de forma determinista."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in SCHEMAS.items():
        schema = model.model_json_schema(mode="serialization")
        text = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        path = out_dir / f"{name}.schema.json"
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def register(app: typer.Typer) -> None:
    """Registra el subcomando ``schema export DIR`` en la CLI."""
    schema_app = typer.Typer(help="Contratos: JSON Schema y tipos generados.")

    @schema_app.command("export")
    def export_cmd(
        dir: Annotated[Path, typer.Argument(help="Directorio donde escribir los schemas.")],
    ) -> None:
        for path in export_schemas(dir):
            typer.echo(str(path))

    app.add_typer(schema_app, name="schema")
