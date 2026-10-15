"""Almacén R2: pull, push con lease e If-Match y publicación (OPS-03)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
import pytest
import typer
from botocore.stub import Stubber
from typer.testing import CliRunner

import frances.ops.r2 as r2
from frances.errors import ConfigError
from frances.ops.r2 import (
    ConflictError,
    LeaseBusy,
    PreconditionFailed,
    S3ObjectStore,
    acquire_lease,
    prune_site,
    publish,
    pull,
    push,
    release_lease,
)
from frances.paths import DataPaths

NOW = datetime(2026, 10, 14, 15, 0, 0, tzinfo=UTC)


class FakeStore:
    """ObjectStore en memoria con etags (sha256) y condiciones if_match/if_none_match."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}
        self._meta: dict[str, dict[str, str]] = {}
        self.order: list[str] = []

    @staticmethod
    def _etag(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def seed(self, mapping: Mapping[str, bytes]) -> None:
        for key, content in mapping.items():
            self._objects[key] = (content, self._etag(content))
            self._meta.setdefault(key, {})

    def etag(self, key: str) -> str:
        return self._objects[key][1]

    def read(self, key: str) -> bytes:
        return self._objects[key][0]

    def has(self, key: str) -> bool:
        return key in self._objects

    def meta(self, key: str) -> dict[str, str]:
        return self._meta[key]

    def keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self._objects if k.startswith(prefix))

    def list_keys(self, prefix: str) -> dict[str, tuple[int, str]]:
        return {k: (len(c), t) for k, (c, t) in self._objects.items() if k.startswith(prefix)}

    def get(self, key: str, dest: Path) -> str:
        content, etag = self._objects[key]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return etag

    def put(
        self,
        key: str,
        src: Path | bytes,
        *,
        if_match: str | None = None,
        if_none_match: bool = False,
        cache_control: str | None = None,
    ) -> str:
        content = src if isinstance(src, bytes) else Path(src).read_bytes()
        existing = self._objects.get(key)
        if if_none_match and existing is not None:
            raise PreconditionFailed(key)
        if if_match is not None and (existing is None or existing[1] != if_match):
            raise PreconditionFailed(key)
        etag = self._etag(content)
        self._objects[key] = (content, etag)
        self._meta[key] = {"cache_control": cache_control or ""}
        self.order.append(key)
        return etag

    def delete(self, key: str, *, if_match: str | None = None) -> None:
        existing = self._objects.get(key)
        if if_match is not None and (existing is None or existing[1] != if_match):
            raise PreconditionFailed(key)
        self._objects.pop(key, None)
        self._meta.pop(key, None)


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def paths(tmp_path: Path) -> DataPaths:
    data = DataPaths(tmp_path)
    data.ensure_dirs()
    return data


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def site(tmp_path: Path) -> Path:
    site_dir = tmp_path / "site"
    (site_dir / "d").mkdir(parents=True)
    (site_dir / "d" / ("a" * 32 + ".bin")).write_bytes(b"bin-a")
    (site_dir / "d" / ("b" * 32 + ".bin")).write_bytes(b"bin-b")
    (site_dir / "bundle.json").write_text('{"format": "FRB1"}', encoding="utf-8")
    return site_dir


@pytest.fixture
def site_builds(store: FakeStore) -> FakeStore:
    old, keep_a, keep_b = "0" * 32, "1" * 32, "2" * 32
    store.seed(
        {
            "site/builds/b1.txt": f"{old}\n".encode(),
            "site/builds/b2.txt": f"{keep_a}\n".encode(),
            "site/builds/b3.txt": f"{keep_b}\n".encode(),
            "site/d/" + old + ".bin": b"old",
            "site/d/" + keep_a + ".bin": b"a",
            "site/d/" + keep_b + ".bin": b"b",
        }
    )
    return store


def test_pull_downloads_missing_and_records_state_etag(store: FakeStore, paths: DataPaths) -> None:
    store.seed({"data/state/state.sql": b"v1", "data/blobs/ab/ab12": b"x" * 10})
    result = pull(store, paths)  # type: ignore[arg-type]
    assert (result.downloaded, result.state_etag) == (2, store.etag("data/state/state.sql"))
    assert pull(store, paths).downloaded == 1  # state.sql siempre; el blob ya está
    assert (paths.cache / "r2_state_etag").read_text(encoding="utf-8") == result.state_etag


def test_push_uploads_blobs_before_state_with_if_match(store: FakeStore, paths: DataPaths) -> None:
    store.seed({"data/state/state.sql": b"v1"})
    pull(store, paths)  # type: ignore[arg-type]
    write(paths.blob_path("cd34"), b"y")
    write(paths.state_sql, b"v2")
    push(store, paths, "daily", NOW)  # type: ignore[arg-type]
    assert store.order.index("data/blobs/cd/cd34") < store.order.index("data/state/state.sql")
    assert store.read("snapshots/state-2026-10-14.sql") == b"v2"


def test_push_conflict_when_state_changed_remotely(store: FakeStore, paths: DataPaths) -> None:
    store.seed({"data/state/state.sql": b"v1"})
    pull(store, paths)  # type: ignore[arg-type]
    store.seed({"data/state/state.sql": b"otro"})
    write(paths.state_sql, b"mio")
    with pytest.raises(ConflictError):
        push(store, paths, "daily", NOW)  # type: ignore[arg-type]
    assert not store.has("snapshots/state-2026-10-14.sql")


def test_lease_is_exclusive_and_expired_lease_is_taken_over(store: FakeStore) -> None:
    a = acquire_lease(store, "daily-1", 7200, NOW)  # type: ignore[arg-type]
    with pytest.raises(LeaseBusy):
        acquire_lease(store, "reconcile-1", 18000, NOW)  # type: ignore[arg-type]
    taken = acquire_lease(store, "reconcile-1", 18000, NOW + timedelta(hours=3))  # type: ignore[arg-type]
    assert taken.holder == "reconcile-1"
    release_lease(store, a)  # type: ignore[arg-type]
    assert store.has("locks/writer.json")  # a ya no era dueño


def test_publish_uploads_bundle_json_last_with_cache_headers(store: FakeStore, site: Path) -> None:
    publish(store, site, "b1")  # type: ignore[arg-type]
    assert store.order[-1] == "site/bundle.json"
    assert store.meta("site/bundle.json")["cache_control"] == "no-cache"
    assert all(store.meta(k)["cache_control"].endswith("immutable") for k in store.keys("site/d/"))


def test_prune_keeps_bins_of_last_two_builds(store: FakeStore, site_builds: FakeStore) -> None:
    assert prune_site(store_builds := site_builds, keep_builds=2) == 1  # type: ignore[arg-type]
    assert store_builds.has("site/d/" + "1" * 32 + ".bin")
    assert store_builds.has("site/d/" + "2" * 32 + ".bin")
    assert not store_builds.has("site/d/" + "0" * 32 + ".bin")


def test_missing_env_is_config_error_naming_variable() -> None:
    with pytest.raises(ConfigError, match="R2_BUCKET"):
        S3ObjectStore.from_env(
            {"R2_ACCOUNT_ID": "a", "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s"}
        )


def test_s3_store_maps_412_to_precondition_failed() -> None:
    client = boto3.client(
        "s3",
        region_name="auto",
        aws_access_key_id="k",
        aws_secret_access_key="s",
    )
    stubber = Stubber(client)
    stubber.add_client_error(
        "put_object", service_error_code="PreconditionFailed", http_status_code=412
    )
    stubber.activate()
    store = S3ObjectStore("frances-data", client)
    with pytest.raises(PreconditionFailed):
        store.put("data/state/state.sql", b"x", if_match="deadbeef")
    stubber.assert_no_pending_responses()


def test_cli_prints_counts_not_keys(
    monkeypatch: pytest.MonkeyPatch, store: FakeStore, paths: DataPaths
) -> None:
    store.seed({"data/state/state.sql": b"v1", "data/blobs/ab/ab12": b"x" * 10})
    monkeypatch.setattr(r2, "store_from_env", lambda env=None: store)
    app = typer.Typer()
    r2.register(app)
    result = CliRunner().invoke(app, ["r2", "pull", "--data", str(paths.root)])
    assert result.exit_code == 0, result.output
    assert "blobs/" not in result.output and "state.sql" not in result.output
