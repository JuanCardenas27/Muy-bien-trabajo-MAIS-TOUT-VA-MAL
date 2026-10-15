from datetime import datetime, timezone

import pytest

from frances.timeutil import BOGOTA, format_ts, norm_ts, now_utc, parse_ts, to_bogota


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-14T15:20:24Z", "2026-10-14T15:20:24.000000Z"),
        ("2026-10-14T15:20:24.898Z", "2026-10-14T15:20:24.898000Z"),
        ("2026-10-14T15:20:24.045123456Z", "2026-10-14T15:20:24.045123Z"),
        ("2026-10-14T10:20:24-05:00", "2026-10-14T15:20:24.000000Z"),
        ("2026-10-14T15:20:24+00:00", "2026-10-14T15:20:24.000000Z"),
    ],
)
def test_norm_ts_variable_fraction_digits(raw: str, expected: str) -> None:
    assert norm_ts(raw) == expected


def test_norm_ts_rejects_naive() -> None:
    with pytest.raises(ValueError):
        norm_ts("2026-10-14T15:20:24")


def test_norm_ts_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        norm_ts("ayer a las tres")


def test_format_ts() -> None:
    dt = datetime(2026, 10, 14, 10, 20, 24, 898000, tzinfo=BOGOTA)
    assert format_ts(dt) == "2026-10-14T15:20:24.898000Z"


def test_format_ts_rejects_naive() -> None:
    with pytest.raises(ValueError):
        format_ts(datetime(2026, 10, 14, 15, 20, 24))


def test_to_bogota() -> None:
    assert to_bogota(parse_ts("2026-11-01T03:00:00Z")).isoformat() == "2026-10-31T22:00:00-05:00"


def test_parse_ts_is_aware_utc() -> None:
    dt = parse_ts("2026-10-14T15:20:24Z")
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(None)
    assert norm_ts("2026-10-14T15:20:24Z") == format_ts(dt)


def test_now_utc_is_aware_utc() -> None:
    now = now_utc()
    assert now.tzinfo is not None
    assert now.utcoffset() == timezone.utc.utcoffset(None)
