"""Tests del generador por reglas (CRD-02): spaCy + Translator inyectado."""

from frances.cards.rules import PENDING_NOTE, RulesGenerator
from frances.models.content import GenerationInput, TextBlock

LESSON = (
    "Bonjour ! Je m'appelle Marie et j'habite à Lyon. "
    "Le matin, je vais à l'école avec mon frère. "
    "L'école est grande et les professeurs sont gentils. "
    "Nous mangeons à la cantine."
)


class FakeTranslator:
    """Devuelve "ES:" + texto y registra las llamadas por lote."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate(
        self, texts: list[str], src: str = "fr", dst: str = "es"
    ) -> list[str | None]:
        self.calls.append(list(texts))
        return ["ES:" + t for t in texts]


class NoneTranslator:
    """Simula cuota agotada: todo queda pendiente."""

    def translate(
        self, texts: list[str], src: str = "fr", dst: str = "es"
    ) -> list[str | None]:
        return [None] * len(texts)


def _inp(text: str, lang: str) -> GenerationInput:
    return GenerationInput(
        item_id="it_1",
        title="Leçon 1",
        blocks=[TextBlock(text=text, lang=lang, source="item")],  # type: ignore[arg-type]
        input_hash="h",
    )


def _vocab(out) -> list[str]:
    return [c.front_fr for c in out.cards if c.kind == "vocab"]


def test_vocab_has_article_with_elision() -> None:
    fronts = _vocab(RulesGenerator(FakeTranslator()).generate(_inp(LESSON, "fr")))
    assert "l'école" in fronts and "la cantine" in fronts and "le matin" in fronts


def test_no_proper_nouns() -> None:
    fronts = {
        c.front_fr.lower()
        for c in RulesGenerator(FakeTranslator()).generate(_inp(LESSON, "fr")).cards
    }
    assert not any("marie" in f or "lyon" in f for f in fronts)


def test_respects_vocab_max() -> None:
    assert (
        len(
            _vocab(
                RulesGenerator(FakeTranslator(), vocab_max=3).generate(
                    _inp(LESSON, "fr")
                )
            )
        )
        == 3
    )


def test_phrases_between_3_and_14_tokens_max_10() -> None:
    out = RulesGenerator(FakeTranslator()).generate(_inp(LESSON, "fr"))
    phrases = [c for c in out.cards if c.kind == "phrase"]
    assert 1 <= len(phrases) <= 10
    for card in phrases:
        n_tokens = len(card.front_fr.split())
        assert 3 <= n_tokens <= 14
        assert card.back_es.startswith("ES:")


def test_single_batched_translation_call() -> None:
    t = FakeTranslator()
    RulesGenerator(t).generate(_inp(LESSON, "fr"))
    assert len(t.calls) == 1


def test_none_translation_marks_pending() -> None:
    card = RulesGenerator(NoneTranslator()).generate(_inp(LESSON, "fr")).cards[0]
    assert card.back_es == "" and card.notes == PENDING_NOTE


def test_spanish_blocks_ignored() -> None:
    out = RulesGenerator(FakeTranslator()).generate(
        _inp("Hola a todos, mañana hay clase.", "es")
    )
    assert out.cards == [] and out.sheet.vocab_fronts == []


def test_sheet_summary_and_grammar_empty() -> None:
    s = RulesGenerator(FakeTranslator()).generate(_inp(LESSON, "fr")).sheet
    assert s.summary_es.startswith("ES:") and s.grammar == [] and s.vocab_fronts
