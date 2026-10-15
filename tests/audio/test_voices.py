"""Tests del registro de voces (AUD-01)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from frances.audio.voices import load_voices, validate_voices
from frances.errors import ConfigError
from frances.models.audio import Voice
from frances.paths import DataPaths

EXPECTED_DEFAULT_IDS = [
    "fr-FR-DeniseNeural",
    "fr-FR-EloiseNeural",
    "fr-FR-HenriNeural",
    "fr-FR-RemyMultilingualNeural",
    "fr-FR-VivienneMultilingualNeural",
    "fr-BE-CharlineNeural",
    "fr-BE-GerardNeural",
    "fr-CA-AntoineNeural",
    "fr-CA-JeanNeural",
    "fr-CA-SylvieNeural",
    "fr-CA-ThierryNeural",
    "fr-CH-ArianeNeural",
    "fr-CH-FabriceNeural",
    "synth-teen-f",
    "synth-teen-m",
    "synth-child-f",
    "synth-child-m",
]


def _write_user_yaml(root: Path, entries: list[dict[str, Any]]) -> None:
    (root / "voices.yaml").write_text(
        yaml.safe_dump({"voices": entries}, allow_unicode=True), encoding="utf-8"
    )


def _new_synthetic(voice_id: str) -> dict[str, Any]:
    return {
        "id": voice_id,
        "label": "X",
        "engine": "edge",
        "source": "synthetic",
        "derived_from": "fr-FR-EloiseNeural",
        "age": "teen",
        "gender": "female",
        "accent": "Francia",
        "pitch_hz": 10,
        "shift_ratio": 1.1,
    }


def test_defaults_are_13_builtin_plus_4_synthetic(tmp_path: Path) -> None:
    voices = load_voices(DataPaths(tmp_path))  # sin voices.yaml
    assert [v.id for v in voices] == EXPECTED_DEFAULT_IDS
    assert {v.engine for v in voices} == {"edge"}
    assert sum(v.source == "builtin" for v in voices) == 13
    assert sum(v.source == "synthetic" for v in voices) == 4
    assert all(v.enabled for v in voices)
    by_id = {v.id: v for v in voices}
    assert by_id["fr-FR-EloiseNeural"].age == "child"
    assert by_id["synth-child-m"].derived_from == "fr-FR-RemyMultilingualNeural"
    assert by_id["fr-FR-DeniseNeural"].label == "Denise · Francia · adulta"


def test_override_enabled_label_and_tuning(tmp_path: Path) -> None:
    _write_user_yaml(
        tmp_path,
        [
            {"id": "fr-CA-JeanNeural", "enabled": False, "label": "Jean (desactivada)"},
            {"id": "synth-teen-f", "pitch_hz": 30},
        ],
    )
    voices = load_voices(DataPaths(tmp_path))
    assert len(voices) == 17
    by_id = {v.id: v for v in voices}
    assert by_id["fr-CA-JeanNeural"].enabled is False
    assert by_id["fr-CA-JeanNeural"].label == "Jean (desactivada)"
    assert by_id["synth-teen-f"].pitch_hz == 30
    assert by_id["synth-teen-f"].shift_ratio == 1.08


def test_override_other_field_rejected(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path)
    _write_user_yaml(tmp_path, [{"id": "fr-FR-HenriNeural", "age": "teen"}])
    with pytest.raises(ConfigError):
        load_voices(paths)
    _write_user_yaml(tmp_path, [{"id": "fr-FR-HenriNeural", "pitch_hz": 10}])
    with pytest.raises(ConfigError):
        load_voices(paths)


def test_duplicate_ids_rejected(tmp_path: Path) -> None:
    _write_user_yaml(tmp_path, [_new_synthetic("synth-x"), _new_synthetic("synth-x")])
    with pytest.raises(ConfigError):
        load_voices(DataPaths(tmp_path))


def test_builtin_has_no_tuning(tmp_path: Path) -> None:
    defaults = load_voices(DataPaths(tmp_path))
    denise = next(v for v in defaults if v.id == "fr-FR-DeniseNeural")
    assert denise.pitch_hz == 0 and denise.shift_ratio == 1.0
    assert denise.derived_from is None
    with pytest.raises(ConfigError):
        validate_voices([*defaults, denise.model_copy(update={"pitch_hz": 10})])
    with pytest.raises(ConfigError):
        validate_voices([*defaults, denise.model_copy(update={"shift_ratio": 1.1})])
    with pytest.raises(ConfigError):
        validate_voices(
            [*defaults, denise.model_copy(update={"derived_from": "fr-FR-HenriNeural"})]
        )


def test_synthetic_must_derive_from_builtin(tmp_path: Path) -> None:
    defaults = load_voices(DataPaths(tmp_path))
    base: dict[str, Any] = {
        "id": "x",
        "label": "X",
        "engine": "edge",
        "age": "teen",
        "gender": "female",
        "accent": "Francia",
        "source": "synthetic",
    }
    for bad in (None, "no-existe", "synth-teen-m"):  # sin base, base inexistente, base sintética
        with pytest.raises(ConfigError):
            validate_voices([*defaults, Voice(**base, derived_from=bad)])
    validate_voices([*defaults, Voice(**base, derived_from="fr-FR-EloiseNeural")])  # no lanza


def test_tuning_ranges(tmp_path: Path) -> None:
    defaults = load_voices(DataPaths(tmp_path))

    def with_tuning(**kwargs: Any) -> list[Voice]:
        return [
            *defaults,
            Voice(
                id="y",
                label="Y",
                engine="edge",
                age="child",
                gender="female",
                accent="Francia",
                source="synthetic",
                derived_from="fr-FR-EloiseNeural",
                **kwargs,
            ),
        ]

    for bad_pitch in (101, -51):
        with pytest.raises(ConfigError):
            validate_voices(with_tuning(pitch_hz=bad_pitch))
    for bad_shift in (0.99, 1.36):
        with pytest.raises(ConfigError):
            validate_voices(with_tuning(shift_ratio=bad_shift))
    validate_voices(with_tuning(pitch_hz=-50, shift_ratio=1.0))
    validate_voices(with_tuning(pitch_hz=100, shift_ratio=1.35))
