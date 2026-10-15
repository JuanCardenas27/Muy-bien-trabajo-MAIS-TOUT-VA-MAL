from dataclasses import dataclass
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

import frances.cli as cli
from frances.cli import COMMAND_MODULES
from frances.errors import AuthError, ConfigError


def test_command_modules_lists_all_stages() -> None:
    assert COMMAND_MODULES == (
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


def test_exit_with_maps_report_and_errors(capsys: pytest.CaptureFixture[str]) -> None:
    @dataclass
    class FakeReport:  # estructuralmente igual a StageReport.exit_code (FND-03)
        code: int

        def exit_code(self) -> int:
            return self.code

    def boom() -> None:
        raise ConfigError("token ya29.xyz inválido")

    for fn, code in (
        (lambda: None, 0),
        (lambda: FakeReport(2), 2),
        (lambda: FakeReport(1), 1),
        (boom, 4),
    ):
        with pytest.raises(typer.Exit) as e:
            cli.exit_with(fn)
        assert e.value.exit_code == code
    err = capsys.readouterr().err
    assert "ya29.xyz" not in err and "[REDACTED]" in err


def test_broken_import_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "broken_cmd.py").write_text("import paquete_inexistente_xyz\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(cli, "COMMAND_MODULES", ("broken_cmd",))
    with pytest.raises(ModuleNotFoundError):
        cli.load_commands(typer.Typer())


def test_missing_module_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "COMMAND_MODULES", ("frances.nope_missing",))
    cli.load_commands(typer.Typer())  # no lanza


def test_frances_error_maps_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def register(app: typer.Typer) -> None:
        # Segundo comando solo para que typer use modo grupo (con uno solo
        # invocaría el comando directamente sin aceptar su nombre).
        @app.command()
        def ping() -> None:
            typer.echo("pong")

        @app.command()
        def boom(data: cli.DataOpt = Path(".")) -> None:
            def fn() -> None:
                raise AuthError("token ya29.xyz inválido")

            cli.exit_with(fn)

    fake = tmp_path / "fake_boom_cmd.py"
    fake.write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib.util

    spec = importlib.util.spec_from_file_location("fake_boom_cmd", fake)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module.register = register  # type: ignore[attr-defined]
    import sys

    sys.modules["fake_boom_cmd"] = module
    monkeypatch.setattr(cli, "COMMAND_MODULES", ("fake_boom_cmd",))
    monkeypatch.setattr(sys, "argv", ["frances", "boom", "--data", str(tmp_path)])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 3
    err = capsys.readouterr().err
    assert "ya29.xyz" not in err and "[REDACTED]" in err
    runner_result = CliRunner().invoke(cli.app, ["--help"])
    assert runner_result.exit_code in (0, 2)  # app existe y responde
