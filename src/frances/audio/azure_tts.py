"""Motor Azure TTS F0 de respaldo con tope mensual de caracteres (AUD-04).

Alternativa a Edge-TTS (familia ``ms-neural``) que habla con Azure Speech.
Cuenta los caracteres sintetizados en el medidor ``azure_tts_chars`` y no
lanza peticiones cuando el tope mensual ya se agotaría. La clave de Azure
nunca aparece en los mensajes de error (R-07).
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import httpx

from frances.audio.edge import EngineError
from frances.db.store import Store
from frances.db.usage import current_month, usage_add, usage_get
from frances.models.audio import EngineFamily, Voice
from frances.timeutil import now_utc

METER = "azure_tts_chars"

_OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
_TIMEOUT_SECONDS = 30.0
_ENDPOINT = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"


class CapExceeded(Exception):
    """El tope mensual de caracteres de Azure TTS ya se agotaría."""


def build_ssml(text: str, voice: Voice) -> str:
    """SSML de síntesis: voz base (``derived_from`` o ``id``) y prosodia si hay."""
    voice_id = voice.derived_from or voice.id
    body = escape(text)
    if voice.pitch_hz != 0:
        body = f"<prosody pitch='{voice.pitch_hz:+d}Hz'>{body}</prosody>"
    return f"<speak version='1.0' xml:lang='fr-FR'><voice name='{voice_id}'>{body}</voice></speak>"


class AzureTtsEngine:
    """Motor Azure TTS (familia ``ms-neural``). Cumple el protocolo ``TtsEngine``."""

    family: EngineFamily = "ms-neural"
    family_version: str = "1"

    def __init__(
        self,
        key: str,
        region: str,
        store: Store,
        monthly_cap: int,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], datetime] = now_utc,
    ) -> None:
        self._key = key
        self._region = region
        self._store = store
        self._monthly_cap = monthly_cap
        self._client = client
        self._now = now

    async def synthesize(self, text: str, voice: Voice, out_wav_or_mp3: Path) -> None:
        """Sintetiza ``text`` con Azure y escribe MP3 en ``out_wav_or_mp3``."""
        month = current_month(self._now())
        with self._store.tx() as conn:
            used = usage_get(conn, month, METER)
        if used + len(text) > self._monthly_cap:
            raise CapExceeded(
                f"tope mensual de Azure TTS agotado: {used}/{self._monthly_cap} caracteres"
            )

        headers = {
            "Ocp-Apim-Subscription-Key": self._key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": _OUTPUT_FORMAT,
            "User-Agent": "frances",
        }
        url = _ENDPOINT.format(region=self._region)
        response = await self._post(url, headers, build_ssml(text, voice))

        if response.status_code == 200:
            out_wav_or_mp3.write_bytes(response.content)
            with self._store.tx() as conn:
                usage_add(conn, month, METER, len(text))
            return
        retryable = response.status_code == 429 or response.status_code >= 500
        raise EngineError(
            f"azure tts HTTP {response.status_code} con voz {voice.derived_from or voice.id}",
            retryable=retryable,
        )

    async def _post(self, url: str, headers: dict[str, str], body: str) -> httpx.Response:
        try:
            if self._client is not None:
                return await self._client.post(
                    url, headers=headers, content=body, timeout=_TIMEOUT_SECONDS
                )
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, trust_env=False) as client:
                return await client.post(url, headers=headers, content=body)
        except httpx.TimeoutException as exc:
            raise EngineError("azure tts: timeout de red", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise EngineError(
                f"azure tts: error de red ({type(exc).__name__})", retryable=True
            ) from exc
