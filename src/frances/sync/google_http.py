"""Cliente HTTP de Google: refresh de OAuth, reintentos, paginación y errores."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, nullcontext
from typing import Any, cast

import httpx
from google.auth import credentials as auth_credentials
from google.auth import transport
from google.auth.exceptions import RefreshError

from frances.errors import AuthError, FrancesError

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 5


class ForbiddenError(FrancesError):
    """Google devolvió 403; el motivo de la API viene en `reason`."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Google denegó el acceso: {reason}")
        self.reason = reason


class NotFoundError(FrancesError):
    """Google devolvió 404."""


class RetryExhaustedError(FrancesError):
    """Se agotaron los reintentos ante errores transitorios de Google."""

    def __init__(self, status: int) -> None:
        super().__init__(f"Google devolvió {status} tras {MAX_ATTEMPTS} intentos")
        self.status = status


class _HttpxTransportResponse(transport.Response):
    """Adapta un httpx.Response a lo que google-auth espera del refresh."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    @property
    def status(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> Mapping[str, str]:
        return self._response.headers

    @property
    def data(self) -> bytes:
        return self._response.content


class HttpxAuthRequest(transport.Request):
    """Transport de google-auth que reutiliza el httpx.Client del GoogleApi."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> transport.Response:
        response = self._client.request(
            method, url, content=body, headers=dict(headers or {}), timeout=timeout
        )
        return _HttpxTransportResponse(response)


def _error_reason(response: httpx.Response) -> str:
    """Extrae `errors[0].reason` del cuerpo de un 403; si no hay, `forbidden`."""
    response.read()
    try:
        payload = response.json()
    except ValueError:
        return "forbidden"
    if not isinstance(payload, dict):
        return "forbidden"
    error = payload.get("error")
    if not isinstance(error, dict):
        return "forbidden"
    errors = error.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict) and first.get("reason"):
            return str(first["reason"])
    message = error.get("message")
    if isinstance(message, str) and message:
        return message
    return "forbidden"


class GoogleApi:
    """GET/iteración/descarga contra una base de Google con refresh y reintentos."""

    def __init__(
        self,
        credentials: auth_credentials.Credentials,
        base_url: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._credentials = credentials
        self._base_url = base_url.rstrip("/")
        # Sin trust_env: el cliente no lee proxies del ambiente (httpx 0.28
        # revienta con IPv6 con corchetes en NO_PROXY y un proxy vería el token).
        self._client = client if client is not None else httpx.Client(trust_env=False)
        self._sleep = sleep

    def refresh(self) -> None:
        """Renueva el token; un RefreshError se convierte en AuthError."""
        try:
            # google-auth no está anotado; el ignore cubre solo esa llamada.
            self._credentials.refresh(HttpxAuthRequest(self._client))  # type: ignore[no-untyped-call]
        except RefreshError as exc:
            raise AuthError("No se pudo renovar el acceso a Google") from exc

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        raw = response.headers.get("Retry-After")
        if raw is not None:
            try:
                return float(cast(str, raw))
            except ValueError:
                pass
        backoff: float = (2**attempt) * random.uniform(0.8, 1.2)
        return backoff

    def _raise_for_error(self, response: httpx.Response, path: str) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        if status == 401:
            # Solo se llega aquí si ya se refrescó una vez en esta llamada.
            raise AuthError("Google rechazó el token renovado")
        if status == 403:
            raise ForbiddenError(_error_reason(response))
        if status == 404:
            raise NotFoundError(f"Recurso no encontrado en Google: {path}")
        raise FrancesError(f"Google devolvió un error no reintentable: {status}")

    @contextmanager
    def _send(
        self, method: str, path: str, params: Mapping[str, object], stream: bool
    ) -> Iterator[httpx.Response]:
        """Único bucle de refresh + reintentos que usan get_json, paginate y stream."""
        if not self._credentials.valid:
            self.refresh()
        refreshed = False
        attempt = 0
        url = f"{self._base_url}/{path}"
        while True:
            headers = {"Authorization": f"Bearer {self._credentials.token}"}
            query = cast("dict[str, Any]", dict(params))
            opener = (
                self._client.stream(method, url, params=query, headers=headers)
                if stream
                else nullcontext(self._client.request(method, url, params=query, headers=headers))
            )
            with opener as response:
                status = response.status_code
                if status == 401 and not refreshed:
                    refreshed = True
                    self.refresh()
                    continue
                if status in RETRY_STATUSES:
                    if attempt >= MAX_ATTEMPTS - 1:
                        raise RetryExhaustedError(status)
                    self._sleep(self._retry_delay(response, attempt))
                    attempt += 1
                    continue
                self._raise_for_error(response, path)
                yield response
                return

    def get_json(self, path: str, params: Mapping[str, object]) -> dict[str, Any]:
        """GET con reintentos que devuelve el cuerpo JSON como dict."""
        with self._send("GET", path, params, False) as response:
            data = response.json()
        if not isinstance(data, dict):
            raise FrancesError(f"Google devolvió un JSON no objeto en {path}")
        return data

    def paginate(
        self, path: str, params: Mapping[str, object], items_key: str
    ) -> Iterator[dict[str, Any]]:
        """Itera los ítems de todas las páginas; `items_key` ausente = página vacía."""
        query = dict(params)
        while True:
            with self._send("GET", path, query, False) as response:
                page = response.json()
            items = page.get(items_key, []) if isinstance(page, dict) else []
            yield from items
            token = page.get("nextPageToken") if isinstance(page, dict) else None
            if not token:
                break
            query["pageToken"] = token

    @contextmanager
    def stream(self, path: str, params: Mapping[str, object]) -> Iterator[httpx.Response]:
        """Cede una respuesta en streaming ya verificada; se cierra al salir."""
        with self._send("GET", path, params, True) as response:
            yield response
