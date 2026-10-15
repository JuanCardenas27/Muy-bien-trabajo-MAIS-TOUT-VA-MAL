"""Tests for frances.bundle.frb1 (Task BND-01)."""

import base64
import hashlib
import json
import unicodedata
from pathlib import Path

import pytest

from frances.bundle.frb1 import (
    AAD,
    CHECK_PLAINTEXT,
    MAGIC,
    NONCE_LEN,
    b64url_decode,
    b64url_encode,
    decrypt,
    derive_keys,
    derive_master,
    encrypt,
    file_id,
    make_check,
)

SALT = bytes(range(16))  # b64url "AAECAwQFBgcICQoLDA0ODw"
ITERATIONS = 1000

NFC_PASS = unicodedata.normalize("NFC", "mot de passe très très long é")
NFD_PASS = unicodedata.normalize("NFD", "mot de passe très très long é")


def _keys(p: str) -> tuple[bytes, bytes]:
    return derive_keys(derive_master(p, SALT, ITERATIONS))


def test_roundtrip() -> None:
    enc, non = _keys("demo demo demo demo demo demo")
    assert decrypt(encrypt(b"Bonjour", enc, non), enc) == b"Bonjour"


def test_deterministic_blob() -> None:
    enc, non = _keys("demo demo demo demo demo demo")
    a = encrypt(b"x" * 100, enc, non)
    b = encrypt(b"x" * 100, enc, non)
    assert a == b
    assert a[:4] == b"FRB1"
    assert a[:4] == MAGIC
    assert len(a) == 4 + 12 + 100 + 16
    assert NONCE_LEN == 12
    assert AAD == b"FRB1"


def test_bad_magic_raises() -> None:
    enc, non = _keys("demo demo demo demo demo demo")
    blob = encrypt(b"Bonjour", enc, non)
    with pytest.raises(ValueError):
        decrypt(b"FRB0" + blob[4:], enc)


def test_tampered_tag_raises() -> None:
    enc, non = _keys("demo demo demo demo demo demo")
    blob = bytearray(encrypt(b"Bonjour", enc, non))
    blob[-1] ^= 1
    with pytest.raises(ValueError):
        decrypt(bytes(blob), enc)


def test_wrong_key_raises() -> None:
    enc, non = _keys("demo demo demo demo demo demo")
    blob = encrypt(b"Bonjour", enc, non)
    other_enc, _ = _keys("otra passphrase de veinticuatro")
    with pytest.raises(ValueError):
        decrypt(blob, other_enc)


def test_nfc_nfd_passphrase_same_key() -> None:
    assert NFC_PASS != NFD_PASS
    assert _keys(NFC_PASS) == _keys(NFD_PASS)


def test_file_id_is_32_hex() -> None:
    assert file_id(b"FRB1abc") == hashlib.sha256(b"FRB1abc").hexdigest()[:32]


def test_check_decrypts_to_frb1_ok() -> None:
    enc, non = _keys("demo demo demo demo demo demo")
    assert CHECK_PLAINTEXT == b"FRB1-OK"
    assert decrypt(b64url_decode(make_check(enc, non)), enc) == b"FRB1-OK"


def test_vectors_reproducible(fixtures_dir: Path) -> None:
    vectors = json.loads((fixtures_dir / "frb1_vectors.json").read_text(encoding="utf-8"))
    assert len(vectors) == 4
    assert vectors[2]["enc_key_hex"] == vectors[3]["enc_key_hex"]  # NFC vs NFD
    for v in vectors:
        salt = b64url_decode(v["salt_b64url"])
        master = derive_master(v["passphrase"], salt, v["iterations"])
        enc, non = derive_keys(master)
        assert enc.hex() == v["enc_key_hex"]
        plaintext = base64.b64decode(v["plaintext_b64"])
        blob = b64url_decode(v["blob_b64"])
        assert b64url_encode(encrypt(plaintext, enc, non)) == v["blob_b64"]
        assert file_id(blob) == v["file_id"]
