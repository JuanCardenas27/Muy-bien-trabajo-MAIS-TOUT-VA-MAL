"""Fonemización con espeak-ng y mapeo a etiquetas canónicas (CRD-06).

``espeak_ipa`` llama a ``espeak-ng -q -v fr-fr --ipa`` por subprocess (nunca
``shell=True``) y ``to_azure_phonemes`` traduce su salida a las etiquetas IPA
en NFC de ADR-004. ``run_phonemize`` rellena ``cards.ipa`` (con prefijo de
versión, R-12) y ``cards.phonemes`` de forma idempotente.
"""

import json
import sqlite3
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

import typer

from frances.cards.phoneme_map import ESPEAK_TO_AZURE, IGNORED, PHONEME_MAP_VERSION
from frances.cli import DataOpt, exit_with
from frances.db.usage import record_run
from frances.log import redact
from frances.stage import StageContext, StageReport, make_context
from frances.textnorm import tts_norm
from frances.timeutil import format_ts

_ESPEAK_CMD = ("espeak-ng", "-q", "-v", "fr-fr", "--ipa")
_SORTED_KEYS: tuple[str, ...] = tuple(sorted(ESPEAK_TO_AZURE, key=len, reverse=True))
BATCH_SIZE = 200


def espeak_ipa(texts: list[str]) -> list[str]:
    """IPA de cada texto, una salida por entrada (misma longitud que ``texts``).

    Un texto sin caracteres alfanuméricos (``…``, ``?``, emoji) devuelve ``""``
    sin pasar por espeak-ng, que no emite línea para él. El resto va en una sola
    llamada separado por saltos de línea; como cada texto alfanumérico produce al
    menos una línea, el lote solo se acepta si hay exactamente una por texto. Si
    no (la puntuación inserta pausas), repite con una llamada por texto y une sus
    líneas con espacio, de modo que el resultado siempre queda alineado.
    """
    prepared = [tts_norm(text).replace("\n", " ") for text in texts]
    spoken = [index for index, text in enumerate(prepared) if _has_alnum(text)]
    ipas = [""] * len(texts)
    if not spoken:
        return ipas
    result = subprocess.run(
        list(_ESPEAK_CMD),
        input="\n".join(prepared[index] for index in spoken),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    lines = _nonempty_lines(result.stdout)
    if len(lines) != len(spoken):
        lines = [_phonemize_one(prepared[index]) for index in spoken]
    for index, line in zip(spoken, lines, strict=True):
        ipas[index] = line
    return ipas


def to_azure_phonemes(ipa: str) -> list[str]:
    """Etiquetas canónicas del IPA dado; ``ValueError`` con el símbolo si falta.

    Recorre en NFC y prueba las claves de mayor a menor longitud, de modo que las
    secuencias multichar (nasales) ganan a sus bases; salta los símbolos de
    ``IGNORED`` (acentos, longitud, separadores).
    """
    text = unicodedata.normalize("NFC", ipa)
    labels: list[str] = []
    index = 0
    while index < len(text):
        for key in _SORTED_KEYS:
            if text.startswith(key, index):
                labels.append(ESPEAK_TO_AZURE[key])
                index += len(key)
                break
        else:
            symbol = text[index]
            if symbol in IGNORED:
                index += 1
                continue
            raise ValueError(f"símbolo de fonema no mapeado: {symbol!r}")
    return labels


def ipa_display(stored: str | None) -> str | None:
    """IPA sin el prefijo de versión ``v<n>|`` (R-12)."""
    return None if stored is None else stored.split("|", 1)[-1]


def run_phonemize(ctx: StageContext) -> StageReport:
    """Rellena ``ipa`` y ``phonemes`` de las tarjetas que los necesitan.

    Clave de cambio: ``phonemize.updated`` (R-09). Una tarjeta cuyo IPA tenga un
    símbolo desconocido va a ``errors`` y deja ``ipa`` en NULL (status ``partial``).
    """
    report = StageReport(stage="phonemize", status="ok")
    report.counts = {"phonemize.updated": 0}
    started_at = format_ts(ctx.now())
    last_id = ""
    while True:
        rows = _q_cards_needing_ipa(ctx.store.conn, PHONEME_MAP_VERSION, last_id, BATCH_SIZE)
        if not rows:
            break
        _process_batch(ctx, rows, report)
        last_id = str(rows[-1][0])
    if report.errors:
        report.status = "partial"
    with ctx.store.tx() as conn:
        record_run(conn, report, started_at, format_ts(ctx.now()))
    return report


def _nonempty_lines(output: str) -> list[str]:
    """Líneas de la salida de espeak-ng sin vacías y recortadas."""
    return [line.strip() for line in output.splitlines() if line.strip()]


def _has_alnum(text: str) -> bool:
    """``True`` si el texto tiene al menos un carácter alfanumérico."""
    return any(char.isalnum() for char in text)


def _phonemize_one(text: str) -> str:
    """IPA de un solo texto; sus líneas (pausas) se unen con espacio."""
    result = subprocess.run(
        list(_ESPEAK_CMD),
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return " ".join(_nonempty_lines(result.stdout))


def _process_batch(ctx: StageContext, rows: list[Any], report: StageReport) -> None:
    """Fonemiza un lote de tarjetas y escribe las que se pudieron mapear."""
    fronts = [str(row[1]) for row in rows]
    try:
        ipas = espeak_ipa(fronts)
    except Exception as exc:  # un fallo del binario no corta la etapa
        report.errors.append(redact(str(exc), ctx.env))
        return
    updates: list[tuple[str, str, str]] = []
    failed: list[tuple[str]] = []
    for row, ipa in zip(rows, ipas, strict=True):
        card = str(row[0])
        try:
            labels = to_azure_phonemes(ipa)
        except ValueError as exc:
            report.errors.append(f"{card}: {exc}")
            failed.append((card,))
            continue
        unique = list(dict.fromkeys(labels))
        updates.append(
            (f"v{PHONEME_MAP_VERSION}|{ipa}", json.dumps(unique, ensure_ascii=False), card)
        )
    if not updates and not failed:
        return
    with ctx.store.tx() as conn:
        _q_update_ipa(conn, updates)
        _q_clear_ipa(conn, failed)
    report.counts["phonemize.updated"] += len(updates)


def _q_cards_needing_ipa(
    conn: sqlite3.Connection, version: str, after: str, limit: int
) -> list[Any]:
    """Tarjetas con ``ipa`` NULL o de otra versión, por ``id`` creciente (keyset)."""
    rows = conn.execute(
        "SELECT id, front_fr FROM cards WHERE (ipa IS NULL OR ipa NOT LIKE ?) AND id > ?"
        " ORDER BY id LIMIT ?",
        (f"v{version}|%", after, limit),
    ).fetchall()
    return list(rows)


def _q_update_ipa(conn: sqlite3.Connection, updates: list[tuple[str, str, str]]) -> None:
    """Escribe ``ipa`` y ``phonemes`` de cada tarjeta del lote."""
    conn.executemany("UPDATE cards SET ipa = ?, phonemes = ? WHERE id = ?", updates)


def _q_clear_ipa(conn: sqlite3.Connection, cards: list[tuple[str]]) -> None:
    """Deja ``ipa`` en NULL en las tarjetas cuyo IPA no se pudo mapear."""
    conn.executemany("UPDATE cards SET ipa = NULL WHERE id = ? AND ipa IS NOT NULL", cards)


def register(app: typer.Typer) -> None:
    """Registra ``frances phonemize [--data DIR]`` (R-05)."""

    @app.command()
    def phonemize(data: DataOpt = Path(".")) -> None:
        """Calcula el IPA y las etiquetas de fonema de cada tarjeta."""
        exit_with(lambda: run_phonemize(make_context(data)))
