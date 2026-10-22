"""Mapa de símbolos espeak-ng (fr-fr) a etiquetas canónicas de fonema (CRD-06).

La etiqueta canónica es IPA en forma normalizada NFC y la fija ADR-004: es la
única tabla de etiquetas del sistema (R-11), compartida con PRN-01. El nombre
``ESPEAK_TO_AZURE`` queda por historia: el valor nunca es un código propietario
de Azure. Aquí el mapa es la identidad porque espeak-ng ya emite el símbolo
canónico; se conserva explícito para no acoplar el contrato al binario.
"""

import unicodedata

_VOWELS: tuple[str, ...] = (
    "a",
    "\u0251",  # U+0251
    "e",
    "\u025b",  # U+025B
    "i",
    "o",
    "\u0254",  # U+0254
    "u",
    "y",
    "\u00f8",  # U+00F8
    "\u0153",  # U+0153
    "\u0259",  # U+0259
)

_NASALS: tuple[str, ...] = (
    "\u0251\u0303",  # U+0251 U+0303
    "\u0254\u0303",  # U+0254 U+0303
    "\u025b\u0303",  # U+025B U+0303
    "\u0153\u0303",  # U+0153 U+0303
)

_CONSONANTS: tuple[str, ...] = (
    "p",
    "b",
    "t",
    "d",
    "k",
    "\u0261",  # U+0261
    "f",
    "v",
    "s",
    "z",
    "\u0283",  # U+0283
    "\u0292",  # U+0292
    "m",
    "n",
    "\u0272",  # U+0272
    "\u014b",  # U+014B
    "l",
    "\u0281",  # U+0281
)

_SEMIVOWELS: tuple[str, ...] = (
    "j",
    "w",
    "\u0265",  # U+0265
)

_CANONICAL: tuple[str, ...] = (*_VOWELS, *_NASALS, *_CONSONANTS, *_SEMIVOWELS)

#: Símbolo de espeak-ng → etiqueta canónica IPA en NFC (ADR-004).
ESPEAK_TO_AZURE: dict[str, str] = {
    symbol: unicodedata.normalize("NFC", symbol) for symbol in _CANONICAL
}

#: Símbolos de espeak-ng que no representan un fonema y se descartan.
IGNORED: frozenset[str] = frozenset(
    {"\u02c8", "\u02cc", "\u02d0", "\u02d1", "\u203f", "-", "_", " "}
)

#: Versión del mapa; se guarda en ``cards.ipa`` como ``v<N>|...`` (R-12).
PHONEME_MAP_VERSION = "1"
