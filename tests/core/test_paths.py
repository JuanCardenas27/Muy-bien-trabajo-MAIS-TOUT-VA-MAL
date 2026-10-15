from pathlib import Path

from frances.paths import DataPaths


def test_data_paths_layout(tmp_path: Path) -> None:
    p = DataPaths(tmp_path)
    assert p.config == tmp_path / "frances.toml"
    assert p.voices_yaml == tmp_path / "voices.yaml"
    assert p.voice_refs == tmp_path / "voices" / "refs"
    assert p.state_sql == tmp_path / "state/state.sql"
    assert p.state_db == tmp_path / ".cache/state.db"
    assert p.cache == tmp_path / ".cache"
    assert p.blob_path("ab" + "0" * 62) == tmp_path / "blobs/ab" / ("ab" + "0" * 62)
    assert p.extraction_path("f" * 64, "3") == tmp_path / f"extractions/{'f' * 64}.3.json"
    assert p.audio_path("k" * 32) == tmp_path / f"audio/{'k' * 32}.mp3"


def test_ensure_dirs_creates_layout(tmp_path: Path) -> None:
    p = DataPaths(tmp_path / "data")
    p.ensure_dirs()
    assert p.cache.is_dir()
    assert p.voice_refs.is_dir()
    assert p.state_sql.parent.is_dir()
    p.ensure_dirs()  # idempotente
