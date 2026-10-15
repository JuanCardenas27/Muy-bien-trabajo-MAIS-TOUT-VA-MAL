"""Tests de la CLI `frances restore` / `frances dump`."""

import sqlite3
from pathlib import Path

import typer
from typer.testing import CliRunner

from frances.db import cli as db_cli
from frances.db.store import Store


def _app() -> typer.Typer:
    app = typer.Typer()
    db_cli.register(app)
    return app


def test_restore_cli_without_state_sql_creates_empty_db(tmp_path: Path) -> None:
    result = CliRunner().invoke(_app(), ["restore", "--data", str(tmp_path)])
    assert result.exit_code == 0, result.output
    db_path = tmp_path / ".cache" / "state.db"
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
    finally:
        conn.close()


def test_dump_cli_writes_only_on_change(tmp_path: Path) -> None:
    runner = CliRunner()
    app = _app()
    assert runner.invoke(app, ["restore", "--data", str(tmp_path)]).exit_code == 0
    assert runner.invoke(app, ["dump", "--data", str(tmp_path)]).exit_code == 0
    sql_path = tmp_path / "state" / "state.sql"
    assert sql_path.exists()
    mtime_1 = sql_path.stat().st_mtime_ns
    assert runner.invoke(app, ["dump", "--data", str(tmp_path)]).exit_code == 0
    assert sql_path.stat().st_mtime_ns == mtime_1
    store = Store.open(tmp_path / ".cache" / "state.db")
    try:
        with store.tx() as conn:
            conn.execute("INSERT INTO usage VALUES (?,?,?)", ("2026-10", "llm_items", 1))
    finally:
        store.close()
    assert runner.invoke(app, ["dump", "--data", str(tmp_path)]).exit_code == 0
    assert sql_path.stat().st_mtime_ns != mtime_1


def test_restore_cli_roundtrip_with_state_sql(tmp_path: Path) -> None:
    runner = CliRunner()
    app = _app()
    assert runner.invoke(app, ["restore", "--data", str(tmp_path)]).exit_code == 0
    store = Store.open(tmp_path / ".cache" / "state.db")
    try:
        with store.tx() as conn:
            conn.execute("INSERT INTO usage VALUES (?,?,?)", ("2026-10", "llm_items", 7))
    finally:
        store.close()
    assert runner.invoke(app, ["dump", "--data", str(tmp_path)]).exit_code == 0
    (tmp_path / ".cache" / "state.db").unlink()
    assert runner.invoke(app, ["restore", "--data", str(tmp_path)]).exit_code == 0
    store = Store.open(tmp_path / ".cache" / "state.db")
    try:
        assert store.conn.execute("SELECT amount FROM usage").fetchall() == [(7,)]
    finally:
        store.close()
