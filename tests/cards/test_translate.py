"""Tests de AzureTranslator F0 con medidor de cuota [CRD-03]."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from frances.cards.translate import (
    ENDPOINT,
    METER,
    AzureTranslator,
    NullTranslator,
    translator_from_env,
)
from frances.db.store import Store
from frances.db.usage import current_month, usage_get

FIXED = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    s = Store.open(tmp_path / "s.db")
    yield s
    s.close()


def _echo(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    payload = [{"translations": [{"text": "ES:" + item["Text"], "to": "es"}]} for item in body]
    return httpx.Response(200, json=payload)


@pytest.fixture
def api(respx_mock: respx.Router) -> respx.Router:
    respx_mock.post(ENDPOINT).mock(side_effect=_echo)
    return respx_mock


def test_request_params_and_headers(store: Store, api: respx.Router) -> None:
    AzureTranslator("k", "eastus", store, 1_000).translate(["bonjour"])
    assert len(api.calls) == 1
    req = api.calls[0].request
    q, h = req.url.params, req.headers
    assert (q["api-version"], q["from"], q["to"]) == ("3.0", "fr", "es")
    assert (h["Ocp-Apim-Subscription-Key"], h["Ocp-Apim-Subscription-Region"]) == (
        "k",
        "eastus",
    )


def test_splits_batches_by_count(store: Store, api: respx.Router) -> None:
    out = AzureTranslator("k", "r", store, 10**6).translate(["a"] * 250)
    assert out == ["ES:a"] * 250
    assert [len(json.loads(call.request.content)) for call in api.calls] == [100, 100, 50]


def test_splits_batches_by_chars(store: Store, api: respx.Router) -> None:
    out = AzureTranslator("k", "r", store, 10**6).translate(["x" * 4000] * 3)
    assert out == ["ES:" + "x" * 4000] * 3
    assert len(api.calls) == 2


def test_cap_reached_returns_none_for_rest(store: Store, api: respx.Router) -> None:
    out = AzureTranslator("k", "r", store, 100).translate(["a"] * 101)
    assert out[:100] == ["ES:a"] * 100
    assert out[100] is None
    assert len(api.calls) == 1


def test_usage_accumulates_in_db(store: Store, api: respx.Router) -> None:
    t = AzureTranslator("k", "r", store, 10**6, now=lambda: FIXED)
    assert t.translate(["abc"]) == ["ES:abc"]
    assert t.translate(["de"]) == ["ES:de"]
    assert usage_get(store.conn, current_month(FIXED), METER) == 5


def test_429_retries_then_succeeds(store: Store, respx_mock: respx.Router) -> None:
    ok = httpx.Response(
        200, json=[{"translations": [{"text": "ES:bonjour", "to": "es"}]}]
    )
    respx_mock.post(ENDPOINT).mock(
        side_effect=[httpx.Response(429), httpx.Response(429), ok]
    )
    sleeps: list[float] = []
    t = AzureTranslator("k", "r", store, 10**6, sleep=sleeps.append)
    assert t.translate(["bonjour"]) == ["ES:bonjour"]
    assert len(sleeps) == 2


def test_429_three_times_returns_none(store: Store, respx_mock: respx.Router) -> None:
    respx_mock.post(ENDPOINT).mock(side_effect=[httpx.Response(429)] * 3)
    sleeps: list[float] = []
    t = AzureTranslator("k", "r", store, 10**6, now=lambda: FIXED, sleep=sleeps.append)
    assert t.translate(["bonjour"]) == [None]
    assert len(sleeps) == 2
    assert usage_get(store.conn, current_month(FIXED), METER) == 0


def test_null_translator_and_from_env(store: Store, api: respx.Router) -> None:
    assert NullTranslator().translate(["a", "b"]) == [None, None]
    assert translator_from_env({}, store, 10).translate(["a", "b"]) == [None, None]
    assert isinstance(
        translator_from_env(
            {"AZURE_TRANSLATOR_KEY": "k", "AZURE_TRANSLATOR_REGION": "r"},
            store,
            10,
        ),
        AzureTranslator,
    )
    assert len(api.calls) == 0
