"""Store SQLite: apertura con migraciones, transacciones y FK activadas."""

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

_MIGRATION_RE = re.compile(r"(\d{4})_.*\.sql")


def _split_statements(sql: str) -> list[str]:
    """Parte un archivo de migración en sentencias (sin `;` dentro de literales)."""
    return [chunk.strip() for chunk in sql.split(";") if chunk.strip()]


def _apply_migration(conn: sqlite3.Connection, sql: str) -> None:
    """Aplica una migración dentro de `BEGIN IMMEDIATE`/`COMMIT`."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement in _split_statements(sql):
            conn.execute(statement)
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _pending_migrations(version: int) -> list[tuple[int, str]]:
    """Migraciones `NNNN_*.sql` con `NNNN > version`, en orden numérico."""
    base = resources.files("frances.db.migrations")
    names = sorted(
        entry.name
        for entry in base.iterdir()
        if entry.is_file() and _MIGRATION_RE.fullmatch(entry.name)
    )
    pending: list[tuple[int, str]] = []
    for name in names:
        match = _MIGRATION_RE.fullmatch(name)
        assert match is not None  # filtrado arriba
        number = int(match.group(1))
        if number > version:
            sql = (base / name).read_text(encoding="utf-8")
            pending.append((number, sql))
    pending.sort(key=lambda item: item[0])
    return pending


class Store:
    """Conexión SQLite con `foreign_keys=ON` y `journal_mode=DELETE`."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, db_path: Path) -> "Store":
        """Crea el archivo si falta y aplica las migraciones pendientes."""
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=DELETE")
        try:
            row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            version = int(row[0]) if row is not None and row[0] is not None else 0
        except sqlite3.OperationalError:
            version = 0  # la tabla schema_version aún no existe
        for _, sql in _pending_migrations(version):
            _apply_migration(conn, sql)
        return cls(conn)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Transacción `BEGIN IMMEDIATE`; `COMMIT` o `ROLLBACK` al salir."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()
