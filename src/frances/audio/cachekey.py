"""Clave de caché de audio por familia de motor (AUD-02, R-15)."""

import hashlib
import json

from frances.models.audio import AudioRequest, EngineFamily, Voice
from frances.textnorm import tts_norm

FAMILY_VERSION: dict[EngineFamily, str] = {"ms-neural": "1"}


def family_of(voice: Voice) -> EngineFamily:
    """Familia del motor: Edge y Azure comparten la voz neural ``ms-neural``."""
    _ = voice
    return "ms-neural"


def audio_cache_key(text: str, voice: Voice) -> str:
    """Hash de 32 hex de ``{texto norm, voz, familia, versión, afinación}``."""
    family = family_of(voice)
    payload = {
        "t": tts_norm(text),
        "v": voice.id,
        "f": family,
        "fv": FAMILY_VERSION[family],
        "p": voice.pitch_hz,
        "s": voice.shift_ratio,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def audio_request(text: str, voice: Voice) -> AudioRequest:
    """Construye el ``AudioRequest`` listo para ``insert_pending``."""
    family = family_of(voice)
    return AudioRequest(
        cache_key=audio_cache_key(text, voice),
        text=text,
        text_norm=tts_norm(text),
        voice_id=voice.id,
        family=family,
        family_version=FAMILY_VERSION[family],
    )
