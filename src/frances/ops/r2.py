"""Almacén R2: pull, push con lease e If-Match y publicación del bundle (OPS-03).

El bucket privado ``frances-data`` es la única copia persistente de los datos.
``pull`` baja lo que falta, ``push`` sube las novedades con escrituras
condicionales (``If-Match``) para que dos escritores nunca se pisen, el lease
``locks/writer.json`` garantiza un solo escritor y ``publish`` publica el
bundle cifrado (``site/``) que sirve el Worker. Nada de esto imprime claves de
objeto ni contenido: solo conteos y bytes.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, NoReturn, Protocol

import boto3  # type: ignore[import-untyped]
import typer
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from frances.cli import DataOpt, exit_with
from frances.errors import ConfigError, FrancesError
from frances.log import redact
from frances.paths import DataPaths
from frances.timeutil import format_ts, now_utc, to_bogota

DATA_PREFIX = "data/"
LEASE_KEY = "locks/writer.json"
STATE_KEY = "data/state/state.sql"
ETAG_FILE = "r2_state_etag"
CONTENT_DIRS: tuple[str, ...] = ("blobs", "extractions", "audio")
IMMUTABLE = "public, max-age=31536000, immutable"
REQUIRED_ENV: tuple[str, ...] = (
    "R2_ACCOUNT_ID",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)


class PreconditionFailed(Exception):
    """Un ``if_match``/``if_none_match`` no se cumplió (HTTP 412)."""


class ConflictError(FrancesError):
    """Otro escritor cambió ``state.sql`` en medio: salida 1, sin pisar nada."""

    exit_code = 1


class LeaseBusy(FrancesError):
    """Lease vigente de otro escritor: salida 1, con dueño y vencimiento."""

    exit_code = 1

    def __init__(self, holder: str, expires_at: datetime) -> None:
        super().__init__(f"lease vigente de {holder} hasta {format_ts(expires_at)}")


class ObjectStore(Protocol):
    """Operaciones mínimas sobre el bucket (S3 o un doble en memoria)."""

    def list_keys(self, prefix: str) -> dict[str, tuple[int, str]]:
        """Mapea cada clave bajo ``prefix`` a ``(tamaño, etag)``."""
        ...

    def get(self, key: str, dest: Path) -> str:
        """Baja ``key`` a ``dest`` y devuelve su etag."""
        ...

    def put(
        self,
        key: str,
        src: Path | bytes,
        *,
        if_match: str | None = None,
        if_none_match: bool = False,
        cache_control: str | None = None,
    ) -> str:
        """Sube ``src`` a ``key`` con escritura condicional opcional; devuelve el etag."""
        ...

    def delete(self, key: str, *, if_match: str | None = None) -> None:
        """Borra ``key``, con ``if_match`` opcional."""
        ...


def _strip_quotes(etag: str) -> str:
    return etag.strip('"')


def _is_precondition(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return error.get("Code") in {"PreconditionFailed", "412"} or status == 412


def _reraise_precondition(exc: ClientError) -> NoReturn:
    if _is_precondition(exc):
        raise PreconditionFailed("escritura condicional rechazada") from exc
    raise exc


class S3ObjectStore:
    """ObjectStore real sobre la API S3 de Cloudflare R2 (boto3)."""

    def __init__(self, bucket: str, client: Any) -> None:
        self.bucket = bucket
        self.client = client

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> S3ObjectStore:
        """Cliente boto3 ``s3`` apuntado a R2; falta una variable → ``ConfigError``."""
        for name in REQUIRED_ENV:
            if not env.get(name):
                raise ConfigError(f"falta la variable {name}")
        account = env["R2_ACCOUNT_ID"]
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
            region_name="auto",
            aws_access_key_id=env["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        )
        return cls(env["R2_BUCKET"], client)

    def list_keys(self, prefix: str) -> dict[str, tuple[int, str]]:
        result: dict[str, tuple[int, str]] = {}
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                result[obj["Key"]] = (int(obj["Size"]), _strip_quotes(obj["ETag"]))
        return result

    def get(self, key: str, dest: Path) -> str:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:  # pragma: no cover - el doble de tests no falla
            _reraise_precondition(exc)
        body = response["Body"].read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return _strip_quotes(response["ETag"])

    def put(
        self,
        key: str,
        src: Path | bytes,
        *,
        if_match: str | None = None,
        if_none_match: bool = False,
        cache_control: str | None = None,
    ) -> str:
        body = src if isinstance(src, bytes) else Path(src).read_bytes()
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Key": key, "Body": body}
        if cache_control is not None:
            kwargs["CacheControl"] = cache_control
        if if_match is not None:
            kwargs["IfMatch"] = if_match
        if if_none_match:
            kwargs["IfNoneMatch"] = "*"
        try:
            response = self.client.put_object(**kwargs)
        except ClientError as exc:
            _reraise_precondition(exc)
        return _strip_quotes(response["ETag"])

    def delete(self, key: str, *, if_match: str | None = None) -> None:
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if if_match is not None:
            kwargs["IfMatch"] = if_match
        try:
            self.client.delete_object(**kwargs)
        except ClientError as exc:
            _reraise_precondition(exc)


def store_from_env(env: Mapping[str, str] | None = None) -> ObjectStore:
    """Arma el store R2 desde el entorno (``None`` → ``os.environ``)."""
    source = dict(os.environ) if env is None else dict(env)
    return S3ObjectStore.from_env(source)


@contextmanager
def _downloaded(store: ObjectStore, key: str) -> Iterator[bytes | None]:
    """Baja ``key`` a un archivo temporal y entrega su contenido (o ``None``)."""
    with tempfile.TemporaryDirectory(prefix="frances-r2-") as tmp:
        dest = Path(tmp) / "object"
        try:
            store.get(key, dest)
        except (KeyError, PreconditionFailed):
            yield None
            return
        yield dest.read_bytes()


@dataclass(frozen=True)
class PullResult:
    downloaded: int
    skipped: int
    state_etag: str | None


@dataclass(frozen=True)
class PushResult:
    uploaded: int
    state_changed: bool


@dataclass(frozen=True)
class Lease:
    holder: str
    expires_at: datetime
    etag: str


def _etag_file(paths: DataPaths) -> Path:
    return paths.cache / ETAG_FILE


def _read_saved_etag(paths: DataPaths) -> str | None:
    try:
        return _etag_file(paths).read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None


def _write_saved_etag(paths: DataPaths, etag: str) -> None:
    paths.cache.mkdir(parents=True, exist_ok=True)
    _etag_file(paths).write_text(etag, encoding="utf-8")


def pull(store: ObjectStore, paths: DataPaths, only: Sequence[str] | None = None) -> PullResult:
    """Baja de ``data/`` lo que falta o difiere en tamaño; ``state``/``voices`` siempre."""
    allowed = set(only) if only else None
    downloaded = 0
    skipped = 0
    state_etag: str | None = _read_saved_etag(paths)
    for key, (size, etag) in sorted(store.list_keys(DATA_PREFIX).items()):
        rel = key[len(DATA_PREFIX) :]
        top = rel.split("/", 1)[0]
        if allowed is not None and top not in allowed:
            continue
        local = paths.root / rel
        if top in CONTENT_DIRS:
            if local.exists() and local.stat().st_size == size:
                skipped += 1
                continue
            store.get(key, local)
            downloaded += 1
        else:
            store.get(key, local)
            downloaded += 1
            if rel == "state/state.sql":
                state_etag = etag
    if state_etag is not None:
        _write_saved_etag(paths, state_etag)
    return PullResult(downloaded=downloaded, skipped=skipped, state_etag=state_etag)


def push(store: ObjectStore, paths: DataPaths, label: str, now: datetime) -> PushResult:
    """Sube lo content-addressed que falta y ``state.sql`` con ``If-Match``.

    Un ``PreconditionFailed`` sobre ``state.sql`` (otro escritor se coló) es
    :class:`ConflictError` y no escribe el snapshot del día. ``label`` describe
    la corrida (``daily``/``reconcile``) y no altera el layout.
    """
    uploaded = 0
    remote = store.list_keys(DATA_PREFIX)
    for top in CONTENT_DIRS:
        directory = paths.root / top
        if not directory.is_dir():
            continue
        for local in sorted(path for path in directory.rglob("*") if path.is_file()):
            key = DATA_PREFIX + local.relative_to(paths.root).as_posix()
            if key in remote:
                continue
            store.put(key, local)
            uploaded += 1
    previous = _read_saved_etag(paths)
    try:
        if previous is None:
            new_etag = store.put(STATE_KEY, paths.state_sql, if_none_match=True)
        else:
            new_etag = store.put(STATE_KEY, paths.state_sql, if_match=previous)
    except PreconditionFailed as exc:
        raise ConflictError("conflicto: otro escritor cambió state.sql") from exc
    uploaded += 1
    _write_saved_etag(paths, new_etag)
    date = to_bogota(now).strftime("%Y-%m-%d")
    store.put(f"snapshots/state-{date}.sql", paths.state_sql)
    return PushResult(uploaded=uploaded, state_changed=new_etag != previous)


def _lease_payload(holder: str, expires_at: datetime) -> bytes:
    return json.dumps({"holder": holder, "expires_at": format_ts(expires_at)}).encode("utf-8")


def _load_lease(store: ObjectStore) -> Lease | None:
    with _downloaded(store, LEASE_KEY) as content:
        if content is None:
            return None
        data = json.loads(content)
        key = store.list_keys(LEASE_KEY)
        etag = key.get(LEASE_KEY, (0, ""))[1]
        return Lease(
            holder=str(data["holder"]),
            expires_at=datetime.fromisoformat(str(data["expires_at"]).replace("Z", "+00:00")),
            etag=etag,
        )


def acquire_lease(
    store: ObjectStore, holder: str, ttl_s: int, now: datetime, wait_s: int = 0
) -> Lease:
    """Toma ``locks/writer.json``; lease vigente → espera y luego ``LeaseBusy``."""
    expires_at = now + timedelta(seconds=ttl_s)
    payload = _lease_payload(holder, expires_at)
    waited = 0
    while True:
        try:
            etag = store.put(LEASE_KEY, payload, if_none_match=True)
            return Lease(holder=holder, expires_at=expires_at, etag=etag)
        except PreconditionFailed:
            current = _load_lease(store)
            if current is not None and current.expires_at <= now:
                try:
                    store.delete(LEASE_KEY, if_match=current.etag)
                except PreconditionFailed:
                    pass
                else:
                    try:
                        etag = store.put(LEASE_KEY, payload, if_none_match=True)
                        return Lease(holder=holder, expires_at=expires_at, etag=etag)
                    except PreconditionFailed:
                        current = _load_lease(store)
            if wait_s and waited < wait_s:
                time.sleep(min(60, wait_s - waited))
                waited += 60
                continue
            busy = current or Lease(holder="desconocido", expires_at=now, etag="")
            raise LeaseBusy(busy.holder, busy.expires_at) from None


def release_lease(store: ObjectStore, lease: Lease) -> None:
    """Borra el lease si todavía es nuestro; si ya no, no hace nada."""
    try:
        store.delete(LEASE_KEY, if_match=lease.etag)
    except PreconditionFailed:
        return


def publish(store: ObjectStore, site_dir: Path, build_id: str) -> int:
    """Sube los ``d/*.bin`` que falten, la lista del build y ``bundle.json`` al final."""
    remote = store.list_keys("site/d/")
    uploaded = 0
    ids: list[str] = []
    d_dir = site_dir / "d"
    if d_dir.is_dir():
        for local in sorted(d_dir.glob("*.bin")):
            ids.append(local.stem)
            key = f"site/d/{local.name}"
            if key in remote:
                continue
            store.put(key, local, cache_control=IMMUTABLE)
            uploaded += 1
    listing = "".join(f"{bin_id}\n" for bin_id in ids)
    store.put(f"site/builds/{build_id}.txt", listing.encode("utf-8"))
    store.put("site/bundle.json", site_dir / "bundle.json", cache_control="no-cache")
    return uploaded


def prune_site(store: ObjectStore, keep_builds: int = 2) -> int:
    """Borra los ``site/d/*.bin`` que no figuran en los últimos ``keep_builds`` builds."""
    kept: set[str] = set()
    for key in sorted(store.list_keys("site/builds/"))[-keep_builds:]:
        with _downloaded(store, key) as content:
            if content is None:
                continue
            kept.update(
                line.strip() for line in content.decode("utf-8").splitlines() if line.strip()
            )
    deleted = 0
    for key in store.list_keys("site/d/"):
        bin_id = key.rsplit("/", 1)[-1].removesuffix(".bin")
        if bin_id not in kept:
            store.delete(key)
            deleted += 1
    return deleted


def register(app: typer.Typer) -> None:
    """Registra el grupo ``frances r2`` en la CLI."""
    r2_app = typer.Typer(help="Almacén R2: pull, push, lease y publicación.")
    lease_app = typer.Typer(help="Lease de escritor único.")

    @r2_app.command("pull")
    def pull_cmd(
        only: str | None = typer.Option(None, "--only", help="Directorios: a,b"),
        data: DataOpt = Path("."),
    ) -> None:
        def run() -> None:
            paths = DataPaths(data)
            paths.ensure_dirs()
            result = pull(store_from_env(), paths, only.split(",") if only else None)
            typer.echo(redact(f"downloaded={result.downloaded} skipped={result.skipped}"))
            return None

        exit_with(run)

    @r2_app.command("push")
    def push_cmd(
        label: str = typer.Option(..., "--label", help="Etiqueta de la corrida"),
        data: DataOpt = Path("."),
    ) -> None:
        def run() -> None:
            paths = DataPaths(data)
            paths.ensure_dirs()
            result = push(store_from_env(), paths, label, now_utc())
            typer.echo(redact(f"uploaded={result.uploaded} state_changed={result.state_changed}"))
            return None

        exit_with(run)

    @r2_app.command("publish")
    def publish_cmd(
        site: Annotated[Path, typer.Option("--site", help="Directorio site/ a publicar")],
        build_id: str = typer.Option(..., "--build-id", help="Id del build"),
    ) -> None:
        def run() -> None:
            uploaded = publish(store_from_env(), site, build_id)
            typer.echo(f"uploaded={uploaded}")
            return None

        exit_with(run)

    @r2_app.command("prune")
    def prune_cmd(
        keep: int = typer.Option(2, "--keep", help="Builds a conservar"),
    ) -> None:
        def run() -> None:
            deleted = prune_site(store_from_env(), keep)
            typer.echo(f"deleted={deleted}")
            return None

        exit_with(run)

    @lease_app.command("acquire")
    def lease_acquire_cmd(
        holder: str = typer.Option(..., "--holder", help="Dueño del lease"),
        ttl: int = typer.Option(7200, "--ttl", help="Vigencia en segundos"),
        wait: int = typer.Option(0, "--wait", help="Segundos a esperar"),
    ) -> None:
        def run() -> None:
            lease = acquire_lease(store_from_env(), holder, ttl, now_utc(), wait_s=wait)
            typer.echo(redact(f"lease={lease.holder} ttl={ttl}"))
            return None

        exit_with(run)

    @lease_app.command("release")
    def lease_release_cmd(
        holder: str = typer.Option(..., "--holder", help="Dueño del lease"),
    ) -> None:
        def run() -> None:
            store = store_from_env()
            current = _load_lease(store)
            if current is not None and current.holder == holder:
                release_lease(store, current)
            typer.echo(redact(f"released={holder}"))
            return None

        exit_with(run)

    r2_app.add_typer(lease_app, name="lease")
    app.add_typer(r2_app, name="r2")
