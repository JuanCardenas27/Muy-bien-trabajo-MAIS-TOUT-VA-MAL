"""Tests de OAuth: credenciales desde el entorno + frances auth check (SYN-01)."""

import pytest
import respx
import typer
from typer.testing import CliRunner

from frances.errors import ConfigError
from frances.sync.auth import REAUTH_MESSAGE, SCOPES, TOKEN_URI, build_credentials, register

pytestmark = pytest.mark.respx(assert_all_called=False)

FAKE_ENV = {
    "GOOGLE_REFRESH_TOKEN": "rt",
    "GOOGLE_CLIENT_ID": "cid",
    "GOOGLE_CLIENT_SECRET": "csecret",
}

TOKEN_OK = {
    "access_token": "ya29.test-access-token",
    "expires_in": 3600,
    "token_type": "Bearer",
}

CLASSROOM_COURSES = "https://classroom.googleapis.com/v1/courses"


def make_app() -> typer.Typer:
    app = typer.Typer()
    register(app)
    return app


def test_build_credentials_uses_scopes_and_token_uri() -> None:
    c = build_credentials(FAKE_ENV)
    assert (c.refresh_token, c.client_id, c.token_uri) == ("rt", "cid", TOKEN_URI)
    assert tuple(c.scopes) == SCOPES and len(SCOPES) == 6


@pytest.mark.parametrize("missing", sorted(FAKE_ENV))
def test_missing_variable_raises_config_error_naming_it(missing: str) -> None:
    with pytest.raises(ConfigError, match=missing):
        build_credentials({k: v for k, v in FAKE_ENV.items() if k != missing})


def test_check_ok_lists_one_course(respx_mock: respx.Router) -> None:
    respx_mock.post(TOKEN_URI).respond(200, json=TOKEN_OK)
    respx_mock.get(CLASSROOM_COURSES).respond(200, json={"courses": [{"id": "c1"}]})
    res = CliRunner(env=FAKE_ENV).invoke(make_app(), ["auth", "check"])
    assert res.exit_code == 0
    assert respx_mock.calls.last.request.url.params["pageSize"] == "1"


def test_check_invalid_grant_exits_3(respx_mock: respx.Router) -> None:
    respx_mock.post(TOKEN_URI).respond(400, json={"error": "invalid_grant"})
    res = CliRunner(env=FAKE_ENV).invoke(make_app(), ["auth", "check"])
    assert res.exit_code == 3
    assert "OAuth Playground" in res.output and REAUTH_MESSAGE in res.output
    assert "rt" not in res.output.split()
