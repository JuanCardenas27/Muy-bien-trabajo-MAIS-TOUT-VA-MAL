from frances.extract.lang import detect_lang, split_blocks


def test_french_and_spanish_sentences():
    assert detect_lang("Je voudrais un café, s'il vous plaît.") == "fr"
    assert detect_lang("Quisiera un café, por favor, gracias.") == "es"


def test_mixed_paragraph():
    txt = "Le chat dort sur le canapé tout l'après-midi. El perro juega en el jardín con los niños."
    assert detect_lang(txt) == "mixed"


def test_short_text_is_unknown():
    assert detect_lang("Bonjour") == "unknown"


def test_split_blocks_by_blank_line():
    blocks = split_blocks(
        "Je suis étudiant à l'université.\n\n   \n\nSoy estudiante de la universidad.",
        "at_0123456789abcdef",
        page=2,
    )
    assert [(b.lang, b.source, b.page) for b in blocks] == [
        ("fr", "at_0123456789abcdef", 2),
        ("es", "at_0123456789abcdef", 2),
    ]
    assert blocks[0].text == "Je suis étudiant à l'université."
