"""Tests del cliente HTTP de Google: refresh, reintentos, paginación, errores (SYN-02)."""

import httpx
import pytest
import respx
from google.auth.exceptions import RefreshError

from frances.errors import AuthError
from frances.sync.google_http import (
    ForbiddenError,
    GoogleApi,
    NotFoundError,
    RetryExhaustedError,
)

BASE = "https://classroom.googleapis.com/v1"


class FakeCreds:
    """Doble local de credenciales: token, valid y refresh(request)."""

    def __init__(self, token: str = "t0") -> None:
        self.token = token
        self.valid = True
        self.refresh_calls = 0

    def refresh(self, request: object) -> None:
        self.refresh_calls += 1
        self.token = f"t{self.refresh_calls}"


def make_api(sleeps: list[float]) -> GoogleApi:
    return GoogleApi(FakeCreds(token="t0"), BASE, sleep=sleeps.append)


def test_retries_429_then_ok(respx_mock: respx.Router) -> None:
    sleeps: list[float] = []
    route = respx_mock.get(f"{BASE}/x").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(200, json={"ok": 1}),
        ]
    )
    assert make_api(sleeps).get_json("x", {}) == {"ok": 1}
    assert route.call_count == 3 and len(sleeps) == 2
    assert 0.8 <= sleeps[0] <= 1.2 and 1.6 <= sleeps[1] <= 2.4


def test_gives_up_after_5_attempts(respx_mock: respx.Router) -> None:
    sleeps: list[float] = []
    route = respx_mock.get(f"{BASE}/x").respond(503)
    with pytest.raises(RetryExhaustedError) as exc_info:
        make_api(sleeps).get_json("x", {})
    assert route.call_count == 5 and len(sleeps) == 4 and exc_info.value.status == 503


def test_401_refreshes_once(respx_mock: respx.Router) -> None:
    creds = FakeCreds(token="t0")
    route = respx_mock.get(f"{BASE}/x").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={})]
    )
    GoogleApi(creds, BASE, sleep=lambda s: None).get_json("x", {})
    assert creds.refresh_calls == 1
    assert route.calls[1].request.headers["Authorization"] == "Bearer t1"


def test_paginate_follows_tokens(respx_mock: respx.Router) -> None:
    route = respx_mock.get(f"{BASE}/list").mock(
        side_effect=[
            httpx.Response(
                200, json={"things": [{"id": "a"}, {"id": "b"}], "nextPageToken": "p2"}
            ),
            httpx.Response(200, json={"things": [{"id": "c"}]}),
        ]
    )
    assert [t["id"] for t in make_api([]).paginate("list", {"pageSize": 2}, "things")] == [
        "a",
        "b",
        "c",
    ]
    assert route.calls[1].request.url.params["pageToken"] == "p2"
    assert route.calls[1].request.url.params["pageSize"] == "2"


def test_403_reason_parsed(respx_mock: respx.Router) -> None:
    respx_mock.get(f"{BASE}/x").respond(
        403,
        json={
            "error": {
                "errors": [{"reason": "exportSizeLimitExceeded"}],
                "message": "This file is too large to be exported.",
            }
        },
    )
    with pytest.raises(ForbiddenError) as exc_info:
        make_api([]).get_json("x", {})
    assert exc_info.value.reason == "exportSizeLimitExceeded"


def test_retry_after_header_respected(respx_mock: respx.Router) -> None:
    sleeps: list[float] = []
    respx_mock.get(f"{BASE}/x").mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": "7"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    assert make_api(sleeps).get_json("x", {}) == {"ok": True}
    assert sleeps == [7.0]


def test_401_twice_raises_auth_error(respx_mock: respx.Router) -> None:
    respx_mock.get(f"{BASE}/x").respond(401)
    with pytest.raises(AuthError):
        make_api([]).get_json("x", {})


def test_invalid_grant_on_refresh_raises_auth_error() -> None:
    class BadCreds(FakeCreds):
        def refresh(self, request: object) -> None:
            raise RefreshError("invalid_grant: Token has been expired or revoked.")

    with pytest.raises(AuthError):
        GoogleApi(BadCreds(), BASE, sleep=lambda s: None).refresh()


def test_404_raises_not_found(respx_mock: respx.Router) -> None:
    respx_mock.get(f"{BASE}/x").respond(404)
    with pytest.raises(NotFoundError):
        make_api([]).get_json("x", {})
