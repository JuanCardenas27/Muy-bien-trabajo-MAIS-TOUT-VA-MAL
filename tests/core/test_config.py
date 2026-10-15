from pathlib import Path

import pytest

from frances.config import Settings, load_settings
from frances.errors import ConfigError


def test_settings_defaults(tmp_path: Path) -> None:
    s = load_settings(tmp_path / "missing.toml", {})
    assert s.audio.fixed_voices == ["fr-FR-DeniseNeural", "fr-FR-HenriNeural"]
    assert (s.classroom.max_download_mb, s.audio.max_clips_per_run, s.bundle.iterations) == (
        50,
        3000,
        600000,
    )
    assert s.cards.llm == "auto" and s.translator.monthly_char_cap == 1800000
    assert s.classroom.include_course_ids == []
    assert s.classroom.include_name_regex == "(?i)fran"
    assert (s.cards.llm_daily_item_limit, s.cards.vocab_per_item_max) == (30, 25)
    assert (s.audio.rotating, s.audio.azure_tts_monthly_char_cap) == (1, 450000)
    assert (s.bundle.salt, s.bundle.max_total_mb) == ("", 900)


def test_settings_unknown_key_is_config_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("[audio]\nrotatin = 2\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(bad, {})


def test_settings_invalid_toml_is_config_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("[audio", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(bad, {})


def test_settings_partial_file_keeps_other_defaults(tmp_path: Path) -> None:
    partial = tmp_path / "partial.toml"
    partial.write_text("[classroom]\nmax_download_mb = 10\n", encoding="utf-8")
    s = load_settings(partial, {})
    assert s.classroom.max_download_mb == 10
    assert s.cards.llm == "auto"


def test_secret_missing_raises_config_error() -> None:
    with pytest.raises(ConfigError):
        Settings().secret("GOOGLE_REFRESH_TOKEN")


def test_secret_returns_value_when_present() -> None:
    s = Settings()
    s._env = {"GOOGLE_REFRESH_TOKEN": "1//0gAbCdEfGhIjKlMnOpQrSt"}
    assert s.secret("GOOGLE_REFRESH_TOKEN") == "1//0gAbCdEfGhIjKlMnOpQrSt"


def test_optional_secret_none() -> None:
    assert Settings().optional_secret("LLM_API_KEY") is None


def test_optional_secret_returns_value_when_present() -> None:
    s = load_settings(Path("no-existe-frances.toml"), {"LLM_API_KEY": "sk-test-12345678"})
    assert s.optional_secret("LLM_API_KEY") == "sk-test-12345678"


def test_example_toml_matches_defaults() -> None:
    assert load_settings(Path("frances.example.toml"), {}) == load_settings(
        Path("no-existe-frances.toml"), {}
    )
