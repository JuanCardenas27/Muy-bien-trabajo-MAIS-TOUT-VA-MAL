# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "edge-tts==7.3.1",
# ]
# ///
"""SPK-01: Edge-TTS — confirmar voces fr-*, formato real y límites de concurrencia.

Subcomandos (plan 2026-10-14-01, Task SPK-01):
  list                          lista voces fr-* como tabla Markdown
  bench --concurrency N --clips C  sintetiza la frase fija rotando voces
  probe [FILE]                  ffprobe sobre un clip (codec, sample_rate...)

Toda salida intermedia vive en .cache/spikes/spk01/ (dentro del worktree).
Uso: uv run scripts/spikes/spk01_edge_voices.py <subcomando> [opciones]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# El proxy MITM de egress reescribe la cabecera `Connection: Upgrade` del 101
# del handshake WebSocket a `Connection: close`. Para tolerarlo hay que
# parchear el parser Python de aiohttp, lo que exige desactivar sus
# extensiones C ANTES de que se importe aiohttp (se importa de forma
# perezosa dentro de las funciones de este script).
os.environ.setdefault("AIOHTTP_NO_EXTENSIONS", "1")


TEXT = "Bonjour, comment allez-vous ?"
CACHE_DIR_NAME = Path(".cache") / "spikes" / "spk01"


def repo_root() -> Path:
    # scripts/spikes/spk01_edge_voices.py -> repo root (2 niveles arriba de spikes/)
    return Path(__file__).resolve().parents[2]


def default_cache_dir() -> Path:
    d = repo_root() / CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SPK-01: voces, formato y límites de Edge-TTS")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="listar voces fr-* como tabla Markdown")
    p_list.add_argument(
        "--locale-prefix", default="fr-", help="prefijo de Locale (por defecto fr-)"
    )

    p_bench = sub.add_parser("bench", help="sintetizar N clips con concurrencia limitada")
    p_bench.add_argument("--concurrency", type=int, default=2, help="tamaño del Semaphore")
    p_bench.add_argument("--clips", type=int, default=20, help="número de clips a sintetizar")
    p_bench.add_argument("--text", default=TEXT, help="frase a sintetizar")
    p_bench.add_argument(
        "--out-dir",
        default=None,
        help="directorio de salida (por defecto .cache/spikes/spk01/)",
    )

    p_probe = sub.add_parser("probe", help="ffprobe sobre un clip")
    p_probe.add_argument("path", nargs="?", default=None, help="clip a inspeccionar")
    p_probe.add_argument("--file", dest="file", default=None, help="alias de path")
    return p


def _patch_edge_tts_ssl() -> None:
    """Confía en el CA del proxy de egress además de certifi (sin desactivar TLS).

    edge-tts fija `ssl.create_default_context(cafile=certifi.where())`, lo que
    ignora SSL_CERT_FILE del entorno y rompe la cadena del proxy MITM. Aquí
    construimos un contexto con el bundle del entorno (que ya incluye las CA
    públicas + la del proxy) y lo inyectamos en ambos módulos de edge-tts.
    Solo entorno del spike; en producción (runner self-hosted sin MITM,
    OPS-08) no hace falta.
    """
    import ssl

    cafile = os.environ.get("SSL_CERT_FILE")
    if cafile and Path(cafile).exists():
        ctx = ssl.create_default_context(cafile=cafile)
    else:
        ctx = ssl.create_default_context()
    try:
        import edge_tts.communicate as _comm
        import edge_tts.voices as _voices

        _comm._SSL_CTX = ctx
        _voices._SSL_CTX = ctx
    except ImportError:
        pass


def _patch_ws_handshake_for_mitm_proxy() -> None:
    """Tolera que el proxy MITM reescriba `Connection: Upgrade` a `close` en el 101.

    Sin esto aiohttp (a) rechaza el handshake ("Invalid connection header") y
    (b) suelta la conexión porque el parser marca `upgrade=False` y
    `should_close=True`. El parche solo actúa cuando el 101 trae
    `Upgrade: websocket` + `Sec-WebSocket-Accept` válidos (o sea, el origen
    sí aceptó el upgrade); no toca los bytes de audio ni desactiva TLS.
    Requiere el parser Python de aiohttp (AIOHTTP_NO_EXTENSIONS=1, fijado
    arriba). Idempotente.
    """
    try:
        from aiohttp import http_parser as _hp
        from multidict import CIMultiDict
    except ImportError:
        return
    if getattr(_hp.HttpResponseParser.parse_message, "_spk01_patched", False):
        return
    _orig_parse = _hp.HttpResponseParser.parse_message

    def _fixed_parse(self, lines):  # type: ignore[no-untyped-def]
        msg = _orig_parse(self, lines)
        try:
            if (
                msg.code == 101
                and msg.headers.get("Upgrade", "").lower() == "websocket"
                and msg.headers.get("Sec-WebSocket-Accept", "")
                and "upgrade" not in msg.headers.get("Connection", "").lower()
            ):
                new_headers = CIMultiDict(msg.headers)
                new_headers["Connection"] = "Upgrade"
                new_raw = tuple(
                    (k, b"Upgrade" if k.lower() == b"connection" else v) for k, v in msg.raw_headers
                )
                msg = msg._replace(
                    headers=new_headers,
                    raw_headers=new_raw,
                    should_close=False,
                    upgrade=True,
                )
        except Exception:
            pass
        return msg

    _fixed_parse._spk01_patched = True  # type: ignore[attr-defined]
    _hp.HttpResponseParser.parse_message = _fixed_parse  # type: ignore[method-assign]


def _ensure_proxy_patches() -> None:
    _patch_edge_tts_ssl()
    _patch_ws_handshake_for_mitm_proxy()


def _proxy_from_env() -> str | None:
    """Proxy del entorno (aiohttp confía en trust_env para HTTPS, pero ws_connect
    necesita el proxy explícito en este entorno de egress)."""
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        v = os.environ.get(k)
        if v:
            return v
    return None


async def fetch_fr_voices(locale_prefix: str = "fr-") -> list[dict]:
    import edge_tts  # import local: solo cuando hay red (no en CI sin red)

    _ensure_proxy_patches()
    voices = await edge_tts.list_voices(proxy=_proxy_from_env())
    fr = [v for v in voices if str(v.get("Locale", "")).startswith(locale_prefix)]
    fr.sort(key=lambda v: str(v.get("ShortName", "")))
    return fr


def cmd_list(locale_prefix: str) -> int:
    fr = asyncio.run(fetch_fr_voices(locale_prefix))
    print("| ShortName | Gender | Locale |")
    print("| --- | --- | --- |")
    for v in fr:
        print(f"| {v.get('ShortName', '')} | {v.get('Gender', '')} | {v.get('Locale', '')} |")
    return 0


async def _synth_one(text: str, voice: str, out: Path) -> float:
    import edge_tts

    _ensure_proxy_patches()
    t0 = time.perf_counter()
    comm = edge_tts.Communicate(text, voice, proxy=_proxy_from_env())
    await comm.save(str(out))
    return time.perf_counter() - t0


async def _bench_async(
    text: str, voices: list[str], out_dir: Path, concurrency: int, clips: int
) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)

    async def one(i: int) -> dict:
        voice = voices[i % len(voices)]
        fname = f"bench_c{concurrency}_{i:02d}_{voice}.mp3"
        out = out_dir / fname
        async with sem:
            t0 = time.perf_counter()
            try:
                await _synth_one(text, voice, out)
                return {
                    "i": i,
                    "voice": voice,
                    "file": fname,
                    "ok": True,
                    "seconds": time.perf_counter() - t0,
                }
            except Exception as e:
                return {
                    "i": i,
                    "voice": voice,
                    "file": fname,
                    "ok": False,
                    "seconds": time.perf_counter() - t0,
                    "error": f"{type(e).__name__}: {e}",
                }

    return list(await asyncio.gather(*[one(i) for i in range(clips)]))


def _p95(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    import math

    k = max(0, min(len(s) - 1, math.ceil(0.95 * len(s)) - 1))
    return s[k]


def cmd_bench(concurrency: int, clips: int, text: str, out_dir: str | None) -> int:
    if concurrency < 1 or clips < 1:
        print("error: --concurrency y --clips deben ser >= 1", file=sys.stderr)
        return 2
    out = Path(out_dir) if out_dir else default_cache_dir()
    out.mkdir(parents=True, exist_ok=True)
    fr = asyncio.run(fetch_fr_voices())
    if not fr:
        print("error: no se encontraron voces fr-*", file=sys.stderr)
        return 1
    voices = [str(v["ShortName"]) for v in fr]
    results = asyncio.run(_bench_async(text, voices, out, concurrency, clips))
    ok = [r for r in results if r["ok"]]
    fails = [r for r in results if not r["ok"]]
    lat = [r["seconds"] for r in ok]
    mean = sum(lat) / len(lat) if lat else 0.0
    p95 = _p95(lat)
    err_rate = len(fails) / len(results) if results else 1.0
    for r in fails:
        print(f"FAIL clip {r['i']} voz {r['voice']}: {r.get('error', '')}", file=sys.stderr)
    print(f"out_dir: {out}")
    print(f"concurrency: {concurrency} clips: {clips} ok: {len(ok)}/{len(results)}")
    print(f"latency_mean_s: {mean:.3f}")
    print(f"latency_p95_s: {p95:.3f}")
    print(f"error_rate: {err_rate:.3f}")
    print("")
    print("| concurrency | clips | ok | latency_mean_s | latency_p95_s | error_rate |")
    print("| --- | --- | --- | --- | --- | --- |")
    ok = [r for r in results if r["ok"]]
    row = (
        f"| {concurrency} | {clips} | {len(ok)}/{len(results)} "
        f"| {mean:.3f} | {p95:.3f} | {err_rate:.3f} |"
    )
    print(row)
    return 0


def _resolve_probe_target(path: str | None) -> Path:
    if path:
        p = Path(path)
        if not p.is_absolute() and not p.exists():
            # relativo al cwd; si no existe, probar relativo a la raíz del repo
            alt = repo_root() / p
            if alt.exists():
                return alt
        return p
    cache = default_cache_dir()
    mp3s = sorted(cache.glob("*.mp3"))
    if not mp3s:
        print(f"error: no hay clips en {cache}; corre bench primero", file=sys.stderr)
        sys.exit(1)
    return mp3s[0]


def cmd_probe(path: str | None) -> int:
    target = _resolve_probe_target(path)
    if not target.exists():
        print(f"error: no existe {target}", file=sys.stderr)
        return 1
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(target)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as e:
        print(f"error: ffprobe devolvió JSON inválido: {e}", file=sys.stderr)
        return 1
    streams = data.get("streams", [])
    if not streams:
        print("error: ffprobe no devolvió streams", file=sys.stderr)
        return 1
    s = streams[0]
    for k in ("codec_name", "sample_rate", "channels", "bit_rate"):
        print(f"{k}={s.get(k, '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "list":
        return cmd_list(args.locale_prefix)
    if args.cmd == "bench":
        return cmd_bench(args.concurrency, args.clips, args.text, args.out_dir)
    if args.cmd == "probe":
        return cmd_probe(args.file or args.path)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
