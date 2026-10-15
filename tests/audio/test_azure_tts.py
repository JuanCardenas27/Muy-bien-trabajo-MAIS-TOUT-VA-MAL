"""Motor Azure TTS F0 de respaldo con tope mensual (AUD-04)."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from frances.audio.azure_tts import METER, AzureTtsEngine, CapExceeded, build_ssml
from frances.audio.edge import EngineError
from frances.db.store import Store
from frances.db.usage import current_month, usage_add, usage_get
from frances.models.audio import Voice
from frances.timeutil import parse_ts

REGION = "eastus"
URL = f"https://{REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
KEY = "clave-azure-secreta-1234567890"
NOW = parse_ts("2026-10-14T15:00:00Z")
MONTH = current_month(NOW)

DENISE = Voice(
    id="fr-FR-DeniseNeural",
    label="Denise · Francia · adulta",
    engine="edge",
    age="adult",
    gender="female",
    accent="Francia",
)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    s = Store.open(tmp_path / "s.db")
    yield s
    s.close()


def make_engine(store: Store, *, cap: int = 450000) -> AzureTtsEngine:
    return AzureTtsEngine(KEY, REGION, store, cap, now=lambda: NOW)


def test_ssml_escapes_text() -> None:
    assert build_ssml("Tom & <Jerry>", DENISE) == (
        "<speak version='1.0' xml:lang='fr-FR'><voice name='fr-FR-DeniseNeural'>"
        "Tom &amp; &lt;Jerry&gt;</voice></speak>"
    )


@respx.mock
def test_synthesize_posts_headers_and_writes_mp3(store: Store, tmp_path: Path) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200, content=b"ID3fakebytes"))
    asyncio.run(make_engine(store).synthesize("Bonjour", DENISE, tmp_path / "a.mp3"))

    assert route.called
    request = route.calls.last.request
    assert request.headers["Ocp-Apim-Subscription-Key"] == KEY
    assert request.headers["Content-Type"] == "application/ssml+xml"
    assert request.headers["X-Microsoft-OutputFormat"] == "audio-24khz-48kbitrate-mono-mp3"
    assert request.headers["User-Agent"] == "frances"
    assert request.content == build_ssml("Bonjour", DENISE).encode()
    assert (tmp_path / "a.mp3").read_bytes() == b"ID3fakebytes"
    assert usage_get(store.conn, MONTH, METER) == len("Bonjour")


@respx.mock
def test_usage_accumulates_across_calls(store: Store, tmp_path: Path) -> None:
    respx.post(URL).mock(return_value=httpx.Response(200, content=b"ID3"))
    engine = make_engine(store)
    asyncio.run(engine.synthesize("abc", DENISE, tmp_path / "a.mp3"))
    asyncio.run(engine.synthesize("de", DENISE, tmp_path / "b.mp3"))
    assert usage_get(store.conn, MONTH, METER) == 5


@respx.mock
def test_cap_exceeded_before_request(store: Store, tmp_path: Path) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200, content=b"ID3"))
    with store.tx() as conn:
        usage_add(conn, MONTH, METER, 8)
    with pytest.raises(CapExceeded):
        asyncio.run(make_engine(store, cap=10).synthesize("abc", DENISE, tmp_path / "a.mp3"))
    assert not route.called
    assert usage_get(store.conn, MONTH, METER) == 8


@respx.mock
def test_429_is_retryable_and_not_metered(store: Store, tmp_path: Path) -> None:
    respx.post(URL).mock(return_value=httpx.Response(429))
    with pytest.raises(EngineError) as exc_info:
        asyncio.run(make_engine(store).synthesize("Bonjour", DENISE, tmp_path / "a.mp3"))
    assert exc_info.value.retryable is True
    assert usage_get(store.conn, MONTH, METER) == 0
    assert not (tmp_path / "a.mp3").exists()


@respx.mock
def test_401_not_retryable_and_key_not_in_message(store: Store, tmp_path: Path) -> None:
    respx.post(URL).mock(return_value=httpx.Response(401))
    with pytest.raises(EngineError) as exc_info:
        asyncio.run(make_engine(store).synthesize("Bonjour", DENISE, tmp_path / "a.mp3"))
    assert exc_info.value.retryable is False
    assert KEY not in str(exc_info.value)
    assert usage_get(store.conn, MONTH, METER) == 0
