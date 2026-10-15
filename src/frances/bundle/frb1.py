"""Formato FRB1 de bundle cifrado (Task BND-01).

Bloque: ``b"FRB1" || nonce || AESGCM(enc_key).encrypt(nonce, plaintext, aad=b"FRB1")``.
Ver el plan maestro (seccion FRB1) para la derivacion completa de claves.
"""

import argparse
import base64
import hashlib
import hmac
import json
import unicodedata
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"FRB1"
AAD = b"FRB1"
NONCE_LEN = 12
CHECK_PLAINTEXT = b"FRB1-OK"

_VECTOR_SALT = bytes(range(16))
_VECTOR_ITERATIONS = 1000
_VECTOR_CASES: tuple[tuple[str, bytes], ...] = (
    ("demo demo demo demo demo demo", b"FRB1-OK"),
    ("correct horse battery staple ok", b""),
    (
        unicodedata.normalize("NFC", "mot de passe très très long é"),
        "Bonjour, l\u2019\u00e9cole !".encode(),
    ),
    (
        unicodedata.normalize("NFD", "mot de passe très très long é"),
        bytes(range(256)) * 4,
    ),
)


def derive_master(passphrase: str, salt: bytes, iterations: int) -> bytes:
    """Deriva la clave maestra de 32 bytes con PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(unicodedata.normalize("NFC", passphrase).encode("utf-8"))


def _hkdf(master: bytes, info: bytes) -> bytes:
    kdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"", info=info)
    return kdf.derive(master)


def derive_keys(master: bytes) -> tuple[bytes, bytes]:
    """Deriva ``(enc_key, nonce_key)`` desde la clave maestra."""
    return (_hkdf(master, b"FRB1 enc"), _hkdf(master, b"FRB1 nonce"))


def encrypt(plaintext: bytes, enc_key: bytes, nonce_key: bytes) -> bytes:
    """Cifra con nonce determinista: el mismo contenido da el mismo blob."""
    nonce = hmac.new(nonce_key, hashlib.sha256(plaintext).digest(), "sha256").digest()[:NONCE_LEN]
    return MAGIC + nonce + AESGCM(enc_key).encrypt(nonce, plaintext, AAD)


def decrypt(blob: bytes, enc_key: bytes) -> bytes:
    """Descifra un blob FRB1; lanza ValueError si magic, longitud o tag son invalidos."""
    if len(blob) < 4 + NONCE_LEN + 16:
        raise ValueError("FRB1: blob demasiado corto")
    if blob[:4] != MAGIC:
        raise ValueError("FRB1: magic inválido")
    try:
        return AESGCM(enc_key).decrypt(blob[4 : 4 + NONCE_LEN], blob[4 + NONCE_LEN :], AAD)
    except InvalidTag as exc:
        raise ValueError("FRB1: autenticación fallida") from exc


def file_id(blob: bytes) -> str:
    """ID de archivo publicado: 32 primeros hex de sha256(blob) (``d/<id>.bin``)."""
    return hashlib.sha256(blob).hexdigest()[:32]


def b64url_encode(data: bytes) -> str:
    """Base64 URL-safe sin padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    """Base64 URL-safe que acepta entrada sin padding."""
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_check(enc_key: bytes, nonce_key: bytes) -> str:
    """Comprobación de clave para bundle.json: blob de CHECK_PLAINTEXT en b64url."""
    return b64url_encode(encrypt(CHECK_PLAINTEXT, enc_key, nonce_key))


def main(argv: list[str] | None = None) -> int:
    """Escribe los vectores de prueba compartidos con la app web (WEB-02)."""
    parser = argparse.ArgumentParser(description="Utilidades del formato FRB1")
    parser.add_argument("--write-vectors", required=True, help="Ruta del JSON de vectores")
    args = parser.parse_args(argv)
    vectors = []
    for passphrase, plaintext in _VECTOR_CASES:
        enc_key, nonce_key = derive_keys(
            derive_master(passphrase, _VECTOR_SALT, _VECTOR_ITERATIONS)
        )
        blob = encrypt(plaintext, enc_key, nonce_key)
        vectors.append(
            {
                "passphrase": passphrase,
                "salt_b64url": b64url_encode(_VECTOR_SALT),
                "iterations": _VECTOR_ITERATIONS,
                "plaintext_b64": base64.b64encode(plaintext).decode("ascii"),
                "enc_key_hex": enc_key.hex(),
                "blob_b64": b64url_encode(blob),
                "file_id": file_id(blob),
            }
        )
    out_path = Path(args.write_vectors)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(vectors, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
