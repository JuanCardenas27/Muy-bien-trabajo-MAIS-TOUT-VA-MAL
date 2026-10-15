from pathlib import Path

import typer
from typer.testing import CliRunner

from frances.models.schema_cli import export_schemas, register


def test_schema_export_is_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    export_schemas(a)
    export_schemas(b)
    names = sorted(p.name for p in a.iterdir())
    assert names == [
        "bundle-manifest.schema.json",
        "content-index.schema.json",
        "pron-result.schema.json",
    ]
    assert all((a / n).read_bytes() == (b / n).read_bytes() for n in names)
    assert (a / names[0]).read_bytes().endswith(b"}\n")


def test_committed_contracts_up_to_date(tmp_path: Path) -> None:
    export_schemas(tmp_path)
    for p in tmp_path.iterdir():
        assert (Path("contracts") / p.name).read_bytes() == p.read_bytes()


def test_register_adds_schema_export_command(tmp_path: Path) -> None:
    app = typer.Typer()
    register(app)
    result = CliRunner().invoke(app, ["schema", "export", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "bundle-manifest.schema.json",
        "content-index.schema.json",
        "pron-result.schema.json",
    ]
