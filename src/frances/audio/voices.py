"""Registro de voces: 13 Edge builtin + voces jóvenes sintéticas (AUD-01)."""

from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from frances.errors import ConfigError
from frances.models.audio import Voice
from frances.paths import DataPaths

DEFAULT_VOICES_FILE: Path = Path(__file__).with_name("voices_default.yaml")
PITCH_HZ_RANGE: tuple[int, int] = (-50, 100)
SHIFT_RATIO_RANGE: tuple[float, float] = (1.0, 1.35)

_OVERRIDE_KEYS: frozenset[str] = frozenset({"id", "enabled", "label", "pitch_hz", "shift_ratio"})


def _read_entries(path: Path) -> list[dict[str, Any]]:
    """Lee un YAML con forma `voices: [...]`; error de lectura o forma → ``ConfigError``."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"no se pudo leer {path}: {exc}") from exc
    try:
        doc: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML inválido en {path}: {exc}") from exc
    if doc is None:
        return []
    if not isinstance(doc, dict):
        raise ConfigError(f"formato inválido en {path}: se esperaba un mapa con `voices:`")
    raw: Any = doc.get("voices", [])
    if not isinstance(raw, list):
        raise ConfigError(f"formato inválido en {path}: `voices` debe ser una lista")
    entries: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ConfigError(f"formato inválido en {path}: cada voz debe ser un mapa")
        entries.append(cast("dict[str, Any]", item))
    return entries


def _parse_voice(entry: dict[str, Any], path: Path) -> Voice:
    """Valida una entrada completa como ``Voice``.

    Un ``ValidationError`` de pydantic se re-lanza como ``ConfigError`` con el id.
    """
    try:
        return Voice.model_validate(entry)
    except ValidationError as exc:
        raise ConfigError(f"voz inválida {entry.get('id', '?')!r} en {path}: {exc}") from exc


def _apply_override(base: Voice, entry: dict[str, Any], path: Path) -> Voice:
    """Aplica un ajuste parcial sobre una voz de los defaults.

    Solo se permiten `enabled`, `label` y —en voces sintéticas— `pitch_hz`
    y `shift_ratio`; cualquier otra clave → ``ConfigError``.
    """
    extra = set(entry) - _OVERRIDE_KEYS
    if extra:
        allowed = sorted(_OVERRIDE_KEYS - {"id"})
        raise ConfigError(
            f"voz {base.id!r} en {path}: solo se puede ajustar {allowed}; "
            f"claves no permitidas: {sorted(extra)}"
        )
    if ("pitch_hz" in entry or "shift_ratio" in entry) and base.source != "synthetic":
        raise ConfigError(
            f"voz {base.id!r} en {path}: pitch_hz/shift_ratio solo en voces sintéticas"
        )
    data = base.model_dump()
    for key in ("enabled", "label", "pitch_hz", "shift_ratio"):
        if key in entry:
            data[key] = entry[key]
    return _parse_voice(data, path)


def validate_voices(voices: list[Voice]) -> None:
    """Valida el registro completo; cualquier problema → ``ConfigError``.

    Reglas: sin ids duplicados; `pitch_hz` en ``PITCH_HZ_RANGE`` y `shift_ratio`
    en ``SHIFT_RATIO_RANGE``; las builtin no traen afinación (`pitch_hz == 0`,
    `shift_ratio == 1.0`, sin `derived_from`); cada sintética deriva de una
    builtin existente (nunca se encadenan transformaciones).
    """
    seen: set[str] = set()
    for voice in voices:
        if voice.id in seen:
            raise ConfigError(f"voz duplicada: {voice.id!r}")
        seen.add(voice.id)
    by_id = {voice.id: voice for voice in voices}
    lo_pitch, hi_pitch = PITCH_HZ_RANGE
    lo_shift, hi_shift = SHIFT_RATIO_RANGE
    for voice in voices:
        if not lo_pitch <= voice.pitch_hz <= hi_pitch:
            raise ConfigError(
                f"voz {voice.id!r}: pitch_hz={voice.pitch_hz} fuera de rango "
                f"[{lo_pitch}, {hi_pitch}]"
            )
        if not lo_shift <= voice.shift_ratio <= hi_shift:
            raise ConfigError(
                f"voz {voice.id!r}: shift_ratio={voice.shift_ratio} fuera de rango "
                f"[{lo_shift}, {hi_shift}]"
            )
        if voice.source == "builtin":
            if voice.pitch_hz != 0 or voice.shift_ratio != 1.0 or voice.derived_from is not None:
                raise ConfigError(
                    f"voz builtin {voice.id!r}: no puede traer pitch_hz/shift_ratio/derived_from"
                )
        elif (
            voice.derived_from is None
            or voice.derived_from not in by_id
            or by_id[voice.derived_from].source != "builtin"
        ):
            raise ConfigError(
                f"voz sintética {voice.id!r}: derived_from debe ser una voz builtin existente"
            )


def load_voices(paths: DataPaths) -> list[Voice]:
    """Carga los defaults empaquetados más los ajustes de `voices.yaml`.

    Orden: defaults en el orden del YAML, luego las voces agregadas en el orden
    de `voices.yaml`. Sin `voices.yaml` devuelve solo los defaults. Cualquier
    problema (YAML inválido, `Voice` inválido, ajuste no permitido, id duplicado
    o registro inválido) → ``ConfigError``.
    """
    defaults = _read_entries(DEFAULT_VOICES_FILE)
    voices = [_parse_voice(entry, DEFAULT_VOICES_FILE) for entry in defaults]
    by_id = {voice.id: voice for voice in voices}
    user_path = paths.voices_yaml
    if user_path.exists():
        seen: set[str] = set()
        for entry in _read_entries(user_path):
            voice_id = entry.get("id")
            if not isinstance(voice_id, str) or not voice_id:
                raise ConfigError(f"entrada sin id válido en {user_path}: {entry!r}")
            if voice_id in seen:
                raise ConfigError(f"voz duplicada en {user_path}: {voice_id!r}")
            seen.add(voice_id)
            if voice_id in by_id:
                updated = _apply_override(by_id[voice_id], entry, user_path)
                by_id[voice_id] = updated
                voices = [updated if voice.id == voice_id else voice for voice in voices]
            else:
                new_voice = _parse_voice(entry, user_path)
                if new_voice.source != "synthetic":
                    raise ConfigError(
                        f"voz nueva {voice_id!r} en {user_path}: debe ser source: synthetic"
                    )
                by_id[voice_id] = new_voice
                voices.append(new_voice)
    validate_voices(voices)
    return voices
