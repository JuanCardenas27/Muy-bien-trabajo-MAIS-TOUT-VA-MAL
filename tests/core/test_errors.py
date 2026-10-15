from frances.errors import AuthError, ConfigError, FrancesError, PartialFailure


def test_exit_codes() -> None:
    assert (
        FrancesError.exit_code,
        PartialFailure.exit_code,
        AuthError.exit_code,
        ConfigError.exit_code,
    ) == (1, 2, 3, 4)
    assert issubclass(PartialFailure, FrancesError)
    assert issubclass(AuthError, FrancesError)
    assert issubclass(ConfigError, FrancesError)
