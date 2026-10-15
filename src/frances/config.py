"""Configuración: TOML (``frances.toml``) + secretos solo por entorno."""

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from frances.errors import ConfigError
from frances.log import redact


class ClassroomSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_course_ids: list[str] = Field(default_factory=list)
    include_name_regex: str = "(?i)fran"
    max_download_mb: int = 50


class CardsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: Literal["auto", "off"] = "auto"
    llm_daily_item_limit: int = 30
    vocab_per_item_max: int = 25


class AudioSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixed_voices: list[str] = Field(
        default_factory=lambda: ["fr-FR-DeniseNeural", "fr-FR-HenriNeural"]
    )
    rotating: int = 1
    azure_tts_monthly_char_cap: int = 450000
    max_clips_per_run: int = 3000


class TranslatorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_char_cap: int = 1800000


class BundleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    salt: str = ""
    iterations: int = 600000
    max_total_mb: int = 900


class Settings(BaseModel):
    """Un atributo anidado por sección del TOML (R-08)."""

    model_config = ConfigDict(extra="forbid")

    classroom: ClassroomSettings = Field(default_factory=ClassroomSettings)
    cards: CardsSettings = Field(default_factory=CardsSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    translator: TranslatorSettings = Field(default_factory=TranslatorSettings)
    bundle: BundleSettings = Field(default_factory=BundleSettings)

    _env: Mapping[str, str] = PrivateAttr(default_factory=dict)

    def secret(self, name: str) -> str:
        """Secreto obligatorio del entorno; falta → ``ConfigError``."""
        value = self._env.get(name)
        if value is None:
            raise ConfigError(f"falta la variable {name}")
        return value

    def optional_secret(self, name: str) -> str | None:
        """Secreto opcional del entorno; falta → ``None``."""
        return self._env.get(name)


def load_settings(path: Path, env: Mapping[str, str]) -> Settings:
    """Carga el TOML; archivo inexistente → defaults.

    TOML inválido o claves/valores desconocidos → ``ConfigError`` (sin valores).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        settings = Settings()
        settings._env = dict(env)
        return settings
    except OSError as exc:
        raise ConfigError(f"no se pudo leer {path}: {redact(str(exc), env)}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML inválido en {path}: {redact(str(exc), env)}") from exc
    try:
        settings = Settings.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"config inválida en {path}: {redact(str(exc), env)}") from exc
    settings._env = dict(env)
    return settings
