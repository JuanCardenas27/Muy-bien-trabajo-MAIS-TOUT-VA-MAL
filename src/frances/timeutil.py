"""Timestamps: siempre UTC con 6 decimales (R-06, Global Constraints)."""

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")

_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$")
_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _parse_aware(raw: str) -> datetime:
    match = _TS_RE.match(raw)
    if match is None:
        raise ValueError(f"timestamp inválido (se esperaba ISO 8601 con zona): {raw!r}")
    base, fraction, zone = match.group(1), match.group(2) or "", match.group(3)
    frac6 = (fraction + "000000")[:6]
    suffix = "+00:00" if zone == "Z" else zone
    try:
        parsed = datetime.fromisoformat(f"{base}.{frac6}{suffix}")
    except ValueError as exc:
        raise ValueError(f"timestamp inválido: {raw!r}") from exc
    if parsed.tzinfo is None:  # pragma: no cover - el regex ya exige zona
        raise ValueError(f"timestamp sin zona horaria: {raw!r}")
    return parsed


def norm_ts(raw: str) -> str:
    """Normaliza un ISO 8601 con zona a ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (UTC).

    La fracción se trunca o rellena a 6 dígitos. Sin zona → ``ValueError``.
    """
    return _parse_aware(raw).astimezone(UTC).strftime(_TS_FORMAT)


def parse_ts(raw: str) -> datetime:
    """Parsea un ISO 8601 con zona y lo devuelve aware en UTC."""
    return _parse_aware(raw).astimezone(UTC)


def format_ts(moment: datetime) -> str:
    """Formatea un datetime aware igual que :func:`norm_ts`; naive → ``ValueError``."""
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError("datetime naive sin zona horaria")
    return moment.astimezone(UTC).strftime(_TS_FORMAT)


def now_utc() -> datetime:
    """Ahora, aware en UTC."""
    return datetime.now(UTC)


def to_bogota(moment: datetime) -> datetime:
    """Convierte un datetime aware a America/Bogota (para mostrar)."""
    return moment.astimezone(BOGOTA)
