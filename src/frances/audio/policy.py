"""Política de voces y planificación de clips de audio (AUD-02)."""

import hashlib
from typing import Literal

from frances.audio.cachekey import audio_request
from frances.audio.repo import insert_pending, link_card_audio, prune_card_audio
from frances.config import Settings
from frances.db.store import Store
from frances.models.audio import Voice
from frances.models.content import CardKind


def _fixed_enabled(voices: list[Voice], settings: Settings) -> list[Voice]:
    """Fijas habilitadas en el orden de `fixed_voices`; inexistentes se ignoran."""
    by_id = {v.id: v for v in voices}
    out: list[Voice] = []
    for voice_id in settings.audio.fixed_voices:
        voice = by_id.get(voice_id)
        if voice is not None and voice.enabled:
            out.append(voice)
    return out


def _rotating_pool(voices: list[Voice], settings: Settings) -> list[Voice]:
    """Habilitadas fuera de `fixed_voices`, ordenadas por id."""
    fixed = set(settings.audio.fixed_voices)
    return sorted((v for v in voices if v.enabled and v.id not in fixed), key=lambda v: v.id)


def voices_for(
    card_id: str,
    kind: CardKind,
    field: Literal["front", "example"],
    voices: list[Voice],
    settings: Settings,
) -> list[Voice]:
    """Elige las voces para un campo de una tarjeta."""
    if field == "example":
        fixed = _fixed_enabled(voices, settings)
        return fixed[:1]
    if kind == "drill":
        return sorted((v for v in voices if v.enabled), key=lambda v: v.id)
    fixed = _fixed_enabled(voices, settings)
    pool = _rotating_pool(voices, settings)
    if not pool or settings.audio.rotating <= 0:
        return list(fixed)
    start = int(hashlib.sha256(card_id.encode()).hexdigest(), 16) % len(pool)
    count = min(settings.audio.rotating, len(pool))
    rot = [pool[(start + i) % len(pool)] for i in range(count)]
    return [*fixed, *rot]


def plan_audio(store: Store, voices: list[Voice], settings: Settings, now: str) -> int:
    """Crea pendientes y enlaces para tarjetas no stale; devuelve filas nuevas."""
    created = 0
    with store.tx() as conn:
        cards = conn.execute(
            "SELECT id, kind, front_fr, example_fr FROM cards WHERE stale = 0"
        ).fetchall()
        for card_id, kind, front_fr, example_fr in cards:
            front_voices = voices_for(card_id, kind, "front", voices, settings)
            front_keys: set[str] = set()
            for voice in front_voices:
                req = audio_request(front_fr, voice)
                if insert_pending(conn, req, now):
                    created += 1
                link_card_audio(conn, card_id, "front", req.cache_key)
                front_keys.add(req.cache_key)
            prune_card_audio(conn, card_id, "front", front_keys)
            example_keys: set[str] = set()
            if example_fr:
                for voice in voices_for(card_id, kind, "example", voices, settings):
                    req = audio_request(example_fr, voice)
                    if insert_pending(conn, req, now):
                        created += 1
                    link_card_audio(conn, card_id, "example", req.cache_key)
                    example_keys.add(req.cache_key)
            prune_card_audio(conn, card_id, "example", example_keys)
    return created
