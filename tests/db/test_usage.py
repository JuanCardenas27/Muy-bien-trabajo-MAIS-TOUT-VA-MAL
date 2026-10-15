"""Tests de medidores de uso y registro de etapas."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from frances.db.store import Store
from frances.db.usage import current_month, record_run, usage_add, usage_get
from frances.stage import StageReport
from frances.timeutil import parse_ts

NOW = "2026-10-14T15:20:24.000000Z"


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    s = Store.open(tmp_path / "s.db")
    yield s
    s.close()


def test_usage_add_accumulates(store: Store) -> None:
    assert usage_get(store.conn, "2026-10", "azure_tts_chars") == 0
    assert usage_add(store.conn, "2026-10", "azure_tts_chars", 100) == 100
    assert usage_add(store.conn, "2026-10", "azure_tts_chars", 50) == 150


def test_current_month_bogota_boundary() -> None:
    assert current_month(parse_ts("2026-11-01T03:00:00Z")) == "2026-10"
    assert current_month(parse_ts("2026-11-01T05:00:00Z")) == "2026-11"


def test_record_run(store: Store) -> None:
    report = StageReport("sync", "partial", {"items": 3}, ["x"])
    record_run(store.conn, report, NOW, NOW)
    row = store.conn.execute("SELECT stage, status, stats FROM runs").fetchone()
    assert row == ("sync", "partial", '{"counts":{"items":3},"errors":["x"]}')
