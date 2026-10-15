"""Tests de la clave de cache de audio (AUD-02)."""

import unicodedata
from typing import Any

from frances.audio.cachekey import (
    FAMILY_VERSION,
    audio_cache_key,
    audio_request,
    family_of,
)
from frances.models.audio import Voice

CURLY = chr(0x2019)


def _voice(
    voice_id: str,
    engine: str = "edge",
    pitch_hz: int = 0,
    shift_ratio: float = 1.0,
    **extra: Any,
) -> Voice:
    data: dict[str, Any] = {
        "id": voice_id,
        "label": voice_id,
        "engine": engine,
        "age": "adult",
        "gender": "female",
        "accent": "Francia",
        "source": "builtin",
        "pitch_hz": pitch_hz,
        "shift_ratio": shift_ratio,
    }
    data.update(extra)
    return Voice(**data)


def _denise() -> Voice:
    return _voice("fr-FR-DeniseNeural")


def _henri() -> Voice:
    return _voice("fr-FR-HenriNeural", gender="male")


def test_cache_key_typography_invariant() -> None:
    denise, henri = _denise(), _henri()
    k = audio_cache_key("l'école", denise)
    assert audio_cache_key("l" + CURLY + "école", denise) == k
    assert audio_cache_key(unicodedata.normalize("NFD", "l'école"), denise) == k
    assert audio_cache_key("l" + CURLY + "école", henri) != k
    assert len(k) == 32 and all(c in "0123456789abcdef" for c in k)


def test_cache_key_keeps_case_and_punctuation() -> None:
    denise = _denise()
    assert audio_cache_key("Allez !", denise) != audio_cache_key("allez", denise)
    assert audio_cache_key("Bonjour.", denise) != audio_cache_key("Bonjour", denise)


def test_edge_and_azure_share_family() -> None:
    edge = _voice("fr-FR-DeniseNeural", engine="edge")
    azure = _voice("fr-FR-DeniseNeural", engine="azure")
    assert family_of(edge) == "ms-neural"
    assert family_of(azure) == "ms-neural"
    assert audio_cache_key("Bonjour", edge) == audio_cache_key("Bonjour", azure)


def test_family_version_bump_changes_key(monkeypatch: Any) -> None:
    denise = _denise()
    before = audio_cache_key("Bonjour", denise)
    monkeypatch.setitem(FAMILY_VERSION, "ms-neural", "2")
    assert audio_cache_key("Bonjour", denise) != before


def test_synthetic_tuning_changes_key() -> None:
    base = _voice(
        "synth-teen-f",
        source="synthetic",
        derived_from="fr-FR-VivienneMultilingualNeural",
        pitch_hz=20,
        shift_ratio=1.08,
    )
    other_pitch = base.model_copy(update={"pitch_hz": 21})
    other_shift = base.model_copy(update={"shift_ratio": 1.09})
    assert audio_cache_key("Bonjour", other_pitch) != audio_cache_key("Bonjour", base)
    assert audio_cache_key("Bonjour", other_shift) != audio_cache_key("Bonjour", base)


def test_audio_request_fields() -> None:
    denise = _denise()
    curly_text = "l" + CURLY + "école"
    req = audio_request(curly_text, denise)
    assert req.text == curly_text
    assert req.text_norm == "l'école"
    assert req.voice_id == "fr-FR-DeniseNeural"
    assert req.family == "ms-neural"
    assert req.family_version == "1"
    assert req.cache_key == audio_cache_key(curly_text, denise)
