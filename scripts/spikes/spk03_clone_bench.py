# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "edge-tts==7.3.1",
#   "faster-whisper==1.2.1",
#   "jiwer==4.0.0",
#   "psutil==7.2.2",
#   "soundfile==0.14.0",
# ]
# ///
"""SPK-03: Benchmark de clonacion en CPU — Chatterbox vs XTTS v2.

Mide s/clip, RTF, RAM pico y CER (via faster-whisper small int8 CPU)
sobre frases francesas fijas (las 10 primeras de 1-3 palabras),
clonando una referencia generada con Edge-TTS (fr-FR-EloiseNeural).

CAMBIO DE ALCANCE (2026-10-14, decision del usuario): el benchmark es de
10 clips por motor, no 30 (limite de CPU de la VM: Chatterbox tarda
~2 min/clip en 2 vCPU). El script conserva las 30 frases fijas del plan;
los benchmarks se corren con `--limit 10`. Ver ADR-003.

IMPORTANTE: este archivo NO declara dependencias de motor en PEP 723
(chatterbox-tts y coqui-tts chocan entre si). Se corre una vez por motor:

    uv run --python 3.11 --with chatterbox-tts==0.1.7 --with setuptools==80.9.0 \
        scripts/spikes/spk03_clone_bench.py run --engine chatterbox --limit 10
    (setuptools==80.9.0 aporta pkg_resources, que perth>=1.0.0 exige;
    setuptools>=81 lo elimino y PerthImplicitWatermarker queda en None).

    COQUI_TOS_AGREED=1 uv run --python 3.11 --with coqui-tts==0.27.5 \
        --with torch==2.6.0 --with torchaudio==2.6.0 \
        scripts/spikes/spk03_clone_bench.py run --engine xtts --limit 10
    (coqui-tts trae torch/torchaudio solo como extras `cpu`/`cuda`, asi que
    se fijan explicitos; torch 2.6.0 es el mismo que resolvio chatterbox).

Subcomandos:
    make-ref            genera .cache/spikes/spk03/ref.wav (24 kHz mono, 10-15 s)
    run --engine E      sintetiza las frases (--limit N) y escribe <engine>.json
    requant --engine E  reconstruye <engine>.json desde clips ya existentes
                        (00.wav..NN.wav) + tiempos del <engine>.log, sin
                        re-sintetizar; re-transcribe y re-calcula CER/duracion
    report              une los JSON en una tabla Markdown (stdout)

ROBUSTEZ SANDBOX: ningun temporal va a /tmp ni /proc (la sandbox los
rechaza); todos los temporales viven en .cache/spikes/spk03/tmp.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from importlib import metadata as importlib_metadata
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes del benchmark (fijas por el plan SPK-03)
# ---------------------------------------------------------------------------

VOICE_REF = "fr-FR-EloiseNeural"
TARGET_SR = 24_000

REF_TEXT = (
    "Bonjour les enfants ! Bienvenue dans notre classe de français. "
    "Aujourd'hui, nous apprenons de nouveaux mots et nous chantons "
    "une chanson ensemble. Écoutez bien et répétez après moi."
)

# 30 frases fijas. Las 10 primeras son cortas (1-3 palabras).
PHRASES: list[str] = [
    # --- cortas (1-3 palabras): indices 0-9 ---
    "Bonjour.",
    "Merci beaucoup.",
    "Bonne nuit.",
    "À demain.",
    "Bravo !",
    "Salut !",
    "D'accord.",
    "Bonne chance.",
    "Je t'aime.",
    "Félicitations.",
    # --- largas (indices 10-29) ---
    "Il fait beau en France.",
    "Les enfants chantent une chanson.",
    "J'ai rendez-vous à onze heures.",
    "Le restaurant est très grand.",
    "Un bon vin blanc.",
    "Bonjour, comment allez-vous ?",
    "Nous allons au marché demain.",
    "La petite fille joue dans le jardin.",
    "Le chat dort sous la table.",
    "Elle lit un livre intéressant.",
    "Nous aimons les pommes rouges.",
    "Le train arrive à huit heures.",
    "Mon frère habite à Paris.",
    "La fleur sent très bon.",
    "Ils jouent au ballon samedi.",
    "Le soleil brille sur la mer.",
    "Tu veux un morceau de gâteau ?",
    "La maîtresse écrit au tableau.",
    "Les oiseaux volent dans le ciel.",
    "Je prends mon petit déjeuner à sept heures.",
]

N_SHORT = 10
CER_FAIL_THRESHOLD = 0.15

XTTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"

ENGINES = ("chatterbox", "xtts")


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

def repo_root() -> Path:
    # scripts/spikes/spk03_clone_bench.py -> root = parents[2]
    return Path(__file__).resolve().parents[2]


def cache_dir() -> Path:
    d = repo_root() / ".cache" / "spikes" / "spk03"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ref_path() -> Path:
    return cache_dir() / "ref.wav"


def clips_dir(engine: str) -> Path:
    d = cache_dir() / "clips" / engine
    d.mkdir(parents=True, exist_ok=True)
    return d


def json_path(engine: str) -> Path:
    return cache_dir() / f"{engine}.json"


def log_path(engine: str) -> Path:
    return cache_dir() / f"{engine}.log"


def worktree_tmp() -> Path:
    """Directorio de temporales dentro del worktree (nunca /tmp).

    La sandbox rechaza el acceso a /tmp y /proc; todas las herramientas
    del benchmark deben usar este directorio (via TMPDIR o `dir=`).
    """
    d = cache_dir() / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_worktree_tmp() -> Path:
    """Apunta TMPDIR/TEMP/TMP al worktree si apuntan a /tmp o estan vacias."""
    d = worktree_tmp()
    for var in ("TMPDIR", "TEMP", "TMP"):
        val = os.environ.get(var, "")
        if not val or val == "/tmp" or val.startswith("/tmp/"):
            os.environ[var] = str(d)
    return d


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[^a-zàâäéèêëîïôöùûüçœæ0-9\s]", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def norm(text: str) -> str:
    """Normalizacion para CER: minusculas, sin puntuacion, espacios simples."""
    text = text.lower()
    text = _PUNCT_RE.sub("", text)
    return _WS_RE.sub(" ", text).strip()


def pkg_version(name: str) -> str:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return "n/a"


def engine_versions(engine: str) -> dict[str, str]:
    base = {
        "faster-whisper": pkg_version("faster-whisper"),
        "jiwer": pkg_version("jiwer"),
        "psutil": pkg_version("psutil"),
        "soundfile": pkg_version("soundfile"),
        "torch": pkg_version("torch"),
        "python": platform.python_version(),
    }
    if engine == "chatterbox":
        base["chatterbox-tts"] = pkg_version("chatterbox-tts")
    elif engine == "xtts":
        base["coqui-tts"] = pkg_version("TTS")
        if base["coqui-tts"] == "n/a":
            base["coqui-tts"] = pkg_version("coqui-tts")
    return base


class RamSampler:
    """Muestrea el RSS del proceso en un hilo; registra el pico (bytes)."""

    def __init__(self, interval: float = 0.1) -> None:
        import psutil

        self._psutil = psutil
        self.interval = interval
        self.peak = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        proc = self._psutil.Process(os.getpid())
        while not self._stop.is_set():
            try:
                rss = proc.memory_info().rss
            except Exception:
                break
            if rss > self.peak:
                self.peak = rss
            self._stop.wait(self.interval)

    def __enter__(self) -> RamSampler:
        import psutil

        self.peak = psutil.Process(os.getpid()).memory_info().rss
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)


def wav_duration_s(path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(path))
    if info.samplerate <= 0:
        return 0.0
    return float(info.frames) / float(info.samplerate)


# ---------------------------------------------------------------------------
# Red / TLS del sandbox
# ---------------------------------------------------------------------------

def ensure_tls_trust() -> None:
    """Hace confiable el CA del proxy de salida en este entorno.

    El sandbox MITMiza TLS con un CA propio
    (/usr/local/share/ca-certificates/hatch-egress-ca.crt) que `certifi`
    no incluye. `edge-tts` y `requests`/`huggingface_hub` verifican contra
    el bundle de certifi, asi que lo agregamos si falta (solo en el
    entorno virtual actual) y apuntamos las variables de CA a ese bundle.
    Debe llamarse antes de importar edge_tts / faster_whisper / TTS.
    """
    src = Path("/usr/local/share/ca-certificates/hatch-egress-ca.crt")
    bundle_path: str | None = None
    # httpx (usado por huggingface_hub) no parsea los IPv6 con corchetes de
    # NO_PROXY/NO_PROXY del sandbox (`[::1]` -> `Invalid port: ':1]'`).
    # Esas entradas son hosts internos que el benchmark nunca contacta:
    # se retiran solo en el entorno de este proceso.
    for var in ("NO_PROXY", "no_proxy"):
        val = os.environ.get(var)
        if val:
            kept = [
                e.strip()
                for e in val.split(",")
                if e.strip() and ":" not in e.strip() and "[" not in e.strip()
            ]
            os.environ[var] = ",".join(kept)
    try:
        import certifi

        bundle_path = certifi.where()
        if src.exists():
            bundle = Path(bundle_path)
            ca = src.read_bytes()
            data = bundle.read_bytes()
            if ca.strip() not in data:
                with open(bundle, "ab") as fh:
                    fh.write(ca if data.endswith(b"\n") else b"\n" + ca)
    except Exception as exc:  # noqa: BLE001 - el benchmark sigue sin el parche
        print(f"AVISO TLS: no se pudo parchar certifi ({exc})", file=sys.stderr)
    if bundle_path is not None:
        os.environ.setdefault("SSL_CERT_FILE", bundle_path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle_path)
        os.environ.setdefault("CURL_CA_BUNDLE", bundle_path)


# ---------------------------------------------------------------------------
# make-ref: referencia Edge-TTS -> ref.wav 24 kHz mono
# ---------------------------------------------------------------------------

class _Ws:
    """WebSocket minimo (RFC 6455) sobre un socket ya con handshake 101.

    Existe porque el proxy de este sandbox reescribe
    `Connection: Upgrade` -> `Connection: close` en el 101 de Edge y los
    clientes estrictos (aiohttp, websockets) abortan. Los frames si fluyen.
    Sin extension de compresion: todo va sin comprimir.
    """

    def __init__(self, sock: socket.socket, timeout: float = 60.0) -> None:
        self.sock = sock
        self.sock.settimeout(timeout)
        self._buf = b""

    def send_text(self, text: str) -> None:
        import struct

        payload = text.encode("utf-8")
        key = os.urandom(4)
        header = bytes([0x81])
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", n)
        masked = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + key + masked)

    def _read_exactly(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("socket cerrado durante un frame WS")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv(self) -> str | bytes | None:
        """Siguiente mensaje: str (texto), bytes (binario) o None (close)."""
        import struct

        while True:
            b1, b2 = self._read_exactly(2)
            opcode = b1 & 0x0F
            ln = b2 & 0x7F
            if ln == 126:
                (ln,) = struct.unpack("!H", self._read_exactly(2))
            elif ln == 127:
                (ln,) = struct.unpack("!Q", self._read_exactly(8))
            if b2 & 0x80:
                mask = self._read_exactly(4)
            else:
                mask = None
            payload = self._read_exactly(ln) if ln else b""
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:  # close
                return None
            if opcode == 0x9:  # ping -> pong
                self.sock.sendall(bytes([0x8A, 0x00]))
                continue
            if opcode == 0xA:  # pong
                continue
            if opcode == 0x1:
                return payload.decode("utf-8")
            if opcode == 0x2:
                return payload
            from edge_tts.exceptions import UnexpectedResponse

            raise UnexpectedResponse(f"opcode WS inesperado: {opcode:#x}")


def _edge_socket(path_query: str, headers: dict[str, str]) -> socket.socket:
    """Abre el tunel (proxy CONNECT o directo), hace TLS y el handshake WS.

    Devuelve el socket posicionado tras el 101 (acepta `Connection: close`
    mangleado por el proxy). Lanza si el status no es 101.
    """
    import base64
    import ssl
    import urllib.parse

    import certifi

    proxy = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
    )
    host, port = "speech.platform.bing.com", 443
    if proxy:
        px = urllib.parse.urlparse(proxy)
        sock = socket.create_connection((px.hostname, px.port or 8080), timeout=20)
        creds = ""
        if px.username:
            user = urllib.parse.unquote(px.username)
            pwd = urllib.parse.unquote(px.password or "")
            creds = (
                "Proxy-Authorization: Basic "
                + base64.b64encode(f"{user}:{pwd}".encode()).decode()
                + "\r\n"
            )
        sock.sendall(
            f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            f"{creds}\r\n".encode()
        )
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("proxy cerro el CONNECT")
            resp += chunk
        if not resp.startswith(b"HTTP/1.1 200") and not resp.startswith(b"HTTP/1.0 200"):
            raise ConnectionError(f"CONNECT rechazado: {resp.splitlines()[0]!r}")
    else:
        sock = socket.create_connection((host, port), timeout=20)
    ctx = ssl.create_default_context(cafile=certifi.where())
    tls = ctx.wrap_socket(sock, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET {path_query} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
    )
    for k, v in headers.items():
        if k.lower() in ("sec-websocket-version", "upgrade", "connection",
                         "sec-websocket-key", "host"):
            continue
        req += f"{k}: {v}\r\n"
    req += "\r\n"
    tls.sendall(req.encode())
    tls.settimeout(30)
    raw = b""
    while b"\r\n\r\n" not in raw:
        chunk = tls.recv(65536)
        if not chunk:
            break
        raw += chunk
    status = raw.split(b"\r\n", 1)[0] if raw else b""
    if b" 101 " not in status:
        raise ConnectionError(f"handshake WS rechazado: {status[:120]!r}")
    return tls


async def _edge_save(text: str, voice: str, mp3_path: Path) -> None:
    """Guarda el MP3 de Edge-TTS con socket propio (ver `_Ws`/`_edge_socket`).

    El protocolo (speech.config + SSML + parseo de chunks) replica al de
    edge-tts 7.3.1; se reutilizan sus helpers (SSML, DRM, parseo).
    """
    from urllib.parse import urlparse
    from xml.sax.saxutils import escape

    from edge_tts.communicate import (
        connect_id,
        date_to_string,
        get_headers_and_data,
        mkssml,
        remove_incompatible_characters,
        split_text_by_byte_length,
        ssml_headers_plus_data,
    )
    from edge_tts.constants import SEC_MS_GEC_VERSION, WSS_HEADERS, WSS_URL
    from edge_tts.data_classes import TTSConfig
    from edge_tts.drm import DRM
    from edge_tts.exceptions import NoAudioReceived, UnexpectedResponse, UnknownResponse

    wss = urlparse(WSS_URL)
    path_query = (
        f"{wss.path}?{wss.query}&ConnectionId={connect_id()}"
        f"&Sec-MS-GEC={DRM.generate_sec_ms_gec()}"
        f"&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}"
    )
    config = TTSConfig(voice, "+0%", "+0%", "+0Hz", "SentenceBoundary")
    texts = list(
        split_text_by_byte_length(escape(remove_incompatible_characters(text)), 4096)
    )
    if not texts:
        raise NoAudioReceived("texto vacio: nada que sintetizar")

    sock = _edge_socket(path_query, DRM.headers_with_muid(dict(WSS_HEADERS)))
    ws = _Ws(sock)
    try:
        ws.send_text(
            f"X-Timestamp:{date_to_string()}\r\n"
            "Content-Type:application/json; charset=utf-8\r\n"
            "Path:speech.config\r\n\r\n"
            '{"context":{"synthesis":{"audio":{"metadataoptions":{'
            '"sentenceBoundaryEnabled":"true","wordBoundaryEnabled":"false"},'
            '"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}\r\n'
        )
        with open(mp3_path, "wb") as fh:
            audio_was_received = False
            for partial in texts:
                ws.send_text(
                    ssml_headers_plus_data(
                        connect_id(), date_to_string(), mkssml(config, partial)
                    )
                )
                while True:
                    msg = ws.recv()
                    if msg is None:
                        raise ConnectionError("Edge cerro el websocket (close)")
                    if isinstance(msg, bytes):
                        if len(msg) < 2:
                            raise UnexpectedResponse("mensaje binario sin longitud")
                        header_length = int.from_bytes(msg[:2], "big")
                        if header_length > len(msg):
                            raise UnexpectedResponse("longitud de cabecera imposible")
                        parameters, data = get_headers_and_data(msg, header_length)
                        if parameters.get(b"Path") != b"audio":
                            raise UnexpectedResponse("binario con Path != audio")
                        content_type = parameters.get(b"Content-Type", None)
                        if content_type is None:
                            if data:
                                raise UnexpectedResponse("audio sin Content-Type")
                            continue
                        if content_type != b"audio/mpeg":
                            raise UnexpectedResponse(f"Content-Type {content_type!r}")
                        if not data:
                            raise UnexpectedResponse("audio sin datos")
                        audio_was_received = True
                        fh.write(data)
                    else:
                        encoded = msg.encode("utf-8")
                        parameters, _data = get_headers_and_data(
                            encoded, encoded.find(b"\r\n\r\n")
                        )
                        path = parameters.get(b"Path", None)
                        if path == b"turn.end":
                            break
                        if path not in (b"response", b"turn.start", b"audio.metadata"):
                            raise UnknownResponse(f"Path desconocido: {path!r}")
            if not audio_was_received:
                raise NoAudioReceived("el servicio no devolvio audio")
    finally:
        try:
            sock.close()
        except OSError:
            pass


def cmd_make_ref(voice: str = VOICE_REF) -> Path:
    out = ref_path()
    ensure_worktree_tmp()
    with tempfile.TemporaryDirectory(prefix="spk03-ref-", dir=str(worktree_tmp())) as tmp:
        mp3 = Path(tmp) / "ref.mp3"
        asyncio.run(_edge_save(REF_TEXT, voice, mp3))
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(mp3),
            "-ar", str(TARGET_SR), "-ac", "1", "-c:a", "pcm_s16le",
            str(out),
        ]
        subprocess.run(cmd, check=True)
    dur = wav_duration_s(out)
    print(f"ref: {out} ({dur:.1f} s, {TARGET_SR} Hz mono, voz={voice})")
    if not 10.0 <= dur <= 15.0:
        print(
            f"AVISO: la referencia dura {dur:.1f} s, fuera del rango 10-15 s "
            "(se sigue usando; anotado para el ADR).",
            file=sys.stderr,
        )
    return out


# ---------------------------------------------------------------------------
# Sintesis por motor
# ---------------------------------------------------------------------------

_cb_model: object = None
_xtts_model: object = None


def synth_chatterbox(text: str, ref: Path, out: Path) -> None:
    """Sintetiza con Chatterbox Multilingual (language_id='fr'), CPU."""
    global _cb_model
    if _cb_model is None:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        _cb_model = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    import soundfile as sf

    wav = _cb_model.generate(  # type: ignore[union-attr]
        text, audio_prompt_path=str(ref), language_id="fr"
    )
    if hasattr(wav, "detach"):
        wav = wav.detach().cpu()
    arr = wav.numpy() if hasattr(wav, "numpy") else wav
    import numpy as np

    arr = np.asarray(arr)
    while arr.ndim > 1 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.ndim > 1:
        arr = arr.mean(axis=0)
    sr = int(getattr(_cb_model, "sr", TARGET_SR))
    sf.write(str(out), arr, sr)


def synth_xtts(text: str, ref: Path, out: Path) -> None:
    """Sintetiza con XTTS v2 (language='fr'), CPU."""
    global _xtts_model
    if os.environ.get("COQUI_TOS_AGREED") != "1":
        raise SystemExit(
            "XTTS requiere COQUI_TOS_AGREED=1 en el entorno. "
            "Relanza con: COQUI_TOS_AGREED=1 uv run ..."
        )
    if _xtts_model is None:
        from TTS.api import TTS

        _xtts_model = TTS(XTTS_MODEL, gpu=False)
    _xtts_model.tts_to_file(  # type: ignore[union-attr]
        text=text, file_path=str(out), speaker_wav=str(ref), language="fr"
    )


SYNTH = {"chatterbox": synth_chatterbox, "xtts": synth_xtts}


# ---------------------------------------------------------------------------
# run: benchmark completo de un motor
# ---------------------------------------------------------------------------

def transcribe_clip(model: object, clip: Path) -> str:
    segments, _info = model.transcribe(str(clip), language="fr")  # type: ignore[union-attr]
    return "".join(s.text for s in segments).strip()


def summarize(rows: list[dict]) -> dict:
    import statistics as stats

    secs = [r["seconds"] for r in rows]
    rtfs = [r["rtf"] for r in rows]
    cers = [r["cer"] for r in rows]
    short = rows[:N_SHORT]
    fail_all = sum(1 for c in cers if c is not None and c > CER_FAIL_THRESHOLD)
    fail_short = sum(1 for r in short if r["cer"] is not None and r["cer"] > CER_FAIL_THRESHOLD)
    ok_cers = [c for c in cers if c is not None]
    return {
        "n": len(rows),
        "n_short": len(short),
        "s_per_clip_mean": stats.fmean(secs) if secs else 0.0,
        "rtf_mean": stats.fmean(rtfs) if rtfs else 0.0,
        "ram_peak_gb": (max(r["ram_peak_bytes"] for r in rows) / 1e9) if rows else 0.0,
        "cer_mean": (stats.fmean(ok_cers)) if ok_cers else None,
        "pct_cer_gt_015_all": fail_all / len(rows) if rows else 0.0,
        "pct_cer_gt_015_short": fail_short / len(short) if short else 0.0,
    }


def cmd_run(engine: str, limit: int = len(PHRASES)) -> Path:
    if engine not in SYNTH:
        raise SystemExit(f"--engine debe ser uno de {ENGINES}")
    ref = ref_path()
    if not ref.exists():
        raise SystemExit(f"falta {ref}: corre primero el subcomando make-ref")
    phrases = PHRASES[:limit]
    out_json = json_path(engine)
    cdir = clips_dir(engine)

    synth = SYNTH[engine]

    from faster_whisper import WhisperModel

    print(f"cargando faster-whisper small (int8, cpu) ...", flush=True)
    whisper = WhisperModel("small", device="cpu", compute_type="int8")

    import jiwer

    rows: list[dict] = []
    t_run0 = time.perf_counter()
    for i, text in enumerate(phrases):
        clip = cdir / f"{i:02d}.wav"
        sampler = RamSampler()
        t0 = time.perf_counter()
        with sampler:
            synth(text, ref, clip)
        seconds = time.perf_counter() - t0
        duration = wav_duration_s(clip)
        rtf = seconds / duration if duration > 0 else 0.0
        hyp = transcribe_clip(whisper, clip)
        cer = jiwer.cer(norm(text), norm(hyp))
        rows.append(
            {
                "id": i,
                "text": text,
                "short": i < N_SHORT,
                "audio": str(clip.relative_to(repo_root())),
                "seconds": round(seconds, 3),
                "duration_s": round(duration, 3),
                "rtf": round(rtf, 3),
                "ram_peak_bytes": sampler.peak,
                "ram_peak_gb": round(sampler.peak / 1e9, 3),
                "hypothesis": hyp,
                "cer": round(cer, 4),
            }
        )
        print(
            f"[{engine} {i + 1}/{len(phrases)}] {seconds:7.1f}s "
            f"rtf={rtf:5.2f} ram={sampler.peak / 1e9:4.2f}GB cer={cer:.3f} :: {text}",
            flush=True,
        )

    summary = summarize(rows)
    payload = {
        "engine": engine,
        "model": XTTS_MODEL if engine == "xtts" else "chatterbox-multilingual (language_id=fr)",
        "versions": engine_versions(engine),
        "ref": str(ref.relative_to(repo_root())),
        "whisper": {"model": "small", "compute_type": "int8", "device": "cpu", "language": "fr"},
        "cer_threshold": CER_FAIL_THRESHOLD,
        "total_wall_s": round(time.perf_counter() - t_run0, 1),
        "system": {
            "cpu_count": os.cpu_count(),
            "platform": platform.platform(),
        },
        "rows": rows,
        "summary": summary,
    }
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nOK {engine}: {out_json} ({len(rows)} filas, resumen={summary})")
    return out_json


# ---------------------------------------------------------------------------
# requant: reconstruir el JSON desde clips existentes + log de tiempos
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"\[(?P<engine>[a-z]+)\s+(?P<idx>\d+)/(?P<total>\d+)\]\s+"
    r"(?P<seconds>[\d.]+)s\s+rtf=(?P<rtf>[\d.]+)\s+"
    r"ram=(?P<ram_gb>[\d.]+)GB\s+cer=(?P<cer>[\d.]+)\s+::\s(?P<text>.*)"
)


def parse_log_timings(engine: str) -> dict[int, dict]:
    """Lee <engine>.log y devuelve {indice: {seconds, rtf, ram_gb, log_cer}}."""
    log = log_path(engine)
    if not log.exists():
        raise SystemExit(f"falta {log}: sin log no hay tiempos medidos que reutilizar")
    out: dict[int, dict] = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _LOG_LINE_RE.search(line)
        if m and m.group("engine") == engine:
            out[int(m.group("idx")) - 1] = {
                "seconds": float(m.group("seconds")),
                "rtf": float(m.group("rtf")),
                "ram_gb": float(m.group("ram_gb")),
                "log_cer": float(m.group("cer")),
            }
    return out


def cmd_requant(engine: str, limit: int = 10) -> Path:
    """Reconstruye <engine>.json sin re-sintetizar.

    Usa los clips existentes (00.wav..), los tiempos/RAM medidos en
    <engine>.log y re-transcribe + re-calcula CER y duracion con la misma
    configuracion que `run` (faster-whisper small int8 CPU, `norm`).
    """
    if engine not in SYNTH:
        raise SystemExit(f"--engine debe ser uno de {ENGINES}")
    ensure_worktree_tmp()
    ref = ref_path()
    if not ref.exists():
        raise SystemExit(f"falta {ref}: corre primero el subcomando make-ref")
    phrases = PHRASES[:limit]
    out_json = json_path(engine)
    cdir = clips_dir(engine)
    for i in range(len(phrases)):
        if not (cdir / f"{i:02d}.wav").exists():
            raise SystemExit(f"falta {cdir / f'{i:02d}.wav'}: requant no sintetiza")
    timings = parse_log_timings(engine)
    missing = [i for i in range(len(phrases)) if i not in timings]
    if missing:
        raise SystemExit(f"el log no trae tiempos para los indices {missing}")

    from faster_whisper import WhisperModel

    print("cargando faster-whisper small (int8, cpu) ...", flush=True)
    whisper = WhisperModel("small", device="cpu", compute_type="int8")

    import jiwer

    rows: list[dict] = []
    for i, text in enumerate(phrases):
        clip = cdir / f"{i:02d}.wav"
        t = timings[i]
        duration = wav_duration_s(clip)
        hyp = transcribe_clip(whisper, clip)
        cer = jiwer.cer(norm(text), norm(hyp))
        if abs(cer - t["log_cer"]) > 0.05:
            print(
                f"AVISO clip {i:02d}: CER re-calculado={cer:.3f} difiere del "
                f"log={t['log_cer']:.3f} (se conserva el re-calculado).",
                file=sys.stderr,
            )
        ram_bytes = int(round(t["ram_gb"] * 1e9))
        rows.append(
            {
                "id": i,
                "text": text,
                "short": i < N_SHORT,
                "audio": str(clip.relative_to(repo_root())),
                "seconds": round(t["seconds"], 3),
                "duration_s": round(duration, 3),
                "rtf": round(t["rtf"], 3),
                "ram_peak_bytes": ram_bytes,
                "ram_peak_gb": round(ram_bytes / 1e9, 3),
                "hypothesis": hyp,
                "cer": round(cer, 4),
            }
        )
        print(
            f"[{engine} requant {i + 1}/{len(phrases)}] {t['seconds']:7.1f}s "
            f"rtf={t['rtf']:5.2f} ram={t['ram_gb']:4.2f}GB cer={cer:.3f} :: {text}",
            flush=True,
        )

    summary = summarize(rows)
    payload = {
        "engine": engine,
        "model": XTTS_MODEL if engine == "xtts" else "chatterbox-multilingual (language_id=fr)",
        "versions": engine_versions(engine),
        "ref": str(ref.relative_to(repo_root())),
        "whisper": {"model": "small", "compute_type": "int8", "device": "cpu", "language": "fr"},
        "cer_threshold": CER_FAIL_THRESHOLD,
        "total_wall_s": round(sum(r["seconds"] for r in rows), 1),
        "system": {
            "cpu_count": os.cpu_count(),
            "platform": platform.platform(),
        },
        "rows": rows,
        "summary": summary,
        "provenance": {
            "method": "requant",
            "note": "clips reutilizados sin re-sintetizar; seconds/ram del log, CER re-calculado",
        },
    }
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nOK {engine}: {out_json} ({len(rows)} filas, resumen={summary})")
    return out_json


# ---------------------------------------------------------------------------
# report: tabla Markdown uniendo los JSON
# ---------------------------------------------------------------------------

def _fmt(x: object) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.3f}"
    return str(x)


def cmd_report() -> None:
    found: dict[str, dict] = {}
    for engine in ENGINES:
        p = json_path(engine)
        if p.exists():
            found[engine] = json.loads(p.read_text(encoding="utf-8"))
    if not found:
        raise SystemExit("no hay JSON de benchmark en .cache/spikes/spk03/ (corre run primero)")
    lines = [
        "| motor | s/clip medio | RTF medio | RAM pico GB | CER medio | % CER>0.15 (todas) | % CER>0.15 (1-3 palabras) | n |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for engine, payload in found.items():
        s = payload["summary"]
        lines.append(
            f"| {engine} | {s['s_per_clip_mean']:.1f} | {s['rtf_mean']:.2f} | "
            f"{s['ram_peak_gb']:.2f} | {_fmt(s['cer_mean'])} | "
            f"{100 * s['pct_cer_gt_015_all']:.0f}% | {100 * s['pct_cer_gt_015_short']:.0f}% | {s['n']} |"
        )
    print("\n".join(lines))
    for engine, payload in found.items():
        v = payload.get("versions", {})
        print(f"\n<!-- {engine} versions: {json.dumps(v, sort_keys=True)} -->")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="SPK-03: benchmark de clonacion en CPU")
    ap.add_argument("--engine", choices=list(ENGINES), default=None,
                    help="motor (requerido por el subcomando run)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_ref = sub.add_parser("make-ref", help="generar ref.wav con Edge-TTS")
    p_ref.add_argument("--voice", default=VOICE_REF)
    p_run = sub.add_parser("run", help="correr el benchmark de un motor")
    p_run.add_argument("--engine", choices=list(ENGINES), default=None)
    p_run.add_argument("--limit", type=int, default=len(PHRASES))
    p_req = sub.add_parser("requant", help="reconstruir JSON desde clips + log")
    p_req.add_argument("--engine", choices=list(ENGINES), default=None)
    p_req.add_argument("--limit", type=int, default=10)
    sub.add_parser("report", help="tabla Markdown con los JSON")
    return ap


def main(argv: list[str] | None = None) -> None:
    ensure_tls_trust()
    ensure_worktree_tmp()
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.cmd == "make-ref":
        if shutil.which("ffmpeg") is None:
            raise SystemExit("falta ffmpeg en el PATH")
        cmd_make_ref(args.voice)
    elif args.cmd == "run":
        engine = args.engine or getattr(args, "engine", None)
        if engine is None:
            raise SystemExit("run requiere --engine chatterbox|xtts")
        cmd_run(engine, limit=args.limit)
    elif args.cmd == "requant":
        engine = args.engine or getattr(args, "engine", None)
        if engine is None:
            raise SystemExit("requant requiere --engine chatterbox|xtts")
        cmd_requant(engine, limit=args.limit)
    elif args.cmd == "report":
        cmd_report()


if __name__ == "__main__":
    main()
