import logging

import pytest

from frances.log import SENSITIVE_ENV, get_logger, redact


def test_sensitive_env_lists_ten_names() -> None:
    assert SENSITIVE_ENV == (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REFRESH_TOKEN",
        "AZURE_SPEECH_KEY",
        "AZURE_TRANSLATOR_KEY",
        "FRANCES_PASSPHRASE",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    )


def test_redact_env_values_and_patterns() -> None:
    env = {"AZURE_SPEECH_KEY": "s3cretvalue123", "AZURE_SPEECH_REGION": "eastus"}
    hex32, hex64 = "0123456789abcdef" * 2, "ab" * 32
    out = redact(
        "k=s3cretvalue123 r=eastus t=ya29.a0AfH6x Bearer abc.def 1//0gAbCdEfGhIjKlMnOpQrSt "
        f"c=GOCSPX-abc123def456 h={hex32} s={hex64}",
        env,
    )
    assert "s3cretvalue123" not in out and "ya29." not in out and "abc.def" not in out
    assert "1//0g" not in out and "GOCSPX-abc123def456" not in out
    assert hex32 in out and hex64 in out  # claves de caché, sha256 e ids: no se redactan (R-07)
    assert "eastus" in out  # valores de < 8 caracteres no se tocan
    assert out.count("[REDACTED]") == 5


def test_redact_reads_os_environ_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRANCES_PASSPHRASE", "correct horse battery staple xyz")
    out = redact("p=correct horse battery staple xyz")
    assert "correct horse" not in out
    assert "[REDACTED]" in out


def test_logger_filter_redacts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "demo demo demo demo demo demo"
    monkeypatch.setenv("FRANCES_PASSPHRASE", secret)
    logger = get_logger("test-fnd04-log")
    with caplog.at_level(logging.WARNING, logger="test-fnd04-log"):
        logger.warning("pass=%s", secret)
    assert "demo demo" not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_get_logger_adds_filter_once() -> None:
    first = get_logger("test-fnd04-once")
    second = get_logger("test-fnd04-once")
    assert first is second
    assert len(first.filters) == 1
