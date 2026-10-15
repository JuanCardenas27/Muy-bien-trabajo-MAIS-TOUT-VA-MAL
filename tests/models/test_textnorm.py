from frances.textnorm import display_clean, norm_key, tts_norm


def test_tts_norm_keeps_case_and_punct() -> None:
    assert tts_norm("Allez\u202f!") == "Allez !"
    assert tts_norm("Allez !") != tts_norm("allez")
    assert tts_norm("l\u2019école") == "l'école"


def test_display_clean_keeps_typography() -> None:
    assert display_clean("  « l\u2019école »\u202f?  ") == "« l\u2019école »\u202f?"
    assert display_clean("a   b") == "a b"


def test_norm_key() -> None:
    assert norm_key("« Bonjour ! »") == "bonjour"
    assert norm_key("L\u2019École") == "l'école"
