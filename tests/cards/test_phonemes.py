"""Tests de fonemización espeak-ng y mapa a etiquetas Azure (CRD-06)."""

import json
import sqlite3

import pytest

from frances.cards.phoneme_map import ESPEAK_TO_AZURE
from frances.cards.phonemes import (
    espeak_ipa,
    ipa_display,
    run_phonemize,
    to_azure_phonemes,
)
from frances.models import card_id
from frances.stage import StageContext

NOW = "2026-10-14T10:17:00.000000Z"


def _card(ctx: StageContext, front_fr: str) -> str:
    """Inserta una tarjeta vocab sin IPA en el Store del contexto."""
    cid = card_id(front_fr, "vocab")
    with ctx.store.tx() as conn:
        conn.execute(
            "INSERT INTO cards (id, kind, front_fr, back_es, phonemes, tags, generator,"
            " generator_version, stale, created_at, updated_at)"
            " VALUES (?, 'vocab', ?, '', '[]', '[]', 'rules', '1', 0, ?, ?)",
            (cid, front_fr, NOW, NOW),
        )
    return cid


def _row(ctx: StageContext) -> sqlite3.Row:
    """Primera fila de `cards` con acceso por nombre."""
    ctx.store.conn.row_factory = sqlite3.Row
    row = ctx.store.conn.execute("SELECT * FROM cards ORDER BY id").fetchone()
    assert row is not None
    return row


def test_vent_has_nasal() -> None:
    assert "ɑ̃" in espeak_ipa(["vent"])[0]  # noqa: RUF001


def test_allez_has_closed_e() -> None:
    assert ESPEAK_TO_AZURE["e"] in to_azure_phonemes(espeak_ipa(["allez"])[0])


def test_rouge_has_uvular_r() -> None:
    assert "ʁ" in espeak_ipa(["rouge"])[0]


def test_batch_one_line_per_text() -> None:
    assert len(espeak_ipa(["vent", "Bonjour, ça va ?", "l'école"])) == 3


def test_multichar_tokens_first() -> None:
    assert to_azure_phonemes("vɑ̃") == ["v", ESPEAK_TO_AZURE["ɑ̃"]]  # noqa: RUF001


def test_strips_stress_length_and_separators() -> None:
    assert to_azure_phonemes("ˈaːl‿e") == [ESPEAK_TO_AZURE[c] for c in "ale"]  # noqa: RUF001


def test_unknown_symbol_raises() -> None:
    with pytest.raises(ValueError, match="ʘ"):
        to_azure_phonemes("ʘ")


@pytest.mark.parametrize(
    "word",
    ["vent", "vont", "vin", "allez", "était", "rouge", "brun", "fille", "huit", "oui"],
)
def test_every_label_is_mapped(word: str) -> None:
    assert set(to_azure_phonemes(espeak_ipa([word])[0])) <= set(ESPEAK_TO_AZURE.values())


def test_run_phonemize_fills_and_is_idempotent(ctx: StageContext) -> None:
    _card(ctx, "le vent")
    assert run_phonemize(ctx).counts["phonemize.updated"] == 1
    assert run_phonemize(ctx).counts["phonemize.updated"] == 0
    row = _row(ctx)
    assert row["ipa"].startswith("v1|")
    assert ESPEAK_TO_AZURE["ɑ̃"] in json.loads(row["phonemes"])  # noqa: RUF001


def test_map_version_change_refills(ctx: StageContext, monkeypatch: pytest.MonkeyPatch) -> None:
    _card(ctx, "le vent")
    assert run_phonemize(ctx).counts["phonemize.updated"] == 1
    monkeypatch.setattr("frances.cards.phonemes.PHONEME_MAP_VERSION", "2")
    assert run_phonemize(ctx).counts["phonemize.updated"] == 1
    assert _row(ctx)["ipa"].startswith("v2|")


def test_ipa_display() -> None:
    assert ipa_display("v1|ʁuʒ") == "ʁuʒ"
    assert ipa_display(None) is None
