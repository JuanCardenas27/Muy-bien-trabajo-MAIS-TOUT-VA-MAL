"""Reglas de IDs estables (plan maestro, «Reglas de IDs»)."""

import hashlib

from frances.models.classroom import AttachmentKind, ItemKind
from frances.models.content import CardKind
from frances.textnorm import norm_key

ITEM_PREFIX: dict[str, str] = {"coursework": "cw_", "material": "mt_", "announcement": "an_"}


def item_id(kind: ItemKind, classroom_id: str) -> str:
    """Prefijo por tipo de publicación + id de Classroom."""
    return ITEM_PREFIX[kind] + classroom_id


def attachment_id(item_id: str, kind: AttachmentKind, external_id: str) -> str:
    """Id estable del adjunto: at_ + 16 hex del sha256 de sus tres partes."""
    digest = hashlib.sha256(f"{item_id}\x1f{kind}\x1f{external_id}".encode()).hexdigest()
    return "at_" + digest[:16]


def card_id(front_fr: str, kind: CardKind) -> str:
    """Id estable de la tarjeta: c_ + 16 hex de norm_key(frente) + kind.

    La misma palabra con apóstrofo tipográfico, en NFD o entre « »
    produce una sola tarjeta; cambiar ``kind`` cambia el id.
    """
    digest = hashlib.sha256((norm_key(front_fr) + "\x1f" + kind).encode()).hexdigest()
    return "c_" + digest[:16]


def content_hash(*parts: str) -> str:
    """Huella hex de las partes unidas con \\x1f."""
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
