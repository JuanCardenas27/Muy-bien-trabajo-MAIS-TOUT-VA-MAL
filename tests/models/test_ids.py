import hashlib
import re
import unicodedata

from frances.models.ids import attachment_id, card_id, content_hash, item_id


def test_card_id_typography_invariant() -> None:
    base = card_id("l'école", "vocab")
    assert card_id("l’école", "vocab") == base
    assert card_id(unicodedata.normalize("NFD", "l'école"), "vocab") == base
    assert card_id("« l'école »", "vocab") == base
    assert card_id("l'école", "phrase") != base
    assert re.fullmatch(r"c_[0-9a-f]{16}", base)


def test_item_id_prefixes() -> None:
    assert [item_id(k, "123") for k in ("coursework", "material", "announcement")] == [
        "cw_123",
        "mt_123",
        "an_123",
    ]


def test_attachment_id_stable_and_16_hex() -> None:
    a = attachment_id("cw_1", "drive_file", "abc")
    assert a == attachment_id("cw_1", "drive_file", "abc") and re.fullmatch(r"at_[0-9a-f]{16}", a)
    assert a == "at_" + hashlib.sha256("cw_1\x1fdrive_file\x1fabc".encode()).hexdigest()[:16]
    assert a != attachment_id("cw_1", "link", "abc")


def test_content_hash() -> None:
    assert content_hash("a", "b") == hashlib.sha256(b"a\x1fb").hexdigest()
