"""Normalización de texto para IDs, TTS y búsquedas (Global Constraints).

Solo ``frances.textnorm`` normaliza texto en todo el proyecto.
"""

import re
import string
import unicodedata

#: Apóstrofo tipográfico (U+2019), plegado a ASCII por :func:`tts_norm`.
_CURLY_APOSTROPHE = "\u2019"
#: Espacios que :func:`display_clean` conserva y :func:`tts_norm` convierte.
_FINE_SPACES_RE = "[\u00a0\u202f\u2009]"
#: Caracteres que :func:`norm_key` recorta de los extremos: «», comillas
#: ASCII/tipográficas y puntuación salvo el apóstrofo, más el espacio.
_STRIP_CHARS = '«»"“”' + string.punctuation.replace("'", "") + " "


def display_clean(s: str) -> str:
    """Limpieza visual: NFC, espacios/tabs repetidos a uno, recorta extremos.

    Conserva la tipografía (apóstrofo, « », espacios finos) para el usuario.
    """
    return re.sub(r"[ \t]{2,}", " ", unicodedata.normalize("NFC", s)).strip()


def tts_norm(s: str) -> str:
    """Normalización para TTS: display_clean + apóstrofo a ASCII + finos a espacio.

    Conserva mayúsculas y puntuación (la voz sí distingue "Allez !" de "allez").
    """
    cleaned = display_clean(s).replace(_CURLY_APOSTROPHE, "'")
    cleaned = re.sub(_FINE_SPACES_RE, " ", cleaned)
    return re.sub(r" {2,}", " ", cleaned).strip()


def norm_key(s: str) -> str:
    """Clave de identidad: tts_norm + casefold + recorte de extremos.

    El apóstrofo tipográfico, la forma NFD y las comillas francesas
    colapsan a la misma clave.
    """
    return tts_norm(s).casefold().strip(_STRIP_CHARS)
