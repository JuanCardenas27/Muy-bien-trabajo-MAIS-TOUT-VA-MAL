"""Errores de Frances con su código de salida de CLI."""


class FrancesError(Exception):
    """Error base: salida 1 (error inesperado)."""

    exit_code: int = 1


class PartialFailure(FrancesError):
    """Estado guardado pero hay ítems con error: salida 2."""

    exit_code: int = 2


class AuthError(FrancesError):
    """Fallo de autenticación (no se escribió nada): salida 3."""

    exit_code: int = 3


class ConfigError(FrancesError):
    """Configuración inválida: salida 4."""

    exit_code: int = 4
