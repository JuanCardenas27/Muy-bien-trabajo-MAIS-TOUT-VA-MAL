"""Volcado (`dump_sql`) y restauración (`restore_sql`) deterministas."""

import os
import sqlite3
from pathlib import Path
from typing import Any

from frances.db.store import Store

_HEADER = "-- frances state dump v1"


def _literal(value: Any) -> str:
    """Literal SQL determinista para los tipos que guarda el Store."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise TypeError(f"tipo no soportado en dump: {type(value).__name__}")


def _order_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Columnas para ordenar las filas: PK en orden, `runs` por rowid."""
    if table == "runs":
        return ["rowid"]
    info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    pk_cols = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5] > 0]
    if pk_cols:
        return [str(name) for name in pk_cols]
    return [str(row[1]) for row in info]  # sin PK: todas las columnas


def dump_sql(store: Store) -> str:
    """Vuelca el esquema y las filas de forma determinista.

    Tablas por nombre; filas ordenadas por PK (`runs` por `rowid`);
    un `INSERT` por línea; termina en `\\n`.
    """
    conn = store.conn
    entries = conn.execute(
        "SELECT name, sql FROM sqlite_master"
        " WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    lines = [_HEADER]
    for name, ddl in entries:
        text = str(ddl).strip()
        if not text.endswith(";"):
            text += ";"
        lines.append(text)
    for name, _ in entries:
        table = str(name)
        order = ", ".join(f'"{col}"' for col in _order_columns(conn, table))
        rows = conn.execute(f'SELECT * FROM "{table}" ORDER BY {order}').fetchall()
        for row in rows:
            lines.append(
                f"INSERT INTO {table} VALUES ({', '.join(_literal(v) for v in row)});"
            )
    return "\n".join(lines) + "\n"


def restore_sql(sql_text: str, db_path: Path) -> Store:
    """Restaura `sql_text` en `db_path` de forma atómica y devuelve el Store."""
    tmp_path = db_path.with_suffix(".tmp")
    conn = sqlite3.connect(str(tmp_path), isolation_level=None)
    try:
        conn.executescript(sql_text)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(f"dump con FK rotas: {violations!r}")
    finally:
        conn.close()
    os.replace(tmp_path, db_path)
    return Store.open(db_path)
