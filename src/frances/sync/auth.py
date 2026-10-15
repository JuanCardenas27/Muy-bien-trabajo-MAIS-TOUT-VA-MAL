"""OAuth de Google: credenciales desde el entorno + ``frances auth check``."""

from __future__ import annotations

import os
from collections.abc import Mapping

import typer
from google.oauth2.credentials import Credentials

from frances.cli import exit_with
from frances.errors import AuthError, ConfigError
from frances.sync.google_http import GoogleApi

SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/classroom.topics.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
)

TOKEN_URI = "https://oauth2.googleapis.com/token"

REAUTH_MESSAGE = (
    "Re-autoriza: genera un refresh token nuevo en OAuth Playground (LIVE-01)"
    " y reemplaza el secreto GOOGLE_REFRESH_TOKEN"
)

_REQUIRED_VARS: tuple[str, ...] = (
    "GOOGLE_REFRESH_TOKEN",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
)


def build_credentials(env: Mapping[str, str]) -> Credentials:
    """Crea credenciales OAuth desde el entorno, sin token: llega con ``refresh()``.

    Falta una variable → ``ConfigError`` que la nombra. Nada se escribe en disco
    y no hay ``auth init``: el refresh token se obtiene en el navegador (LIVE-01).
    """
    for var in _REQUIRED_VARS:
        if not env.get(var):
            raise ConfigError(
                f"Falta la variable de entorno {var} para autenticarse con Google"
            )
    return Credentials(
        None,
        refresh_token=env["GOOGLE_REFRESH_TOKEN"],
        client_id=env["GOOGLE_CLIENT_ID"],
        client_secret=env["GOOGLE_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
        scopes=list(SCOPES),
    )


def _run_check() -> None:
    try:
        api = GoogleApi(
            build_credentials(os.environ), "https://classroom.googleapis.com/v1"
        )
        api.refresh()
        api.get_json("courses", {"pageSize": 1})
    except AuthError as exc:
        raise AuthError(REAUTH_MESSAGE) from exc


def register(app: typer.Typer) -> None:
    """Registra ``frances auth check``: renueva el token y lista un curso."""
    auth = typer.Typer(help="Autenticación de Google.")

    @auth.command("check")
    def check() -> None:
        exit_with(_run_check)

    app.add_typer(auth, name="auth")
