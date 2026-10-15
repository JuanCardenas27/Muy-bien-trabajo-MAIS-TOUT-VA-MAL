"""Contratos de audio: voces y peticiones de síntesis (plan maestro)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

VoiceAge = Literal["adult", "teen", "child"]
Engine = Literal["edge", "azure"]
EngineFamily = Literal["ms-neural"]


class Voice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    engine: Engine
    age: VoiceAge
    gender: Literal["female", "male"]
    accent: str
    enabled: bool = True
    source: Literal["builtin", "synthetic"] = "builtin"
    derived_from: str | None = None
    pitch_hz: int = 0
    shift_ratio: float = 1.0


class AudioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cache_key: str
    text: str
    text_norm: str
    voice_id: str
    family: EngineFamily
    family_version: str
