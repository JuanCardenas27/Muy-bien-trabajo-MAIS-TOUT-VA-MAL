"""Traductor Azure F0 con medidor de cuota mensual [CRD-03]."""

import time
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol

import httpx

from frances.db.store import Store
from frances.db.usage import current_month, usage_add, usage_get
from frances.log import get_logger, redact
from frances.timeutil import now_utc

ENDPOINT = "https://api.cognitive.microsofttranslator.com/translate"
MAX_TEXTS = 100
MAX_CHARS = 10_000
METER = "azure_translator_chars"

_API_VERSION = "3.0"
_MAX_ATTEMPTS = 3
_TIMEOUT_S = 30.0

_logger = get_logger(__name__)


class Translator(Protocol):
    """Contrato mínimo que consume el generador por reglas (CRD-02)."""

    def translate(
        self, texts: list[str], src: str = "fr", dst: str = "es"
    ) -> list[str | None]:
        """Traduce en orden; `None` = cuota agotada o fallo reintentable."""
        ...


class NullTranslator:
    """Siempre devuelve `None` (sin credenciales de Azure)."""

    def translate(
        self, texts: list[str], src: str = "fr", dst: str = "es"
    ) -> list[str | None]:
        return [None] * len(texts)


def _split_batches(texts: list[str]) -> list[list[str]]:
    """Lotes greedy en orden: corte por `MAX_TEXTS` o por `MAX_CHARS`."""
    batches: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for text in texts:
        if current and (
            len(current) >= MAX_TEXTS or current_chars + len(text) > MAX_CHARS
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(text)
        current_chars += len(text)
    if current:
        batches.append(current)
    return batches


def _parse_response(resp: httpx.Response, size: int) -> list[str | None] | None:
    """Extrae `translations[0].text` por ítem; `None` si la forma no cuadra."""
    try:
        data = resp.json()
    except ValueError as exc:
        _logger.warning("translator respuesta no JSON: %s", redact(str(exc)))
        return None
    if not isinstance(data, list) or len(data) != size:
        _logger.warning("translator respuesta inesperada: %s", redact(resp.text))
        return None
    out: list[str | None] = []
    for item in data:
        text: str | None = None
        if isinstance(item, dict):
            translations = item.get("translations")
            if isinstance(translations, list) and translations:
                first = translations[0]
                if isinstance(first, dict):
                    candidate = first.get("text")
                    if isinstance(candidate, str):
                        text = candidate
        out.append(text)
    return out


class AzureTranslator:
    """Traductor Azure con tope mensual (`usage.azure_translator_chars`)."""

    def __init__(
        self,
        key: str,
        region: str,
        store: Store,
        monthly_cap: int,
        client: httpx.Client | None = None,
        now: Callable[[], datetime] = now_utc,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._key = key
        self._region = region
        self._store = store
        self._monthly_cap = monthly_cap
        self._client = client if client is not None else httpx.Client(trust_env=False)
        # trust_env=False: sin red en tests y sin depender de proxies del entorno.
        self._now = now
        self._sleep = sleep

    def _send(self, batch: list[str], src: str, dst: str) -> list[str | None] | None:
        """POST de un lote; 429 reintenta, otro fallo → `None`."""
        payload = [{"Text": text} for text in batch]
        params = {"api-version": _API_VERSION, "from": src, "to": dst}
        headers = {
            "Ocp-Apim-Subscription-Key": self._key,
            "Ocp-Apim-Subscription-Region": self._region,
        }
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = self._client.post(
                    ENDPOINT,
                    params=params,
                    headers=headers,
                    json=payload,
                    timeout=_TIMEOUT_S,
                )
            except httpx.TimeoutException as exc:
                _logger.warning("translator timeout: %s", redact(str(exc)))
                return None
            except httpx.HTTPError as exc:
                _logger.warning("translator error de red: %s", redact(str(exc)))
                return None
            if resp.status_code == 200:
                return _parse_response(resp, len(batch))
            if resp.status_code == 429 and attempt < _MAX_ATTEMPTS - 1:
                self._sleep(2.0**attempt)
                continue
            _logger.warning(
                "translator fallo %s: %s", resp.status_code, redact(resp.text)
            )
            return None
        return None  # inalcanzable: el último intento siempre retorna

    def translate(
        self, texts: list[str], src: str = "fr", dst: str = "es"
    ) -> list[str | None]:
        """Traduce por lotes; el tope o un fallo deja `None` en el resto."""
        out: list[str | None] = [None] * len(texts)
        offset = 0
        for batch in _split_batches(texts):
            chars = sum(len(text) for text in batch)
            month = current_month(self._now())
            with self._store.tx() as conn:
                blocked = (
                    usage_get(conn, month, METER) + chars > self._monthly_cap
                )
            if blocked:
                break
            translated = self._send(batch, src, dst)
            if translated is None:
                break
            out[offset : offset + len(batch)] = translated
            with self._store.tx() as conn:
                usage_add(conn, month, METER, chars)
            offset += len(batch)
        return out


def translator_from_env(
    env: Mapping[str, str], store: Store, monthly_cap: int
) -> Translator:
    """`NullTranslator` si falta `AZURE_TRANSLATOR_KEY` o `AZURE_TRANSLATOR_REGION`."""
    key = env.get("AZURE_TRANSLATOR_KEY")
    region = env.get("AZURE_TRANSLATOR_REGION")
    if not key or not region:
        return NullTranslator()
    return AzureTranslator(key, region, store, monthly_cap)
