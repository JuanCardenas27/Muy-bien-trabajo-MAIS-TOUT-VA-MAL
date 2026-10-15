"""Etiquetado de idioma por bloque (EXT-03)."""

import re
from functools import lru_cache

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

from frances.models import Lang, TextBlock

MIN_LETTERS = 12
MIXED_SHARE = 0.25
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@lru_cache(maxsize=1)
def _detector() -> LanguageDetector:
    return (
        LanguageDetectorBuilder.from_languages(Language.FRENCH, Language.SPANISH, Language.ENGLISH)
        .with_minimum_relative_distance(0.1)
        .build()
    )


def _code(language: Language) -> Lang:
    if language == Language.FRENCH:
        return "fr"
    if language == Language.SPANISH:
        return "es"
    return "en"


def _lang_of(text: str) -> Lang:
    detected = _detector().detect_language_of(text)
    if detected is None:
        return "unknown"
    return _code(detected)


def _letters(text: str) -> int:
    return sum(char.isalpha() for char in text)


def detect_lang(text: str) -> Lang:
    total = _letters(text)
    if total < MIN_LETTERS:
        return "unknown"
    sentences = _SENTENCE_RE.split(text)
    fr = sum(_letters(sentence) for sentence in sentences if _lang_of(sentence) == "fr")
    es = sum(_letters(sentence) for sentence in sentences if _lang_of(sentence) == "es")
    if fr >= MIXED_SHARE * total and es >= MIXED_SHARE * total:
        return "mixed"
    return _lang_of(text)


def split_blocks(text: str, source: str, page: int | None = None) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    for raw in re.split(r"\n\s*\n", text):
        stripped = raw.strip()
        if stripped:
            blocks.append(
                TextBlock(text=stripped, lang=detect_lang(stripped), source=source, page=page)
            )
    return blocks
