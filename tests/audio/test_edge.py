"""Motor Edge-TTS: tests del engine y del mapeo de errores (AUD-03)."""

import asyncio
from pathlib import Path
from typing import Any, Literal

import aiohttp
import pytest
from edge_tts.exceptions import NoAudioReceived

from frances.audio.edge import EdgeEngine, EngineError
from frances.models.audio import Voice, VoiceAge


def make_voice(
    voice_id: str,
    *,
    source: Literal["builtin", "synthetic"] = "builtin",
    derived_from: str | None = None,
    pitch_hz: int = 0,
    shift_ratio: float = 1.0,
    gender: Literal["female", "male"] = "female",
    age: VoiceAge = "adult",
) -> Voice:
    return Voice(
        id=voice_id,
        label=voice_id,
        engine="edge",
        age=age,
        gender=gender,
        accent="Francia",
        source=source,
        derived_from=derived_from,
        pitch_hz=pitch_hz,
        shift_ratio=shift_ratio,
    )


class CallLog(list[tuple[str, str, str]]):
    """Llamadas a Communicate como (text, voice, out) más los kwargs en .kwargs."""

    def __init__(self) -> None:
        super().__init__()
        self.kwargs: list[dict[str, Any]] = []


def fake_communicate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    writes: bytes = b"ID3fake",
    raises: BaseException | None = None,
) -> CallLog:
    """Sustituye edge_tts.Communicate por un doble que graba llamadas."""
    calls = CallLog()

    class FakeCommunicate:
        def __init__(self, text: str, voice: str, **kwargs: Any) -> None:
            self._text = text
            self._voice = voice
            self._kwargs = kwargs

        async def save(self, output: str) -> None:
            calls.append((self._text, self._voice, str(output)))
            calls.kwargs.append(dict(self._kwargs))
            if raises is not None:
                raise raises
            Path(output).write_bytes(writes)

    monkeypatch.setattr("edge_tts.Communicate", FakeCommunicate)
    return calls


def test_synthesize_calls_communicate_with_voice_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = fake_communicate(monkeypatch, writes=b"ID3fake")
    asyncio.run(
        EdgeEngine().synthesize(
            "Bonjour", make_voice("fr-FR-DeniseNeural"), tmp_path / "a.mp3"
        )
    )
    assert calls == [("Bonjour", "fr-FR-DeniseNeural", str(tmp_path / "a.mp3"))]


def test_network_error_is_retryable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_communicate(monkeypatch, raises=aiohttp.ClientError("boom"))
    with pytest.raises(EngineError) as exc_info:
        asyncio.run(
            EdgeEngine().synthesize(
                "Bonjour", make_voice("fr-FR-DeniseNeural"), tmp_path / "a.mp3"
            )
        )
    assert exc_info.value.retryable is True


def test_unknown_voice_not_retryable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_communicate(monkeypatch, raises=NoAudioReceived("no audio received"))
    with pytest.raises(EngineError) as exc_info:
        asyncio.run(
            EdgeEngine().synthesize(
                "Bonjour", make_voice("fr-FR-DeniseNeural"), tmp_path / "a.mp3"
            )
        )
    assert exc_info.value.retryable is False


def test_empty_output_not_retryable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_communicate(monkeypatch, writes=b"")
    with pytest.raises(EngineError) as exc_info:
        asyncio.run(
            EdgeEngine().synthesize(
                "Bonjour", make_voice("fr-FR-DeniseNeural"), tmp_path / "a.mp3"
            )
        )
    assert exc_info.value.retryable is False


def test_family_matches_family_version_table() -> None:
    cachekey = pytest.importorskip("frances.audio.cachekey")
    engine = EdgeEngine()
    assert engine.family == "ms-neural"
    assert engine.family_version == cachekey.FAMILY_VERSION[engine.family]


def test_synthetic_voice_uses_base_voice_and_pitch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = fake_communicate(monkeypatch, writes=b"ID3fake")
    child_m = make_voice(
        "synth-child-m",
        source="synthetic",
        derived_from="fr-FR-RemyMultilingualNeural",
        pitch_hz=60,
        shift_ratio=1.25,
        gender="male",
        age="child",
    )
    asyncio.run(EdgeEngine().synthesize("Bonjour", child_m, tmp_path / "a.mp3"))
    assert calls == [
        ("Bonjour", "fr-FR-RemyMultilingualNeural", str(tmp_path / "a.mp3"))
    ]
    assert calls.kwargs == [{"pitch": "+60Hz"}]


@pytest.mark.heavy
def test_real_edge_smoke(tmp_path: Path) -> None:
    out = tmp_path / "smoke.mp3"
    asyncio.run(
        EdgeEngine().synthesize("Bonjour", make_voice("fr-FR-DeniseNeural"), out)
    )
    assert out.stat().st_size > 1024
