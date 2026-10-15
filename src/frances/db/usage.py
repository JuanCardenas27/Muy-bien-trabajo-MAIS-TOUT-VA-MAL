"""Medidores de uso mensual (`usage`) y registro de etapas (`runs`)."""

import json
import sqlite3
from datetime import datetime

from frances.stage import StageReport
from frances.timeutil import to_bogota


def usage_get(conn: sqlite3.Connection, month: str, meter: str) -> int:
    """Acumulado del medidor; 0 si no existe."""
    row = conn.execute(
        "SELECT amount FROM usage WHERE month = ? AND meter = ?", (month, meter)
    ).fetchone()
    return int(row[0]) if row is not None else 0


def usage_add(conn: sqlite3.Connection, month: str, meter: str, amount: int) -> int:
    """Suma `amount` al medidor y devuelve el total nuevo."""
    row = conn.execute(
        "INSERT INTO usage (month, meter, amount) VALUES (?, ?, ?)"
        " ON CONFLICT(month, meter) DO UPDATE"
        " SET amount = amount + excluded.amount RETURNING amount",
        (month, meter, amount),
    ).fetchone()
    assert row is not None
    return int(row[0])


def current_month(now: datetime) -> str:
    """`YYYY-MM` en America/Bogota."""
    return to_bogota(now).strftime("%Y-%m")


def record_run(
    conn: sqlite3.Connection, report: StageReport, started_at: str, finished_at: str
) -> None:
    """Registra un `StageReport` en la tabla `runs`."""
    stats = json.dumps(
        {"counts": report.counts, "errors": report.errors},
        separators=(",", ":"),
        sort_keys=True,
    )
    conn.execute(
        "INSERT INTO runs (stage, started_at, finished_at, status, stats)"
        " VALUES (?, ?, ?, ?, ?)",
        (report.stage, started_at, finished_at, report.status, stats),
    )
