"""Tests de la política de voces y plan_audio (AUD-02)."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from frances.audio.policy import plan_audio, voices_for
from frances.config import Settings
from frances.db.store import Store
from frances.models.audio import Voice
from frances.paths import DataPaths

NOW = "2026-10-14T15:20:24.000000Z"


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    s = Store.open(tmp_path / "policy.db")
    yield s
    s.close()


def _voice(voice_id: str, enabled: bool = True, **extra: Any) -> Voice:
    data: dict[str, Any] = {
        "id": voice_id,
        "label": voice_id,
        "engine": "edge",
        "age": "adult",
        "gender": "female",
        "accent": "Francia",
        "enabled": enabled,
    }
    data.update(extra)
    return Voice(**data)


def _three_voices() -> list[Voice]:
    return [
        _voice("fr-FR-DeniseNeural"),
        _voice("fr-FR-HenriNeural"),
        _voice("fr-FR-VivienneMultilingualNeural"),
    ]


def _settings(**over: Any) -> Settings:
    s = Settings()
    for key, value in over.items():
        setattr(s.audio, key, value)
    return s


def _insert_card(
    store: Store,
    card_id: str,
    kind: str = "vocab",
    front: str = "Bonjour",
    example: str | None = "Je dis bonjour",
    stale: int = 0,
) -> None:
    with store.tx() as conn:
        conn.execute(
            "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                card_id,
                kind,
                front,
                "Hola",
                example,
                "Digo hola" if example else None,
                None,
                None,
                "[]",
                "[]",
                "rules",
                "1",
                stale,
                NOW,
                NOW,
            ),
        )


def _audio_counts(store: Store) -> tuple[int, int]:
    n_audio = store.conn.execute("SELECT count(*) FROM audio").fetchone()[0]
    n_links = store.conn.execute("SELECT count(*) FROM card_audio").fetchone()[0]
    return (n_audio, n_links)


def test_front_gets_fixed_plus_one_rotating() -> None:
    voices = _three_voices()
    settings = _settings()
    got = voices_for("c_abc", "vocab", "front", voices, settings)
    assert [v.id for v in got][:2] == ["fr-FR-DeniseNeural", "fr-FR-HenriNeural"]
    assert len(got) == 3
    assert got[2].id == "fr-FR-VivienneMultilingualNeural"


def test_rotation_is_deterministic() -> None:
    voices = [_voice("fr-FR-DeniseNeural"), _voice("fr-FR-HenriNeural")]
    voices += [_voice(f"v-extra-{i:02d}") for i in range(10)]
    settings = _settings()
    first = voices_for("c_same", "vocab", "front", voices, settings)
    assert voices_for("c_same", "vocab", "front", voices, settings) == first
    seen = {
        voices_for(f"c_{i:03d}", "vocab", "front", voices, settings)[-1].id
        for i in range(200)
    }
    assert len(seen) >= 5


def test_drill_front_uses_all_enabled(tmp_path: Path) -> None:
    from frances.audio.voices import load_voices

    voices = load_voices(DataPaths(tmp_path))
    assert len(voices) == 17
    settings = _settings()
    got = voices_for("c_drill", "drill", "front", voices, settings)
    assert len(got) == 17
    assert [v.id for v in got] == sorted(v.id for v in voices)
    disabled = [v.model_copy(update={"enabled": False}) if v.id == "fr-CA-JeanNeural" else v
                for v in voices]
    got2 = voices_for("c_drill", "drill", "front", disabled, settings)
    assert len(got2) == 16
    assert "fr-CA-JeanNeural" not in {v.id for v in got2}


def test_example_uses_first_fixed_only() -> None:
    voices = _three_voices()
    settings = _settings()
    got = voices_for("c_x", "vocab", "example", voices, settings)
    assert [v.id for v in got] == ["fr-FR-DeniseNeural"]
    got_drill = voices_for("c_x", "drill", "example", voices, settings)
    assert [v.id for v in got_drill] == ["fr-FR-DeniseNeural"]


def test_example_skips_missing_and_disabled_fixed() -> None:
    voices = [_voice("fr-FR-HenriNeural"), _voice("fr-FR-VivienneMultilingualNeural")]
    settings = _settings(fixed_voices=["no-existe", "fr-FR-HenriNeural"])
    assert [v.id for v in voices_for("c_x", "vocab", "example", voices, settings)] == [
        "fr-FR-HenriNeural"
    ]
    voices_off = [_voice("fr-FR-DeniseNeural", enabled=False), _voice("fr-FR-HenriNeural")]
    got = voices_for("c_x", "vocab", "example", voices_off, _settings())
    assert [v.id for v in got] == ["fr-FR-HenriNeural"]


def test_disabled_rotating_voice_never_chosen() -> None:
    voices = [
        _voice("fr-FR-DeniseNeural"),
        _voice("fr-FR-HenriNeural"),
        _voice("fr-FR-VivienneMultilingualNeural", enabled=False),
    ]
    settings = _settings()
    for i in range(50):
        got = voices_for(f"c_{i}", "vocab", "front", voices, settings)
        assert "fr-FR-VivienneMultilingualNeural" not in {v.id for v in got}
    assert all(len(voices_for(f"c_{i}", "vocab", "front", voices, settings)) == 2
               for i in range(5))


def test_plan_audio_creates_pending_and_links(store: Store) -> None:
    _insert_card(store, "c_plan1")
    settings = _settings()
    created = plan_audio(store, _three_voices(), settings, NOW)
    assert created == 4
    assert _audio_counts(store) == (4, 4)
    rows = store.conn.execute("SELECT DISTINCT status FROM audio").fetchall()
    assert rows == [("pending",)]


def test_plan_audio_is_idempotent(store: Store) -> None:
    _insert_card(store, "c_plan2")
    voices = _three_voices()
    settings = _settings()
    assert plan_audio(store, voices, settings, NOW) == 4
    assert plan_audio(store, voices, settings, NOW) == 0
    assert _audio_counts(store) == (4, 4)


def test_plan_audio_prunes_links_not_rows(store: Store) -> None:
    _insert_card(store, "c_plan3")
    settings = _settings()
    voices = _three_voices()
    assert plan_audio(store, voices, settings, NOW) == 4
    pruned_voices = [
        _voice("fr-FR-DeniseNeural"),
        _voice("fr-FR-HenriNeural"),
        _voice("fr-FR-VivienneMultilingualNeural", enabled=False),
    ]
    assert plan_audio(store, pruned_voices, settings, NOW) == 0
    # El enlace de la voz rotativa se borra pero su fila audio sigue.
    assert _audio_counts(store) == (4, 3)
    remaining = {r[0] for r in store.conn.execute("SELECT voice_id FROM audio").fetchall()}
    assert "fr-FR-VivienneMultilingualNeural" in remaining


def test_plan_audio_skips_stale_cards(store: Store) -> None:
    _insert_card(store, "c_stale", stale=1)
    _insert_card(store, "c_fresh", front="Salut")
    created = plan_audio(store, _three_voices(), _settings(), NOW)
    assert created == 4
    assert _audio_counts(store) == (4, 4)
    assert store.conn.execute(
        "SELECT count(*) FROM card_audio WHERE card_id = 'c_stale'"
    ).fetchone()[0] == 0
