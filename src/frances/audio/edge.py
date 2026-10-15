"""Motor Edge-TTS para la síntesis de audio por lotes (AUD-03).

Sintetiza con las voces neurales de Microsoft (familia ``ms-neural``) y
escribe MP3. Sin reintentos aquí: los hace la etapa ``run_audio`` (AUD-06)
según ``EngineError.retryable``.
"""

import asyncio
from pathlib import Path

import aiohttp
import edge_tts
from edge_tts.exceptions import NoAudioReceived, WebSocketError

from frances.models.audio import EngineFamily, Voice


class EngineError(Exception):
    """Fallo de síntesis de un motor TTS.

    Lo reutilizan AUD-04 (Azure) y AUD-06 (etapa audio). El mensaje nunca
    incluye el texto sintetizado (contenido del curso); solo la voz.
    """

    def __init__(self, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class EdgeEngine:
    """Motor Edge-TTS (familia ``ms-neural``). Cumple el protocolo ``TtsEngine``."""

    family: EngineFamily = "ms-neural"
    family_version: str = "1"

    def __init__(self, concurrency_hint: int = 2) -> None:
        self.concurrency_hint = concurrency_hint

    async def synthesize(
        self, text: str, voice: Voice, out_wav_or_mp3: Path
    ) -> None:
        """Sintetiza ``text`` con ``voice`` y escribe MP3 en ``out_wav_or_mp3``.

        Las voces sintéticas usan su voz base de Edge
        (``voice.derived_from``) con la prosodia ``pitch_hz``.
        """
        edge_voice = voice.derived_from or voice.id
        pitch = f"{voice.pitch_hz:+d}Hz"
        try:
            communicate = edge_tts.Communicate(text, edge_voice, pitch=pitch)
            await communicate.save(str(out_wav_or_mp3))
        except (aiohttp.ClientError, asyncio.TimeoutError, WebSocketError) as exc:
            raise EngineError(
                f"edge-tts transitorio con voz {edge_voice}: {exc}",
                retryable=True,
            ) from exc
        except (NoAudioReceived, ValueError) as exc:
            raise EngineError(
                f"edge-tts definitivo con voz {edge_voice}: {exc}",
                retryable=False,
            ) from exc
        try:
            size = out_wav_or_mp3.stat().st_size
        except OSError as exc:
            raise EngineError(
                f"edge-tts sin archivo de salida con voz {edge_voice}: {exc}",
                retryable=False,
            ) from exc
        if size == 0:
            raise EngineError(
                f"edge-tts devolvió un archivo vacío con voz {edge_voice}",
                retryable=False,
            )
